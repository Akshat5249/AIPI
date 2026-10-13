"""Allowlisted, parameterized telemetry SELECTs under investigator_ro only."""

from datetime import UTC, datetime
from typing import Any

from aipi_telemetry.evidence import Evidence, EvidenceType, evidence_id
from aipi_telemetry.storage import events, logs, metrics, spans
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Table, case, create_engine, func, select, text
from sqlalchemy.engine import Engine, make_url

from aipi_tools.ranking import (
    ERROR_SEVERITIES,
    RETRIEVAL_VERSION,
    RULE_METRICS,
    RUNTIME_NAMES,
    select_ranked,
)
from aipi_tools.scope import Incident, Scope, ScopeDenied, ScopePolicy, ScopeRequest, Window

LIMIT = 50
SOURCES: tuple[tuple[EvidenceType, Table], ...] = (
    ("event", events),
    ("metric", metrics),
    ("log", logs),
    ("trace", spans),
)


class TypeCounts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    event: int = Field(default=0, ge=0)
    metric: int = Field(default=0, ge=0)
    log: int = Field(default=0, ge=0)
    trace: int = Field(default=0, ge=0)

    @property
    def total(self) -> int:
        return sum(self.model_dump().values())


class EvidenceBundle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    source_id: str
    window: Window
    query_params: Scope
    snapshot_at: datetime
    truncated: bool
    items: tuple[Evidence, ...]
    retrieval_version: str = RETRIEVAL_VERSION
    available_counts: TypeCounts
    dropped_counts: TypeCounts

    @model_validator(mode="after")
    def valid_counts(self) -> "EvidenceBundle":
        selected = {
            kind: sum(item.type == kind for item in self.items)
            for kind in self.available_counts.model_dump()
        }
        expected = {
            kind: count - selected[kind]
            for kind, count in self.available_counts.model_dump().items()
        }
        if (
            len(self.items) > LIMIT
            or expected != self.dropped_counts.model_dump()
            or self.truncated != (self.dropped_counts.total > 0)
        ):
            raise ValueError("Evidence truncation metadata is inconsistent")
        return self


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
        if key not in {"ingested_at", "ts", "start_ts", "redactions", "_relevance"}
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


def priority(kind: EvidenceType, table: Table, scope: Scope) -> Any:
    """Match the pure relevance tiers using only names and scoped log severity."""
    if kind == "event":
        return case((table.c.event_name.in_(RUNTIME_NAMES), 0), else_=3)
    if kind == "metric":
        return case((table.c.metric_name.in_(RULE_METRICS), 1), else_=3)
    if kind == "log":
        return case((table.c.severity.in_(ERROR_SEVERITIES), 2), else_=3)
    linked_error = (
        select(logs.c.id)
        .where(
            logs.c.trace_id == table.c.trace_id,
            logs.c.trace_id != "",
            logs.c.service.in_(scope.services),
            logs.c.ts >= scope.window.start_time,
            logs.c.ts <= scope.window.end_time,
            logs.c.severity.in_(ERROR_SEVERITIES),
        )
        .exists()
    )
    return case((linked_error, 2), else_=3)


def source_reference(kind: EvidenceType, table: Table) -> Any:
    if kind == "trace":
        return table.name + ":" + table.c.trace_id + ":" + table.c.span_id
    return table.name + ":" + table.c.id


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
        candidates: list[tuple[int, Evidence]] = []
        available: dict[str, int] = {}
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
                bounded = (
                    table.c.service.in_(scope.services),
                    stamp >= scope.window.start_time,
                    stamp <= scope.window.end_time,
                )
                available[kind] = int(
                    db.scalar(select(func.count()).select_from(table).where(*bounded)) or 0
                )
                rank = priority(kind, table, scope)
                rows = db.execute(
                    select(table, rank.label("_relevance"))
                    .where(*bounded)
                    .order_by(rank, stamp, source_reference(kind, table))
                    .limit(LIMIT)
                ).mappings()
                for row in rows:
                    candidates.append((row["_relevance"], from_row(kind, table, dict(row))))
        chosen = select_ranked(candidates, LIMIT)
        dropped = {
            kind: count - sum(item.type == kind for item in chosen)
            for kind, count in available.items()
        }
        return EvidenceBundle(
            source_id=str(incident.id),
            window=scope.window,
            query_params=scope,
            snapshot_at=datetime.now(UTC),
            truncated=sum(dropped.values()) > 0,
            items=chosen,
            available_counts=TypeCounts.model_validate(available),
            dropped_counts=TypeCounts.model_validate(dropped),
        )
