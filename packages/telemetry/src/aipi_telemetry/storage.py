"""Typed telemetry columns and idempotent PostgreSQL persistence."""

from datetime import UTC, datetime
from itertools import groupby, islice
from typing import Any

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    Index,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
)
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.engine import Engine

metadata = MetaData()
json_type = JSON().with_variant(JSONB(), "postgresql")


def common() -> list[Column[Any]]:
    return [
        Column("id", String(64), primary_key=True),
        Column("ts", DateTime(timezone=True), nullable=False),
        Column("service", String(200), nullable=False),
        Column(
            "ingested_at",
            DateTime(timezone=True),
            nullable=False,
            default=lambda: datetime.now(UTC),
        ),
    ]


logs = Table(
    "telemetry_logs",
    metadata,
    *common(),
    Column("severity", String(30)),
    Column("body", Text),
    Column("trace_id", String(32)),
    Column("span_id", String(16)),
    Column("attributes_json", json_type, nullable=False),
    Column("container", String(200)),
    Column("redactions", json_type, nullable=False),
)
metrics = Table(
    "telemetry_metrics",
    metadata,
    *common(),
    Column("metric_name", String(200), nullable=False),
    Column("value", Float, nullable=False),
    Column("labels_json", json_type, nullable=False),
    Column("redactions", json_type, nullable=False),
)
spans = Table(
    "telemetry_spans",
    metadata,
    Column("trace_id", String(32), primary_key=True),
    Column("span_id", String(16), primary_key=True),
    Column("parent_span_id", String(16)),
    Column("service", String(200), nullable=False),
    Column("operation", Text),
    Column("status", String(30)),
    Column("start_ts", DateTime(timezone=True), nullable=False),
    Column("duration_ms", Float, nullable=False),
    Column("attributes_json", json_type, nullable=False),
    Column("redactions", json_type, nullable=False),
)
events = Table(
    "telemetry_events",
    metadata,
    *common(),
    Column("event_domain", String(100)),
    Column("event_name", String(100)),
    Column("attributes_json", json_type, nullable=False),
    Column("redactions", json_type, nullable=False),
)
for table in (logs, metrics, events):
    Index(f"ix_{table.name}_service_ts", table.c.service, table.c.ts)
Index("ix_logs_trace_id", logs.c.trace_id)
Index("ix_spans_trace_id", spans.c.trace_id)
Index("ix_spans_service_start_ts", spans.c.service, spans.c.start_ts)
TABLES = {"logs": logs, "metrics": metrics, "traces": spans, "events": events}


class TelemetryStore:
    """Writer adapter; investigation readers will use separate credentials."""

    def __init__(self, url: str) -> None:
        self.engine: Engine = create_engine(url, pool_pre_ping=True, hide_parameters=True)

    def persist(self, rows: dict[str, list[dict[str, Any]]]) -> int:
        count = 0
        with self.engine.begin() as connection:
            for kind, items in rows.items():
                # Preserve first-observation order, including heterogeneous optional
                # columns, while bounding each statement well below PG's bind limit.
                for _, group in groupby(items, key=lambda row: tuple(sorted(row))):
                    while batch := list(islice(group, 500)):
                        statement = insert(TABLES[kind]).values(batch).on_conflict_do_nothing()
                        result = connection.execute(statement)
                        count += result.rowcount
        return count
