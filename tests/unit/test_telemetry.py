"""Adversarial parser, redaction and ingest tests without Docker."""

import json
from copy import deepcopy

import pytest
from aipi_api.config import Settings
from aipi_api.main import create_app
from aipi_telemetry.otlp import normalize, ts
from aipi_telemetry.redaction import redact
from fastapi.testclient import TestClient
from pydantic import ValidationError

NANO = "1791849600123456789"
TRACE = "1" * 32
SPAN = "2" * 16


def logs_payload(body="order created"):
    return {
        "resourceLogs": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "checkout-api"}}
                    ]
                },
                "scopeLogs": [
                    {
                        "logRecords": [
                            {
                                "timeUnixNano": NANO,
                                "severityText": "INFO",
                                "body": {"stringValue": body},
                                "traceId": TRACE,
                                "spanId": SPAN,
                                "attributes": [
                                    {"key": "password", "value": {"stringValue": "hidden-value"}}
                                ],
                            }
                        ]
                    }
                ],
            }
        ]
    }


def test_recursive_redaction():
    clean, markers = redact(
        {
            "api_key": "hidden-key",
            "nested": [
                "Bearer hidden-bearer",
                "user@example.com",
                "postgresql://me:hidden-pass@db/aipi",
                "AKIA"
                + "ABCDEFGHIJKLMNOP",  # Construct a synthetic pattern; never a real credential.
                "password=hidden-assignment",
            ],
        }
    )
    serialized = json.dumps(clean)
    assert "hidden" not in serialized and "user@example.com" not in serialized
    assert "postgresql://[REDACTED]@db/aipi" in serialized
    assert len(markers) == 6 and all(set(m) == {"field", "rule"} for m in markers)
    assert "hidden" not in json.dumps(markers)
    assert redact("user@example.com", emails=False) == ("user@example.com", [])


def test_normalizes_and_redacts_otlp_attribute_without_mutation():
    payload = logs_payload("Bearer body-secret")
    original = deepcopy(payload)
    row = normalize("logs", payload)["logs"][0]
    assert row["trace_id"] == TRACE and row["span_id"] == SPAN
    assert row["service"] == "checkout-api"
    assert "hidden-value" not in json.dumps(row, default=str)
    assert row["attributes_json"]["password"] == "[REDACTED]"
    assert row["ts"].microsecond == 123456
    assert row["id"] == normalize("logs", payload)["logs"][0]["id"]
    assert payload == original


@pytest.mark.parametrize("bad", ["abc", "0" * 31, "z" * 32])
def test_rejects_invalid_trace_id(bad):
    payload = logs_payload()
    payload["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]["traceId"] = bad
    with pytest.raises(ValidationError):
        normalize("logs", payload)


def test_missing_service_negative_time_and_wrong_signal():
    with pytest.raises(ValueError, match="service.name"):
        normalize("logs", {"resourceLogs": [{"scopeLogs": []}]})
    payload = logs_payload()
    payload["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]["timeUnixNano"] = "-1"
    with pytest.raises(ValidationError):
        normalize("logs", payload)
    with pytest.raises(ValueError, match="Missing resourceLogs"):
        normalize("logs", {"resourceSpans": []})


def test_runtime_events():
    payload = logs_payload()
    record = payload["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]
    record["attributes"] = [
        {"key": key, "value": {"stringValue": value}}
        for key, value in [
            ("event.domain", "runtime"),
            ("event.name", "die"),
            ("container.name", "checkout-api"),
        ]
    ]
    result = normalize("logs", payload)
    assert result["events"][0]["event_name"] == "die"
    assert "scenario" not in json.dumps(result, default=str)


def test_histogram_and_zero_gauge():
    payload = {
        "resourceMetrics": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "checkout-api"}}
                    ]
                },
                "scopeMetrics": [
                    {
                        "metrics": [
                            {
                                "name": "zero",
                                "gauge": {"dataPoints": [{"timeUnixNano": NANO, "asInt": "0"}]},
                            },
                            {
                                "name": "latency",
                                "histogram": {
                                    "dataPoints": [
                                        {
                                            "timeUnixNano": NANO,
                                            "sum": 10,
                                            "count": "2",
                                            "explicitBounds": [5],
                                            "bucketCounts": [1, 1],
                                        }
                                    ]
                                },
                            },
                        ]
                    }
                ],
            }
        ]
    }
    rows = normalize("metrics", payload)["metrics"]
    assert [(r["metric_name"], r["value"]) for r in rows] == [
        ("zero", 0),
        ("latency.sum", 10),
        ("latency.count", 2),
    ]
    assert rows[1]["labels_json"]["histogram"]["bucketCounts"] == [1, 1]


def test_span_duration_and_redaction():
    span = {
        "traceId": TRACE,
        "spanId": SPAN,
        "name": "query",
        "startTimeUnixNano": NANO,
        "endTimeUnixNano": str(int(NANO) + 2_000_000),
        "status": {"code": 2, "message": "Bearer status-secret"},
    }
    payload = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "checkout-api"}}
                    ]
                },
                "scopeSpans": [{"spans": [span]}],
            }
        ]
    }
    row = normalize("traces", payload)["traces"][0]
    assert row["duration_ms"] == 2 and "status-secret" not in json.dumps(row, default=str)
    span["endTimeUnixNano"] = str(int(NANO) - 1)
    with pytest.raises(ValidationError):
        normalize("traces", payload)
    assert ts(1_999_999_999).microsecond == 999999


def test_settings_hide_credentials_and_validate_provider(monkeypatch):
    monkeypatch.delenv("MODEL_PROVIDER", raising=False)
    config = Settings(
        _env_file=None,
        database_url="postgresql://secret-one",
        telemetry_database_url="postgresql://secret-two",
        model_api_key="hidden-key",
    )
    assert "hidden-key" not in repr(config) and "secret-one" not in repr(config)
    assert config.model_provider == "mock"
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None, database_url="x", telemetry_database_url="y", model_provider="invalid"
        )


def test_whole_batch_is_validated_before_storage(monkeypatch):
    app = create_app(
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://investigator_ro@127.0.0.1:1/aipi",
            telemetry_database_url="postgresql+psycopg://telemetry_writer@127.0.0.1:1/aipi",
            otel_enabled=False,
        )
    )
    saved = []
    monkeypatch.setattr(app.state.store, "persist", lambda rows: saved.append(rows))
    monkeypatch.setattr(app.state.investigator, "recover_interrupted", lambda: None)
    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200
        assert client.post("/internal/otlp/v1/logs", json=logs_payload()).json() == {}
        assert len(saved) == 1 and "hidden-value" not in json.dumps(saved, default=str)
        payload = logs_payload()
        invalid = deepcopy(payload["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0])
        invalid["traceId"] = "bad-secret"
        payload["resourceLogs"][0]["scopeLogs"][0]["logRecords"].append(invalid)
        result = client.post("/internal/otlp/v1/logs", json=payload)
        assert result.status_code == 400 and "bad-secret" not in result.text
        assert len(saved) == 1
        assert client.get("/readyz").status_code == 503


def test_quoted_secret_assignments_and_nested_otlp_values():
    text = """{"password": "a secret with spaces", "api_key":"private-key"}"""
    clean, markers = redact(text)
    assert "a secret with spaces" not in clean and "private-key" not in clean
    assert len(markers) == 1  # One marker per field/rule, even for multiple matches.
    nested = {
        "kvlistValue": {"values": [{"key": "secret", "value": {"stringValue": "nested-secret"}}]}
    }
    clean, markers = redact(nested)
    assert "nested-secret" not in json.dumps(clean) and markers


def test_empty_or_ambiguous_numeric_points_rejected():
    payload = {
        "resourceMetrics": [
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "probe"}}]
                },
                "scopeMetrics": [
                    {
                        "metrics": [
                            {"name": "lag", "gauge": {"dataPoints": [{"timeUnixNano": NANO}]}}
                        ]
                    }
                ],
            }
        ]
    }
    with pytest.raises(ValueError, match="exactly one scalar"):
        normalize("metrics", payload)
    point = payload["resourceMetrics"][0]["scopeMetrics"][0]["metrics"][0]["gauge"]["dataPoints"][0]
    point.update(asInt=1, asDouble=2)
    with pytest.raises(ValueError, match="exactly one scalar"):
        normalize("metrics", payload)


def test_external_runtime_events_are_schema_validated():
    from aipi_demo.contracts import DockerEvent

    event = {
        "Type": "container",
        "Action": "die",
        "timeNano": int(NANO),
        "Actor": {"ID": "container-id", "Attributes": {"exitCode": "137"}},
    }
    assert DockerEvent.model_validate(event).actor.attributes["exitCode"] == "137"
    event["Action"] = "exec_start"
    with pytest.raises(ValidationError):
        DockerEvent.model_validate(event)
