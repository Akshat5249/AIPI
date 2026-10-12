"""Live foundation gate: gateway → checkout → PG → Collector → ingested rows."""

import json
import time
from uuid import uuid4

import httpx
import psycopg
import pytest
from dotenv import dotenv_values

pytestmark = pytest.mark.docker


def connect(role: str = "investigator_ro", *, replica: bool = False) -> psycopg.Connection:
    env = dotenv_values(".env")
    key = {
        "investigator_ro": "INVESTIGATOR_PASSWORD",
        "postgres": "POSTGRES_PASSWORD",
        "telemetry_writer": "TELEMETRY_WRITER_PASSWORD",
    }[role]
    try:
        return psycopg.connect(
            host="127.0.0.1",
            port=5433 if replica else 5432,
            dbname="aipi",
            user=role,
            password=env[key],
            autocommit=True,
            connect_timeout=5,
        )
    except psycopg.Error as exc:
        # Suppress driver traceback locals, which include the connection password.
        pytest.fail(f"Lab database unavailable ({type(exc).__name__}); run make up", pytrace=False)


def eventually(check, timeout: float = 25):
    deadline = time.monotonic() + timeout
    while True:
        result = check()
        if result:
            return result
        assert time.monotonic() < deadline, "Expected telemetry or replica row did not arrive"
        time.sleep(0.5)


def test_request_has_correlated_trace_log_metric_and_replica_read() -> None:
    product = "gate-" + uuid4().hex[:8]
    response = httpx.post(
        "http://localhost:8080/checkout", json={"product": product, "quantity": 2}
    )
    assert response.status_code == 200, response.text
    order = response.json()
    with connect() as db:

        def find_trace():
            return db.execute(
                "SELECT trace_id FROM telemetry_logs WHERE service='checkout-api' "
                "AND attributes_json->>'order.id'=%s",
                (order["id"],),
            ).fetchone()

        trace_id = eventually(find_trace)[0]
        assert trace_id and trace_id != "0" * 32

        def correlated():
            return (
                db.execute(
                    "SELECT count(DISTINCT service) FROM telemetry_spans WHERE trace_id=%s "
                    "AND service IN ('gateway','checkout-api')",
                    (trace_id,),
                ).fetchone()[0]
                == 2
            )

        eventually(correlated)
        eventually(
            lambda: db.execute(
                "SELECT count(*) FROM telemetry_spans WHERE trace_id=%s "
                "AND operation='postgres.insert_order'",
                (trace_id,),
            ).fetchone()[0]
        )
        eventually(
            lambda: db.execute(
                "SELECT count(*) FROM telemetry_metrics WHERE service='checkout-api' "
                "AND metric_name='requests_total' AND value>=1"
            ).fetchone()[0]
        )
        eventually(
            lambda: db.execute(
                "SELECT count(*) FROM telemetry_metrics WHERE service='pg-lag-probe' "
                "AND metric_name='primary_healthy' AND value=1"
            ).fetchone()[0]
        )
    eventually(lambda: httpx.get("http://localhost:8080/orders/" + order["id"]).status_code == 200)
    with connect(replica=True) as replica:
        assert replica.execute("SELECT pg_is_in_recovery()").fetchone()[0]


def test_roles_cannot_mutate_or_read_ground_truth() -> None:
    with connect("postgres") as admin:
        admin.execute("CREATE TABLE IF NOT EXISTS ground_truth.isolation_probe (label text)")
    for role in ("investigator_ro", "telemetry_writer"):
        with connect(role) as db:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                db.execute("SELECT * FROM ground_truth.isolation_probe")
            with pytest.raises(
                (psycopg.errors.InsufficientPrivilege, psycopg.errors.ReadOnlySqlTransaction)
            ):
                db.execute("DELETE FROM telemetry_logs WHERE false")
    with connect() as db:
        with pytest.raises(
            (psycopg.errors.InsufficientPrivilege, psycopg.errors.ReadOnlySqlTransaction)
        ):
            db.execute("INSERT INTO telemetry_events (id) VALUES ('denied')")


def test_ingestion_redacts_before_storage_and_retries_are_idempotent() -> None:
    unique = uuid4().hex
    payload = {
        "resourceLogs": [
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "gate-ingest"}}]
                },
                "scopeLogs": [
                    {
                        "logRecords": [
                            {
                                "timeUnixNano": str(time.time_ns()),
                                "body": {"stringValue": "Bearer private-secret"},
                                "attributes": [
                                    {"key": "test.id", "value": {"stringValue": unique}},
                                    {"key": "api_key", "value": {"stringValue": "private-key"}},
                                ],
                            }
                        ]
                    }
                ],
            }
        ]
    }
    for _ in range(2):
        response = httpx.post("http://localhost:4318/v1/logs", json=payload)
        assert response.status_code == 200, response.text
    with connect() as db:

        def read():
            return db.execute(
                "SELECT body, attributes_json, redactions FROM telemetry_logs "
                "WHERE service='gate-ingest' AND attributes_json->>'test.id'=%s",
                (unique,),
            ).fetchall()

        rows = eventually(read)
        time.sleep(2)  # Allow the retry batch to pass through Collector.
        rows = read()
        assert len(rows) == 1
        assert "private-secret" not in json.dumps(rows) and "private-key" not in json.dumps(rows)
        assert rows[0][1]["api_key"] == "[REDACTED]" and rows[0][2]


def test_runtime_watcher_events_preserve_target_and_original_timestamp() -> None:
    with connect() as db:

        def read():
            return db.execute(
                "SELECT service, ts, attributes_json FROM telemetry_events "
                "WHERE event_name='start' AND service IN ('gateway','traffic') "
                "ORDER BY ts DESC LIMIT 1"
            ).fetchone()

        service, timestamp, attributes = eventually(read)
        assert service == attributes["container.name"]
        assert attributes["service.name"] == "event-watcher"
        assert abs(timestamp.timestamp() - attributes["event.timestamp_ns"] / 1e9) < 0.001
