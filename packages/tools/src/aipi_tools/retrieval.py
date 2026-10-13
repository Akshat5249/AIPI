"""Allowlisted, parameterized telemetry SELECTs under investigator_ro only."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from aipi_telemetry.evidence import Evidence, EvidenceType, evidence_id
from aipi_telemetry.storage import events, logs, metrics, spans
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Table, create_engine, select, text
from sqlalchemy.engine import Engine, make_url

from aipi_tools.correlators import Signal, correlate
from aipi_tools.metric_summaries import summarize_metrics
from aipi_tools.ranking import RETRIEVAL_VERSION, rank_candidates, select_ranked
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
    raw_counts: TypeCounts
    correlation_source: Literal["full_scope"] = "full_scope"
    signals: tuple[Signal, ...]
    capped_rules: tuple[str, ...]

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


@dataclass(frozen=True)
class RetrievedSnapshot:
    bundle: EvidenceBundle
    witnesses: tuple[Evidence, ...]


def build_snapshot(
    incident: Incident, scope: Scope, raw: tuple[Evidence, ...]
) -> RetrievedSnapshot:
    """Correlate the full scope before summarization or selection; retain every cited source."""
    signals = correlate(raw)
    summarized = summarize_metrics(raw)
    chosen = select_ranked(rank_candidates(summarized), LIMIT)
    available = {kind: sum(e.type == kind for e in summarized) for kind, _ in SOURCES}
    dropped = {
        kind: count - sum(e.type == kind for e in chosen) for kind, count in available.items()
    }
    citations = {eid for result in signals for eid in result.evidence_ids}
    witnesses = tuple(e for e in raw if e.evidence_id in citations)
    return RetrievedSnapshot(
        bundle=EvidenceBundle(
            source_id=str(incident.id),
            window=scope.window,
            query_params=scope,
            snapshot_at=datetime.now(UTC),
            truncated=sum(dropped.values()) > 0,
            items=chosen,
            available_counts=TypeCounts.model_validate(available),
            dropped_counts=TypeCounts.model_validate(dropped),
            raw_counts=TypeCounts.model_validate(
                {kind: sum(e.type == kind for e in raw) for kind, _ in SOURCES}
            ),
            signals=signals,
            capped_rules=tuple(s.rule for s in correlate(chosen)),
        ),
        witnesses=witnesses,
    )


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
        return self.retrieve_snapshot(incident, request).bundle

    def retrieve_snapshot(self, incident: Incident, request: ScopeRequest) -> RetrievedSnapshot:
        scope = ScopePolicy().authorize(incident, request)
        raw: list[Evidence] = []
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
                rows = db.execute(select(table).where(*bounded).order_by(stamp)).mappings()
                raw.extend(from_row(kind, table, dict(row)) for row in rows)
        return build_snapshot(incident, scope, tuple(raw))
