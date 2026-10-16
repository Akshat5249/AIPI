"""Real SQL batch/idempotency/atomicity checks without requiring Docker."""

from datetime import UTC, datetime

import pytest
from aipi_telemetry.storage import TelemetryStore, logs, metadata
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError


def row(identifier, **extra):
    return {
        "id": identifier,
        "ts": datetime.now(UTC),
        "service": "api",
        "severity": "INFO",
        "body": "first",
        "attributes_json": {},
        "redactions": [],
        **extra,
    }


def test_bulk_writes_bound_round_trips_and_keep_first_observation():
    store = TelemetryStore("sqlite+pysqlite:///:memory:")
    metadata.create_all(store.engine)
    statements = []
    event.listen(
        store.engine,
        "before_cursor_execute",
        lambda conn, cursor, sql, params, context, many: statements.append(sql),
    )
    try:
        data = [row(str(i)) for i in range(1201)]
        assert store.persist({"logs": data}) == 1201
        assert len(statements) == 3  # 500 + 500 + 201, instead of 1201 writes.
        assert (
            store.persist(
                {
                    "logs": [
                        row("same"),
                        row("different", trace_id="a" * 32),
                        row("same", body="rewrite", trace_id=None),
                    ]
                }
            )
            == 2
        )
        assert store.persist({"logs": data}) == 0
        with store.engine.connect() as db:
            assert db.scalar(select(logs.c.body).where(logs.c.id == "same")) == "first"
    finally:
        store.engine.dispose()


def test_batch_failure_rolls_back_all_prior_chunks():
    store = TelemetryStore("sqlite+pysqlite:///:memory:")
    metadata.create_all(store.engine)
    try:
        with pytest.raises(IntegrityError):
            store.persist({"logs": [row(str(i)) for i in range(501)] + [row("bad", service=None)]})
        with store.engine.connect() as db:
            assert db.execute(select(logs.c.id)).fetchall() == []
    finally:
        store.engine.dispose()
