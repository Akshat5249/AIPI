"""Investigation artifacts, SELECT-only readers and immutable provenance/audits."""

from aipi_api.agent_storage import TABLES
from aipi_api.core_storage import metadata
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    metadata.create_all(op.get_bind(), tables=list(TABLES))
    op.execute(
        "ALTER TABLE investigations ADD CHECK (status IN ('queued','running','completed','failed'))"
    )
    op.execute("ALTER TABLE hypothesis_evidence ADD CHECK (stance IN ('for','against'))")
    op.execute(
        "ALTER TABLE recommendations ADD CHECK (requires_approval=1 AND approval_status='pending')"
    )
    for table in TABLES:
        name = table.name
        op.execute(f"REVOKE ALL ON {name} FROM PUBLIC, app_rw, app_ro, chaos_admin")
        op.execute(f"GRANT SELECT ON {name} TO investigator_ro")
        op.execute(f"GRANT SELECT,INSERT ON {name} TO telemetry_writer")
        if name != "investigations":
            op.execute(
                f"CREATE TRIGGER immutable_rows BEFORE UPDATE OR DELETE ON {name} "
                "FOR EACH ROW EXECUTE FUNCTION reject_evidence_mutation()"
            )
            op.execute(
                f"CREATE TRIGGER immutable_truncate BEFORE TRUNCATE ON {name} "
                "FOR EACH STATEMENT EXECUTE FUNCTION reject_evidence_mutation()"
            )
    op.execute(
        "GRANT UPDATE(status,started_at,completed_at,input_tokens,output_tokens,"
        "estimated_cost,latency_ms,error) ON investigations TO telemetry_writer"
    )


def downgrade() -> None:
    metadata.drop_all(op.get_bind(), tables=list(reversed(TABLES)))
