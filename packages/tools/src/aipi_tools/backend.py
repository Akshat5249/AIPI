"""Scoped SELECT-only live tools and an equivalent offline fixture backend."""

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, cast
from uuid import UUID

from aipi_telemetry.evidence import Evidence, EvidenceType, evidence_id
from aipi_telemetry.storage import events, logs, metrics, spans
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SQLTimeout

from aipi_tools.contracts import (
    LogsInput,
    MetricInput,
    ReplicationInput,
    RunbookInput,
    RuntimeInput,
    ToolInput,
    ToolName,
    TraceInput,
)
from aipi_tools.metric_summaries import summarize_metrics
from aipi_tools.retrieval import EvidenceReader, from_row
from aipi_tools.runbooks import RunbookIndex
from aipi_tools.scope import Incident, Scope, ScopeDenied

REPLICATION_METRICS = (
    "replica_lag_seconds",
    "replica_lag_bytes",
    "replica_replay_paused",
    "primary_healthy",
)


class ToolTimeout(Exception):
    pass


class ToolBackend(Protocol):
    def incident(self, identifier: UUID) -> Incident: ...
    def fetch(self, name: ToolName, args: ToolInput, scope: Scope) -> tuple[Evidence, ...]: ...


def matches(item: Evidence, name: ToolName, args: ToolInput) -> bool:
    if name == "logs_query" and isinstance(args, LogsInput):
        return (
            item.type == "log"
            and (args.severity is None or item.payload.get("severity") == args.severity)
            and (
                args.text is None or args.text.lower() in str(item.payload.get("body", "")).lower()
            )
        )
    if name == "metric_query" and isinstance(args, MetricInput):
        return item.type == "metric" and item.payload.get("metric_name") == args.metric_name
    if name == "trace_lookup" and isinstance(args, TraceInput):
        duration = item.payload.get("duration_ms", 0)
        return (
            item.type == "trace"
            and (args.trace_id is None or item.payload.get("trace_id") == args.trace_id)
            and (
                not args.errors_only
                or str(item.payload.get("status")) in {"2", "STATUS_CODE_ERROR"}
            )
            and (
                args.slow_ms is None
                or isinstance(duration, (int, float))
                and duration >= args.slow_ms
            )
        )
    if name == "runtime_events_query" and isinstance(args, RuntimeInput):
        return item.type == "event" and item.payload.get("event_name") in args.names
    if name == "db_replication_status" and isinstance(args, ReplicationInput):
        return item.type == "metric" and item.payload.get("metric_name") in REPLICATION_METRICS
    return False


class FixtureBackend:
    def __init__(self, incident: Incident, items: Sequence[Evidence], runbooks: Path) -> None:
        self.boundary = incident
        self.items = tuple(items)
        self.runbooks = RunbookIndex(runbooks)

    def incident(self, identifier: UUID) -> Incident:
        if identifier != self.boundary.id:
            raise ScopeDenied("Unknown incident")
        return self.boundary

    def fetch(self, name: ToolName, args: ToolInput, scope: Scope) -> tuple[Evidence, ...]:
        if isinstance(args, RunbookInput):
            return self.runbooks.search(args.query, scope)
        bounded = tuple(
            e
            for e in self.items
            if e.service in scope.services
            and scope.window.start_time <= e.timestamp <= scope.window.end_time
            and matches(e, name, args)
        )
        return (
            summarize_metrics(bounded)
            if name in {"metric_query", "db_replication_status"}
            else bounded
        )


class SQLBackend:
    def __init__(
        self, reader: EvidenceReader, runbooks: Path, replica_url: str | None = None
    ) -> None:
        self.reader = reader
        self.runbooks = RunbookIndex(runbooks)
        self.replica = EvidenceReader(replica_url) if replica_url else None

    def incident(self, identifier: UUID) -> Incident:
        with self.reader.engine.connect() as db:
            row = (
                db.execute(
                    text(
                        "SELECT id,title,service,related_services,start_time,end_time,"
                        "symptom,status,created_at FROM public.incidents WHERE id=:id"
                    ),
                    {"id": identifier},
                )
                .mappings()
                .first()
            )
        if row is None:
            raise ScopeDenied("Unknown incident")
        return Incident.model_validate(dict(row))

    def fetch(self, name: ToolName, args: ToolInput, scope: Scope) -> tuple[Evidence, ...]:
        if isinstance(args, RunbookInput):
            return self.runbooks.search(args.query, scope)
        kind, table = {
            "logs_query": ("log", logs),
            "metric_query": ("metric", metrics),
            "trace_lookup": ("trace", spans),
            "runtime_events_query": ("event", events),
            "db_replication_status": ("metric", metrics),
        }[name]
        stamp = table.c.start_ts if kind == "trace" else table.c.ts
        conditions = [
            table.c.service.in_(scope.services),
            stamp >= scope.window.start_time,
            stamp <= scope.window.end_time,
        ]
        if isinstance(args, LogsInput):
            if args.severity:
                conditions.append(table.c.severity == args.severity)
            if args.text:
                conditions.append(table.c.body.icontains(args.text, autoescape=True))
        elif isinstance(args, MetricInput):
            conditions.append(table.c.metric_name == args.metric_name)
        elif isinstance(args, TraceInput):
            if args.trace_id:
                conditions.append(table.c.trace_id == args.trace_id)
            if args.errors_only:
                conditions.append(table.c.status.in_(("2", "STATUS_CODE_ERROR")))
            if args.slow_ms is not None:
                conditions.append(table.c.duration_ms >= args.slow_ms)
        elif isinstance(args, RuntimeInput):
            conditions.append(table.c.event_name.in_(args.names))
        elif isinstance(args, ReplicationInput):
            conditions.append(table.c.metric_name.in_(REPLICATION_METRICS))
        try:
            with self.reader.engine.connect() as db, db.begin():
                if db.scalar(text("SELECT current_user")) != "investigator_ro":
                    raise ScopeDenied("Unexpected retrieval identity")
                rows = db.execute(select(table).where(*conditions).order_by(stamp)).mappings()
                found = tuple(from_row(cast(EvidenceType, kind), table, dict(row)) for row in rows)
            status_items: tuple[Evidence, ...] = ()
            if (
                name == "db_replication_status"
                and self.replica
                and set(scope.services) & {"pg-lag-probe", "postgres-replica"}
            ):
                # Current status is only meaningful within this requested time window.
                # On a completed historical incident, the bounded view yields no row.
                with self.replica.engine.connect() as db:
                    if db.scalar(text("SELECT current_user")) != "investigator_ro":
                        raise ScopeDenied("Unexpected replica retrieval identity")
                    status_rows = (
                        db.execute(
                            text(
                                "SELECT CURRENT_TIMESTAMP AS observed_at, "
                                "status, written_lsn::text, flushed_lsn::text "
                                "FROM pg_stat_wal_receiver "
                                "WHERE CURRENT_TIMESTAMP BETWEEN :start AND :end"
                            ),
                            {"start": scope.window.start_time, "end": scope.window.end_time},
                        )
                        .mappings()
                        .all()
                    )
                    observed = []
                    for row in status_rows:
                        stamp = row["observed_at"]
                        reference = "replica_status:" + stamp.isoformat()
                        service = next(
                            s for s in scope.services if s in {"pg-lag-probe", "postgres-replica"}
                        )
                        observed.append(
                            Evidence(
                                evidence_id=evidence_id("event", reference),
                                type="event",
                                service=service,
                                timestamp=stamp,
                                source_ref=reference,
                                summary="Read-only WAL receiver observation",
                                payload={
                                    "event_name": "replication_status",
                                    "status": row["status"],
                                    "written_lsn": row["written_lsn"],
                                    "flushed_lsn": row["flushed_lsn"],
                                },
                            )
                        )
                    status_items = tuple(observed)
            return (summarize_metrics(found) if kind == "metric" else found) + status_items
        except SQLTimeout as exc:
            raise ToolTimeout("Read-only source timed out") from exc
        except OperationalError as exc:
            if getattr(exc.orig, "sqlstate", None) == "57014":
                raise ToolTimeout("Read-only source timed out") from exc
            raise
