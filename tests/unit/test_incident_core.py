"""Contracts, deeply immutable evidence, scope enforcement, and HTTP error envelopes."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

import pytest
from aipi_api.config import Settings
from aipi_api.incidents import MissingIncident
from aipi_api.main import create_app
from aipi_telemetry.evidence import Evidence, build_timeline, evidence_id
from aipi_tools.retrieval import SOURCES, EvidenceReader
from aipi_tools.scope import Incident, IncidentCreate, ScopeDenied, ScopePolicy, ScopeRequest
from fastapi.testclient import TestClient
from pydantic import ValidationError

START = datetime(2026, 10, 13, tzinfo=UTC)


def incident() -> Incident:
    return Incident(
        id=uuid4(),
        title="Errors",
        service="checkout-api",
        related_services=("gateway",),
        start_time=START,
        end_time=START + timedelta(minutes=5),
        symptom="5xx",
        created_at=START,
    )


def example(kind="log", ref="telemetry_logs:a", offset=0, payload=None):
    return Evidence(
        evidence_id=evidence_id(kind, ref),
        type=kind,
        service="checkout-api",
        timestamp=START + timedelta(seconds=offset),
        source_ref=ref,
        summary="Observation",
        payload=payload or {},
    )


@pytest.mark.parametrize("duration", [0, -1, 6 * 3600 + 1])
def test_invalid_incident_window(duration):
    body = incident().model_dump(exclude={"id", "status", "created_at"})
    body["end_time"] = START + timedelta(seconds=duration)
    with pytest.raises(ValidationError):
        IncidentCreate.model_validate(body)


def test_six_hour_boundary_and_timezone_validation():
    body = incident().model_dump(exclude={"id", "status", "created_at"})
    assert IncidentCreate.model_validate({**body, "end_time": START + timedelta(hours=6)})
    for change in (
        {"start_time": START.replace(tzinfo=None)},
        {"title": "  "},
        {"service": "unknown"},
    ):
        with pytest.raises(ValidationError):
            IncidentCreate.model_validate({**body, **change})


@pytest.mark.parametrize(
    "change",
    [
        {"service": "api"},
        {"start_time": START - timedelta(seconds=1)},
        {"end_time": START + timedelta(hours=1)},
        {"incident_id": uuid4()},
        {"start_time": START + timedelta(minutes=5)},
    ],
)
def test_scope_widening_denied_and_logged(change, caplog):
    current = incident()
    with pytest.raises(ScopeDenied):
        ScopePolicy().authorize(
            current, ScopeRequest.model_validate({"incident_id": current.id, **change})
        )
    assert "Scope widening denied" in caplog.text


def test_narrowing_and_equivalent_timezone_scope():
    current = incident()
    request = ScopeRequest(
        incident_id=current.id, service="gateway", start_time=START + timedelta(seconds=1)
    )
    scope = ScopePolicy().authorize(current, request)
    assert scope.services == ("gateway",) and scope.window.end_time == current.end_time
    all_services = ScopePolicy().authorize(current, ScopeRequest(incident_id=current.id))
    assert all_services.services == ("checkout-api", "gateway")


def test_evidence_identity_deep_immutability_and_timeline():
    payload = {"nested": {"list": [{"value": 1}]}}
    first = example(payload=payload)
    assert first.evidence_id == "ev_" + sha256(b"log|telemetry_logs:a").hexdigest()[:16]
    payload["nested"]["list"][0]["value"] = 9
    assert first.payload["nested"]["list"][0]["value"] == 1
    for mutate in (
        lambda: first.payload.update({"new": 1}),
        lambda: first.payload["nested"]["list"].append(2),
        lambda: first.payload["nested"]["list"][0].clear(),
    ):
        with pytest.raises(TypeError, match="immutable"):
            mutate()
    with pytest.raises(ValidationError):
        first.summary = "Changed"
    second = example(ref="telemetry_logs:b", offset=1)
    assert Evidence.model_validate_json(first.model_dump_json()) == first
    assert [t.evidence_ids for t in build_timeline((second, first))] == [
        (first.evidence_id,),
        (second.evidence_id,),
    ]
    with pytest.raises(ValidationError):
        Evidence.model_validate({**first.model_dump(), "evidence_id": "ev_invented"})


def test_reader_rejects_noninvestigator_and_has_only_telemetry_sources():
    for role in ("postgres", "chaos_admin", "telemetry_writer"):
        with pytest.raises(ValueError, match="investigator_ro"):
            EvidenceReader(f"postgresql+psycopg://{role}@127.0.0.1/aipi")
    assert {table.name for _, table in SOURCES} == {
        "telemetry_logs",
        "telemetry_metrics",
        "telemetry_spans",
        "telemetry_events",
    }
    reader = EvidenceReader("postgresql+psycopg://investigator_ro@127.0.0.1:1/aipi")
    # Denial precedes opening a DB connection, even when calling retrieval directly.
    with pytest.raises(ScopeDenied):
        reader.retrieve(incident(), ScopeRequest(incident_id=uuid4(), service="ground_truth"))
    reader.engine.dispose()


def test_api_error_contract_and_public_catalog(monkeypatch):
    app = create_app(
        Settings(
            _env_file=None,
            otel_enabled=False,
            database_url="postgresql+psycopg://investigator_ro@127.0.0.1:1/aipi",
            telemetry_database_url="postgresql+psycopg://telemetry_writer@127.0.0.1:1/aipi",
        )
    )

    schema = app.openapi()
    assert (
        schema["paths"]["/api/incidents"]["post"]["responses"]["422"]["content"][
            "application/json"
        ]["schema"]["$ref"]
        == "#/components/schemas/ErrorEnvelope"
    )

    def missing(*args):
        raise MissingIncident()

    monkeypatch.setattr(app.state.core, "get", missing)
    monkeypatch.setattr(app.state.investigator, "recover_interrupted", lambda: None)
    with TestClient(app) as client:
        for method, path, body, code in [
            ("POST", "/api/incidents", {}, "VALIDATION_ERROR"),
            ("GET", f"/api/incidents/{uuid4()}", None, "NOT_FOUND"),
            ("GET", "/api/incidents/not-a-uuid", None, "VALIDATION_ERROR"),
            (
                "GET",
                f"/api/incidents/{uuid4()}/evidence?start_time=2026-10-13T00:00:00",
                None,
                "VALIDATION_ERROR",
            ),
            ("GET", "/api/ground_truth", None, "NOT_FOUND"),
        ]:
            response = client.request(
                method, path, json=body, headers={"X-Request-ID": "test-request"}
            )
            assert response.json() == {
                "error": {
                    "code": code,
                    "message": response.json()["error"]["message"],
                    "retryable": False,
                    "request_id": "test-request",
                }
            }
            assert response.headers["x-request-id"] == "test-request"
        catalog = client.get("/api/scenarios").json()
        assert len(catalog) == 2 and all(
            set(item) == {"id", "name", "description"} for item in catalog
        )
        assert (
            client.get("/healthz", headers={"X-Request-ID": "bad value"}).headers["x-request-id"]
            != "bad value"
        )
