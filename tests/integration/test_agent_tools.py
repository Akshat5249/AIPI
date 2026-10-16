"""Live M4a gate: actual investigator role, scoped SELECT tools and durable audits."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from aipi_api.agent_audit import DatabaseAudit
from aipi_api.agent_storage import investigations
from aipi_api.incidents import IncidentCore
from aipi_tools.backend import SQLBackend
from aipi_tools.contracts import LogsInput, ReplicationInput, RunbookInput
from aipi_tools.registry import ToolRunner
from aipi_tools.scope import IncidentCreate
from sqlalchemy import event, insert, select
from sqlalchemy.engine import make_url

from chaos.scenarios.lab import Lab
from tests.integration.test_incidents import url

pytestmark = pytest.mark.docker


def test_live_tools_durable_audit_and_readonly_privileges():
    lab = Lab()
    core = IncidentCore(url(lab, "investigator_ro"), url(lab, "telemetry_writer"))
    now = datetime.now(UTC)
    incident = core.create(
        IncidentCreate(
            title="Tool gate",
            service="pg-lag-probe",
            start_time=now - timedelta(seconds=15),
            end_time=now + timedelta(minutes=1),
            symptom="Lag check",
        )
    )
    identifier = uuid4()
    with core.writer.begin() as db:
        db.execute(
            insert(investigations).values(
                id=identifier,
                incident_id=incident.id,
                model="deterministic-mock-v1",
                provider="mock",
                status="queued",
                created_at=now,
                prompt_version="v1",
                tool_version="v1",
                code_commit="gate",
                input_tokens=0,
                output_tokens=0,
                estimated_cost=0,
            )
        )
    replica = (
        make_url(url(lab, "investigator_ro"))
        .set(port=lab.target.replica_port)
        .render_as_string(hide_password=False)
    )
    backend = SQLBackend(core.reader, Path("runbooks"), replica)
    statements = []
    for engine in (core.reader.engine, backend.replica.engine):
        event.listen(
            engine,
            "before_cursor_execute",
            lambda conn, cursor, sql, params, context, many: statements.append(sql),
        )
    audit = DatabaseAudit(core, identifier, incident.id)
    runner = ToolRunner(backend, audit, identifier, incident.id)
    try:
        status = runner.call(
            "db_replication_status", ReplicationInput(incident_id=incident.id), "Verifier"
        )
        assert status.status == "ok" and status.items
        assert any(e.payload.get("event_name") == "replication_status" for e in status.items)
        books = runner.call(
            "runbook_search",
            RunbookInput(incident_id=incident.id, query="replica lag replay"),
            "Retriever",
        )
        assert books.items and books.items[0].type == "runbook"
        denied = runner.call(
            "logs_query", LogsInput(incident_id=incident.id, service="gateway"), "Verifier"
        )
        assert denied.status == "denied"
        with core.reader.engine.connect() as db:
            from aipi_api.agent_storage import investigation_events, tool_calls

            calls = (
                db.execute(select(tool_calls).where(tool_calls.c.investigation_id == identifier))
                .mappings()
                .all()
            )
            events = (
                db.execute(
                    select(investigation_events).where(
                        investigation_events.c.investigation_id == identifier
                    )
                )
                .mappings()
                .all()
            )
        assert len(calls) == len(events) == 3 and sorted(e["seq"] for e in events) == [1, 2, 3]
        assert calls[0]["actor"] == "Verifier" and calls[0]["latency_ms"] >= 0
        assert all(
            "ground_truth" not in s and s.lstrip().upper().startswith("SELECT") for s in statements
        )
        with lab.connect("investigator_ro") as db:
            for query in (
                "INSERT INTO tool_calls(id) VALUES(gen_random_uuid())",
                "UPDATE investigations SET status='completed'",
                "INSERT INTO telemetry_logs(id) VALUES('forbidden')",
                "UPDATE telemetry_metrics SET value=0",
                "SELECT * FROM ground_truth.scenarios",
            ):
                with pytest.raises(
                    (psycopg.errors.InsufficientPrivilege, psycopg.errors.ReadOnlySqlTransaction)
                ):
                    db.execute(query)
        print(
            "M4a live: 3 calls + 3 events; denied widening logged; "
            "WAL receiver SELECT observed; investigator INSERT/UPDATE/truth denied"
        )
    finally:
        backend.replica.engine.dispose()
        core.close()
        lab.close()
