"""Live M3 gate: scoped immutable replay, real chaos windows, and ground-truth isolation."""

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import psycopg
import pytest
from aipi_telemetry.storage import TelemetryStore
from aipi_tools.correlators import PrimaryHealthRule, ProcessExitRule, ReplicaLagRule
from aipi_tools.retrieval import EvidenceBundle, EvidenceReader
from aipi_tools.scope import Incident, ScopeDenied, ScopeRequest
from sqlalchemy import event, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import ProgrammingError

from chaos.scenarios.lab import ROOT, Lab

pytestmark = pytest.mark.docker
API = "http://127.0.0.1:8000"


def url(lab, role):
    key = {
        "investigator_ro": "INVESTIGATOR_PASSWORD",
        "telemetry_writer": "TELEMETRY_WRITER_PASSWORD",
    }[role]
    return URL.create(
        "postgresql+psycopg",
        username=role,
        password=lab.env[key],
        host="127.0.0.1",
        port=5432,
        database="aipi",
    ).render_as_string(hide_password=False)


def admin(lab):
    try:
        return psycopg.connect(
            host="127.0.0.1",
            port=5432,
            dbname="aipi",
            user="postgres",
            password=lab.env["POSTGRES_PASSWORD"],
            autocommit=True,
        )
    except psycopg.Error:
        pytest.fail("Lab administrator unavailable", pytrace=False)


def create(client, start, end, service, related=()):
    response = client.post(
        "/api/incidents",
        json={
            "title": "Observed errors",
            "service": service,
            "related_services": list(related),
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
            "symptom": "Investigate observed failures",
        },
    )
    assert response.status_code == 201, response.text
    return Incident.model_validate(response.json())


@pytest.mark.parametrize(
    "module,service,related",
    [
        ("scn_001_service_kill", "checkout-api", ("gateway",)),
        ("scn_002_replica_lag", "orders-api", ("pg-lag-probe", "checkout-api")),
    ],
)
def test_live_incident_evidence_replay_and_correlations(module, service, related):
    start = datetime.now(UTC)
    command = subprocess.run(
        [sys.executable, "-m", f"chaos.scenarios.{module}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=100,
        check=False,
    )
    assert command.returncode == 0, command.stdout
    observed = json.loads(command.stdout)
    end = datetime.now(UTC)
    with httpx.Client(base_url=API, timeout=20) as client:
        current = create(client, start, end, service, related)
        path = f"/api/incidents/{current.id}"
        first_response = client.get(path + "/evidence")
        assert first_response.status_code == 200, first_response.text
        first = EvidenceBundle.model_validate(first_response.json())
        second = EvidenceBundle.model_validate(client.get(path + "/evidence").json())
        ids = [item.evidence_id for item in first.items]
        assert first == second and ids and len(ids) <= 50
        assert ids == [item.evidence_id for item in second.items]
        assert all(
            start <= item.timestamp <= end and item.service in current.services
            for item in first.items
        )
        assert all(item.source_ref.startswith("telemetry_") for item in first.items)
        timeline = client.get(path + "/timeline").json()
        assert {eid for item in timeline["items"] for eid in item["evidence_ids"]} == set(ids)
        assert [item["ts"] for item in timeline["items"]] == sorted(
            item["ts"] for item in timeline["items"]
        )
        if module == "scn_002_replica_lag":
            assert ReplicaLagRule.apply(first.items)
            contradiction = PrimaryHealthRule.apply(first.items)
            assert contradiction and contradiction[0].contradicts == "primary outage"
        else:
            assert ProcessExitRule.apply(first.items)
        print(
            json.dumps(
                {
                    "module": module,
                    "incident_id": str(current.id),
                    "items": len(ids),
                    "truncated": first.truncated,
                    "identical_ids": True,
                    "rules": [signal["rule"] for signal in client.get(path + "/signals").json()],
                    "chaos_recovery": observed["recovery_status"],
                }
            )
        )


def test_scope_cap_late_arrivals_and_database_immutability():
    lab = Lab()
    store = TelemetryStore(url(lab, "telemetry_writer"))
    stamp = datetime(2020, 1, 1, tzinfo=UTC) + timedelta(days=int(uuid4().hex[:4], 16))
    prefix = uuid4().hex
    logs = [
        {
            "id": f"{prefix}-{index}",
            "ts": stamp + timedelta(seconds=index),
            "service": "api",
            "severity": "INFO",
            "body": "synthetic cap check",
            "attributes_json": {"synthetic": True},
            "redactions": [],
        }
        for index in range(60)
    ]
    logs += [
        {**logs[0], "id": prefix + "outside-service", "service": "gateway"},
        {**logs[0], "id": prefix + "outside-time", "ts": stamp - timedelta(seconds=1)},
    ]
    store.persist(
        {
            "logs": logs,
            "events": [
                {
                    "id": prefix,
                    "ts": stamp,
                    "service": "api",
                    "event_domain": "runtime",
                    "event_name": "start",
                    "attributes_json": {},
                    "redactions": [],
                }
            ],
            "metrics": [
                {
                    "id": prefix,
                    "ts": stamp,
                    "service": "api",
                    "metric_name": "test_gauge",
                    "value": 1,
                    "labels_json": {},
                    "redactions": [],
                }
            ],
            "traces": [
                {
                    "trace_id": prefix,
                    "span_id": prefix[:16],
                    "service": "api",
                    "operation": "synthetic",
                    "status": "0",
                    "start_ts": stamp,
                    "duration_ms": 1,
                    "attributes_json": {},
                    "redactions": [],
                }
            ],
        }
    )
    try:
        with httpx.Client(base_url=API, timeout=20) as client:
            current = create(client, stamp, stamp + timedelta(seconds=60), "api")
            path = f"/api/incidents/{current.id}"
            assert client.get(path).json()["id"] == str(current.id)
            assert any(
                row["id"] == str(current.id)
                for row in client.get("/api/incidents?service=api&status=open").json()
            )
            response = client.get(path + "/evidence")
            assert response.status_code == 200, response.text
            first = EvidenceBundle.model_validate(response.json())
            assert len(first.items) == 50 and first.truncated
            assert {item.type for item in first.items} == {"log", "metric", "trace", "event"}
            assert all(
                item.service == "api" and stamp <= item.timestamp <= current.end_time
                for item in first.items
            )
            # Late arrival sorts before all original logs, but cannot alter the persisted snapshot.
            store.persist({"logs": [{**logs[0], "id": prefix + "late", "severity": "ERROR"}]})
            assert first == EvidenceBundle.model_validate(client.get(path + "/evidence").json())
            for suffix in ("evidence", "timeline", "signals"):
                denied = client.get(
                    path + "/" + suffix,
                    params={"service": "gateway"},
                    headers={"X-Request-ID": "scope-denial"},
                )
                assert denied.status_code == 403
                assert denied.json()["error"]["code"] == "SCOPE_POLICY_DENIED"
                assert (
                    denied.json()["error"]["request_id"]
                    == denied.headers["x-request-id"]
                    == "scope-denial"
                )
            denied = client.get(
                path + "/evidence",
                params={"start_time": (stamp - timedelta(seconds=1)).isoformat()},
            )
            assert denied.status_code == 403
            narrow = client.get(
                path + "/evidence",
                params={"start_time": (stamp + timedelta(seconds=55)).isoformat()},
            )
            assert narrow.status_code == 200 and len(narrow.json()["items"]) == 5
            assert narrow.json()["truncated"] is False
        with admin(lab) as db:
            assert (
                db.execute(
                    "SELECT count(*) FROM scope_denials WHERE incident_id=%s", (current.id,)
                ).fetchone()[0]
                == 4
            )
            for table in ("evidence", "evidence_bundles"):
                with pytest.raises(psycopg.errors.RaiseException, match="immutable"):
                    db.execute(f"DELETE FROM {table} WHERE incident_id=%s", (current.id,))
                with pytest.raises(psycopg.errors.RaiseException, match="immutable"):
                    db.execute(f"TRUNCATE {table}")
            with pytest.raises(psycopg.errors.RaiseException, match="immutable"):
                db.execute(
                    "UPDATE evidence SET summary='rewrite' WHERE incident_id=%s", (current.id,)
                )
        with lab.connect("investigator_ro") as db:
            for query in (
                "UPDATE evidence SET summary='x'",
                "DELETE FROM incidents",
                "INSERT INTO scope_denials(id) VALUES (gen_random_uuid())",
            ):
                with pytest.raises(
                    (psycopg.errors.InsufficientPrivilege, psycopg.errors.ReadOnlySqlTransaction)
                ):
                    db.execute(query)
    finally:
        store.engine.dispose()
        lab.close()


def test_ground_truth_unreachable_from_api_role_and_retrieval():
    lab = Lab()
    reader = EvidenceReader(url(lab, "investigator_ro"))
    statements = []
    event.listen(
        reader.engine,
        "before_cursor_execute",
        lambda conn, cursor, statement, params, ctx, many: statements.append(statement),
    )
    marker = "hidden-" + uuid4().hex
    try:
        with admin(lab) as db:
            db.execute("CREATE TABLE IF NOT EXISTS ground_truth.isolation_probe(label text)")
            db.execute("INSERT INTO ground_truth.isolation_probe(label) VALUES (%s)", (marker,))
        with httpx.Client(base_url=API, timeout=20) as client:
            current = create(
                client, datetime.now(UTC) - timedelta(seconds=5), datetime.now(UTC), "checkout-api"
            )
            path = f"/api/incidents/{current.id}"
            public = [
                client.get("/api/scenarios").json(),
                client.get(path).json(),
                client.get(path + "/evidence").json(),
                client.get(path + "/timeline").json(),
            ]
            assert all(set(item) == {"id", "name", "description"} for item in public[0])
            assert marker not in json.dumps(public)
            assert not any(
                key in json.dumps(public)
                for key in ("expected_root_cause", "injected_fault", "injection_ts")
            )
            for route in ("/api/ground_truth", "/api/scenarios/SCN-002", path + "/ground_truth"):
                assert client.get(route).status_code == 404
        bundle = reader.retrieve(current, ScopeRequest(incident_id=current.id))
        assert all(e.service == current.service for e in bundle.items)
        assert statements and all(
            "ground_truth" not in sql and "SELECT" in sql for sql in statements
        )
        assert sum("telemetry_" in sql for sql in statements) == 4
        with pytest.raises(ScopeDenied):
            reader.retrieve(
                current, ScopeRequest(incident_id=current.id, service="ground_truth.scenarios")
            )
        # A forged in-memory Incident cannot widen the stored boundary.
        forged = current.model_copy(update={"related_services": ("gateway",)})
        with pytest.raises(ScopeDenied):
            reader.retrieve(forged, ScopeRequest(incident_id=current.id, service="gateway"))
        with reader.engine.connect() as db:
            assert db.scalar(text("SELECT current_user")) == "investigator_ro"
            for table in ("scenarios", "chaos_runs", "isolation_probe"):
                with pytest.raises(ProgrammingError, match="permission denied"):
                    # Verify the exact privilege failure, not an arbitrary connection error.
                    db.execute(text(f"SELECT * FROM ground_truth.{table}"))
                db.rollback()
        with admin(lab) as db:
            assert not db.execute(
                "SELECT has_schema_privilege('telemetry_writer','ground_truth','USAGE')"
            ).fetchone()[0]
    finally:
        reader.engine.dispose()
        lab.close()


def test_live_incident_validation_and_error_request_ids():
    start = datetime.now(UTC)
    body = {
        "title": "Validation",
        "service": "checkout-api",
        "start_time": start.isoformat(),
        "end_time": (start + timedelta(minutes=1)).isoformat(),
        "symptom": "Errors",
    }
    with httpx.Client(base_url=API, timeout=10) as client:
        schema = client.get("/openapi.json").json()
        assert (
            schema["paths"]["/api/incidents"]["post"]["responses"]["422"]["content"][
                "application/json"
            ]["schema"]["$ref"]
            == "#/components/schemas/ErrorEnvelope"
        )
        assert "GroundTruth" not in schema["components"]["schemas"]
        for patch in (
            {"end_time": start.isoformat()},
            {"end_time": (start + timedelta(hours=6, seconds=1)).isoformat()},
            {"start_time": start.replace(tzinfo=None).isoformat()},
            {"service": "ground_truth"},
            {"title": " "},
            {"expected_root_cause": "not allowed"},
        ):
            response = client.post(
                "/api/incidents",
                json={**body, **patch},
                headers={"X-Request-ID": "validation-gate"},
            )
            assert response.status_code == 422
            assert response.json()["error"]["code"] == "VALIDATION_ERROR"
            assert (
                response.json()["error"]["request_id"]
                == response.headers["x-request-id"]
                == "validation-gate"
            )
        missing = client.get(f"/api/incidents/{uuid4()}")
        assert missing.status_code == 404 and missing.json()["error"]["code"] == "NOT_FOUND"
