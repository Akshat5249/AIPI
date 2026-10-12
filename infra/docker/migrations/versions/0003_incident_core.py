"""Scoped incidents, immutable evidence snapshots and persistent policy-denial audit."""

from aipi_api.core_storage import metadata
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    metadata.create_all(op.get_bind())
    op.execute(
        "ALTER TABLE incidents ADD CONSTRAINT incident_window CHECK "
        "(end_time>start_time AND end_time-start_time <= interval '6 hours')"
    )
    for name in ("incidents", "evidence", "evidence_bundles", "scope_denials"):
        op.execute(f"REVOKE ALL ON {name} FROM PUBLIC, app_rw, app_ro, chaos_admin")
        op.execute(f"GRANT SELECT ON {name} TO investigator_ro")
        op.execute(f"GRANT SELECT, INSERT ON {name} TO telemetry_writer")
    op.execute("""CREATE FUNCTION reject_evidence_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Evidence is immutable'; END $$""")
    for name in ("evidence", "evidence_bundles"):
        op.execute(
            f"CREATE TRIGGER immutable_rows BEFORE UPDATE OR DELETE ON {name} "
            "FOR EACH ROW EXECUTE FUNCTION reject_evidence_mutation()"
        )
        op.execute(
            f"CREATE TRIGGER immutable_truncate BEFORE TRUNCATE ON {name} "
            "FOR EACH STATEMENT EXECUTE FUNCTION reject_evidence_mutation()"
        )


def downgrade() -> None:
    metadata.drop_all(op.get_bind())
    op.execute("DROP FUNCTION reject_evidence_mutation()")
