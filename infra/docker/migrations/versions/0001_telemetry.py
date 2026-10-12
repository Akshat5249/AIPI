"""Initial telemetry store with per-signal indexes and restricted ingest grants."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name in ("logs", "metrics", "events"):
        columns = [
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
            sa.Column("service", sa.String(200), nullable=False),
            sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("redactions", postgresql.JSONB(), nullable=False),
        ]
        if name == "logs":
            columns += [
                sa.Column("severity", sa.String(30)),
                sa.Column("body", sa.Text()),
                sa.Column("trace_id", sa.String(32)),
                sa.Column("span_id", sa.String(16)),
                sa.Column("attributes_json", postgresql.JSONB(), nullable=False),
                sa.Column("container", sa.String(200)),
            ]
        elif name == "metrics":
            columns += [
                sa.Column("metric_name", sa.String(200), nullable=False),
                sa.Column("value", sa.Float(), nullable=False),
                sa.Column("labels_json", postgresql.JSONB(), nullable=False),
            ]
        else:
            columns += [
                sa.Column("event_domain", sa.String(100)),
                sa.Column("event_name", sa.String(100)),
                sa.Column("attributes_json", postgresql.JSONB(), nullable=False),
            ]
        op.create_table("telemetry_" + name, *columns)
        op.create_index(
            "ix_telemetry_" + name + "_service_ts", "telemetry_" + name, ["service", "ts"]
        )
    op.create_table(
        "telemetry_spans",
        sa.Column("trace_id", sa.String(32), primary_key=True),
        sa.Column("span_id", sa.String(16), primary_key=True),
        sa.Column("parent_span_id", sa.String(16)),
        sa.Column("service", sa.String(200), nullable=False),
        sa.Column("operation", sa.Text()),
        sa.Column("status", sa.String(30)),
        sa.Column("start_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Float(), nullable=False),
        sa.Column("attributes_json", postgresql.JSONB(), nullable=False),
        sa.Column("redactions", postgresql.JSONB(), nullable=False),
    )
    op.create_index("ix_logs_trace_id", "telemetry_logs", ["trace_id"])
    op.create_index("ix_spans_trace_id", "telemetry_spans", ["trace_id"])
    op.create_index("ix_spans_service_start_ts", "telemetry_spans", ["service", "start_ts"])
    for table in ("logs", "metrics", "spans", "events"):
        op.execute(f"GRANT SELECT, INSERT ON telemetry_{table} TO telemetry_writer")


def downgrade() -> None:
    for table in ("events", "spans", "metrics", "logs"):
        op.drop_table("telemetry_" + table)
