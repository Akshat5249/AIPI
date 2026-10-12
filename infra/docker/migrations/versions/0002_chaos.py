"""Restricted scenario registry and injection runs; least-privilege replay controls."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS ground_truth AUTHORIZATION chaos_admin")
    op.execute(
        "REVOKE ALL ON SCHEMA ground_truth FROM PUBLIC, investigator_ro, "
        "telemetry_writer, app_rw, app_ro"
    )
    op.create_table(
        "scenarios",
        sa.Column("id", sa.String(20), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("injected_fault", sa.Text(), nullable=False),
        sa.Column("expected_root_cause", sa.Text(), nullable=False),
        sa.Column("spec_json", postgresql.JSONB(), nullable=False),
        schema="ground_truth",
    )
    op.create_table(
        "chaos_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "scenario_id", sa.String(20), sa.ForeignKey("ground_truth.scenarios.id"), nullable=False
        ),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("injection_ts", sa.DateTime(timezone=True)),
        sa.Column("target", sa.String(200), nullable=False),
        sa.Column("expected_root_cause", sa.Text(), nullable=False),
        sa.Column("scenario_snapshot_json", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("recovery_status", sa.String(30), nullable=False),
        sa.Column("recovery_ts", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("error", sa.Text()),
        sa.Column("observations_json", postgresql.JSONB()),
        sa.CheckConstraint("status IN ('running','completed','failed','precondition_failed')"),
        sa.CheckConstraint("recovery_status IN ('pending','verified','failed','not_needed')"),
        schema="ground_truth",
    )
    op.create_index(
        "ix_chaos_runs_scenario_injection",
        "chaos_runs",
        ["scenario_id", "injection_ts"],
        schema="ground_truth",
    )
    for table in ("scenarios", "chaos_runs"):
        op.execute(f"ALTER TABLE ground_truth.{table} OWNER TO chaos_admin")
        op.execute(
            f"REVOKE ALL ON ground_truth.{table} FROM PUBLIC, investigator_ro, "
            "telemetry_writer, app_rw, app_ro"
        )
    # Catalog grants replicate to the standby. No superuser or broad role membership.
    for function in (
        "pg_wal_replay_pause",
        "pg_wal_replay_resume",
        "pg_is_wal_replay_paused",
        "pg_get_wal_replay_pause_state",
    ):
        op.execute(f"GRANT EXECUTE ON FUNCTION pg_catalog.{function}() TO chaos_admin")


def downgrade() -> None:
    for function in (
        "pg_wal_replay_pause",
        "pg_wal_replay_resume",
        "pg_is_wal_replay_paused",
        "pg_get_wal_replay_pause_state",
    ):
        op.execute(f"REVOKE EXECUTE ON FUNCTION pg_catalog.{function}() FROM chaos_admin")
    op.drop_table("chaos_runs", schema="ground_truth")
    op.drop_table("scenarios", schema="ground_truth")
