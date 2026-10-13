"""Evaluation jobs reference protected runs; API identities see scores only."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Registry seed is protected and available before a first fault run/golden API replay.
    op.execute(
        "INSERT INTO ground_truth.scenarios "
        "(id,name,description,injected_fault,expected_root_cause,spec_json) VALUES "
        "('SCN-001','Service Kill','Bounded service termination','process terminated',"
        "'checkout-api process/container terminated','{}'::jsonb),"
        "('SCN-002','Replica Lag','Bounded replica replay pause','replay paused',"
        "'postgres-replica WAL replay intentionally paused','{}'::jsonb) "
        "ON CONFLICT(id) DO NOTHING"
    )
    op.create_table(
        "evaluation_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "scenario_id", sa.String(20), sa.ForeignKey("ground_truth.scenarios.id"), nullable=False
        ),
        sa.Column("investigation_id", UUID(as_uuid=True), sa.ForeignKey("investigations.id")),
        sa.Column("chaos_run_id", UUID(as_uuid=True), sa.ForeignKey("ground_truth.chaos_runs.id")),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("request_json", JSONB, nullable=False),
        sa.Column("metrics_json", JSONB),
        sa.Column("error", sa.String(100)),
        sa.CheckConstraint("status IN ('queued','running','completed','failed')"),
    )
    op.create_index(
        "ix_evaluation_runs_scenario_created", "evaluation_runs", ["scenario_id", "created_at"]
    )
    op.execute("REVOKE ALL ON evaluation_runs FROM PUBLIC,app_rw,app_ro,chaos_admin")
    op.execute("GRANT SELECT ON evaluation_runs TO investigator_ro")
    op.execute("GRANT SELECT,INSERT ON evaluation_runs TO telemetry_writer")
    op.execute(
        "GRANT UPDATE(status,completed_at,investigation_id,metrics_json,error) "
        "ON evaluation_runs TO telemetry_writer"
    )


def downgrade() -> None:
    op.drop_table("evaluation_runs")
