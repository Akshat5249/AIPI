"""Allowlisted, parameterized telemetry SELECTs under investigator_ro only."""

from datetime import UTC, datetime
from typing import Any

from aipi_telemetry.evidence import Evidence, EvidenceType, evidence_id
from aipi_telemetry.storage import events, logs, metrics, spans
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Table, case, create_engine, select, text
from sqlalchemy.engine import Engine, make_url

from aipi_tools.scope import Incident, Scope, ScopeDenied, ScopePolicy, ScopeRequest, Window

LIMIT = 50
SOURCES: tuple[tuple[EvidenceType, Table], ...] = (
    ("event", events),
    ("metric", metrics),
    ("log", logs),
    ("trace", spans),
)


class EvidenceBundle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    source_id: str
    window: Window
    query_params: Scope
    snapshot_at: datetime
    truncated: bool
    items: tuple[Evidence, ...]


def from_row(kind: EvidenceType, table: Table, row: dict[str, Any]) -> Evidence:
    """Use only normalized telemetry columns, never external labels or registry data."""
    stamp = row["start_ts" if kind == "trace" else "ts"]
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    reference = (
        f"{table.name}:{row['trace_id']}:{row['span_id']}"
        if kind == "trace"
        else f"{table.name}:{row['id']}"
    )
    payload = {
        key: value
        for key, value in row.items()
        if key not in {"ingested_at", "ts", "start_ts", "redactions"}
    }
    if kind == "metric":
        summary = f"{row['metric_name']}={row['value']}"
    elif kind == "event":
        summary = f"{row['event_domain']}: {row['event_name']}"
    elif kind == "trace":
        summary = f"{row['operation']} status={row['status']} duration_ms={row['duration_ms']}"
    else:
        summary = f"{row['severity']}: {row['body']}"
    return Evidence(
        evidence_id=evidence_id(kind, reference),
        type=kind,
        service=row["service"],
        timestamp=stamp,
        source_ref=reference,
        summary=summary[:200],
        payload=payload,
        redactions=row["redactions"],
    )


def priority(kind: EvidenceType, table: Table) -> Any:
    """Reserve space for diagnostic signals; never use scenario labels to rank."""
    if kind == "metric":
        diagnostic = table.c.metric_name.in_(
            [
                "replica_lag_seconds",
                "replica_lag_bytes",
                "replica_replay_paused",
                "primary_healthy",
            ]
        ) | (
            (table.c.metric_name == "requests_total")
            & table.c.labels_json["status"].as_string().in_(["500", "502", "503", "504"])
        )
    elif kind == "log":
        diagnostic = table.c.severity.in_(["ERROR", "WARN", "WARNING"])
    elif kind == "trace":
        diagnostic = table.c.status.in_(["2", "STATUS_CODE_ERROR"])
    else:
        diagnostic = table.c.event_name.in_(["die", "start", "restart"])
    return case((diagnostic, 0), else_=1)


class EvidenceReader:
    """Has no write path, arbitrary SQL input, schema selector, or chaos credentials."""

    def __init__(self, url: str) -> None:
        if make_url(url).username != "investigator_ro":
            raise ValueError("Evidence retrieval requires investigator_ro")
        self.engine: Engine = create_engine(
            url,
            pool_pre_ping=True,
            hide_parameters=True,
            isolation_level="REPEATABLE READ",
            connect_args={"connect_timeout": 5, "options": "-c statement_timeout=5000"},
        )

    def retrieve(self, incident: Incident, request: ScopeRequest) -> EvidenceBundle:
        scope = ScopePolicy().authorize(incident, request)
        groups: list[list[Evidence]] = []
        with self.engine.connect() as db, db.begin():
            if db.scalar(text("SELECT current_user")) != "investigator_ro":
                raise ValueError("Evidence retrieval identity is not investigator_ro")
            persisted = (
                db.execute(
                    text(
                        "SELECT id,title,service,related_services,start_time,end_time,"
                        "symptom,status,created_at "
                        "FROM public.incidents WHERE id=:id"
                    ),
                    {"id": incident.id},
                )
                .mappings()
                .first()
            )
            if persisted is None:
                raise ScopeDenied("Incident has no authoritative persisted boundary")
            scope = ScopePolicy().authorize(Incident.model_validate(dict(persisted)), request)
            for kind, table in SOURCES:
                stamp = table.c.start_ts if kind == "trace" else table.c.ts
                identifiers = (
                    [table.c.trace_id, table.c.span_id] if kind == "trace" else [table.c.id]
                )
                rows = db.execute(
                    select(table)
                    .where(
                        table.c.service.in_(scope.services),
                        stamp >= scope.window.start_time,
                        stamp <= scope.window.end_time,
                    )
                    .order_by(priority(kind, table), stamp, *identifiers)
                    .limit(LIMIT + 1)
                ).mappings()
                groups.append([from_row(kind, table, dict(row)) for row in rows])
        total = sum(len(group) for group in groups)
        chosen: list[Evidence] = []
        # Deterministic round-robin prevents noisy traces from hiding events or lag/health gauges.
        for index in range(LIMIT + 1):
            for group in groups:
                if index < len(group) and len(chosen) < LIMIT:
                    chosen.append(group[index])
        chosen.sort(key=lambda item: (item.timestamp, item.evidence_id))
        return EvidenceBundle(
            source_id=str(incident.id),
            window=scope.window,
            query_params=scope,
            snapshot_at=datetime.now(UTC),
            truncated=total > LIMIT,
            items=tuple(chosen),
        )
