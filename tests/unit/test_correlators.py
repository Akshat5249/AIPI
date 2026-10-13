"""Positive, negative, contradictory and reproducible behavior for all five pure rules."""

from datetime import UTC, datetime, timedelta

import pytest
from aipi_telemetry.evidence import Evidence, evidence_id
from aipi_tools.correlators import (
    DownstreamTimeoutRule,
    ErrorSpikeRule,
    PrimaryHealthRule,
    ProcessExitRule,
    ReplicaLagRule,
    correlate,
)


def ev(kind, payload, offset=0):
    source = f"synthetic:{kind}:{offset}:{payload}"
    return Evidence(
        evidence_id=evidence_id(kind, source),
        type=kind,
        service="gateway",
        timestamp=datetime(2026, 10, 13, tzinfo=UTC) + timedelta(seconds=offset),
        source_ref=source,
        summary=str(payload),
        payload=payload,
    )


def gauge(name, number, offset=0):
    return ev("metric", {"metric_name": name, "value": number}, offset)


def test_process_exit_requires_all_three_observed_signals():
    items = (
        ev("event", {"event_name": "die"}),
        ev(
            "metric",
            {"metric_name": "requests_total", "value": 4, "labels_json": {"status": "503"}},
        ),
        ev("trace", {"status": "2"}),
    )
    assert ProcessExitRule.apply(items)[0].evidence_ids
    for omitted in range(3):
        assert not ProcessExitRule.apply(items[:omitted] + items[omitted + 1 :])


@pytest.mark.parametrize("name", ["error_rate", "latency_p95"])
def test_error_spike_uses_baseline_inside_scope(name):
    assert ErrorSpikeRule.apply((gauge(name, 1), gauge(name, 4, 1)))
    assert not ErrorSpikeRule.apply((gauge(name, 1), gauge(name, 1, 1)))
    assert not ErrorSpikeRule.apply((gauge(name, 4),))


def test_error_spike_failed_span_rate_baseline():
    samples = tuple(ev("trace", {"status": "0" if index < 2 else "2"}, index) for index in range(4))
    assert ErrorSpikeRule.apply(samples)
    assert not ErrorSpikeRule.apply(samples[::-1][:2])


def test_replica_lag_requires_backlog_pause_and_healthy_primary():
    items = (
        gauge("replica_lag_seconds", 5),
        gauge("replica_lag_bytes", 1000),
        gauge("replica_replay_paused", 1),
        gauge("primary_healthy", 1),
    )
    assert ReplicaLagRule.apply(items)
    for omitted in range(4):
        assert not ReplicaLagRule.apply(items[:omitted] + items[omitted + 1 :])
    assert not ReplicaLagRule.apply(items + (gauge("primary_healthy", 0, 1),))


def test_timeout_is_explicit_false_lead():
    for payload in ({"error.type": "ReadTimeout"}, {"body": "stale replica read"}):
        result = DownstreamTimeoutRule.apply((ev("log", payload),))
        assert result[0].kind == "false_lead"
    assert not DownstreamTimeoutRule.apply((ev("log", {"body": "healthy request"}),))


def test_primary_health_contradicts_outage_and_preserves_conflicting_samples():
    result = PrimaryHealthRule.apply((gauge("primary_healthy", 1),))
    assert result[0].stance == "against" and result[0].contradicts == "primary outage"
    assert not PrimaryHealthRule.apply(
        (gauge("primary_healthy", 1), gauge("primary_healthy", 0, 1))
    )
    assert not PrimaryHealthRule.apply(())


def test_correlators_are_deterministic_pure_and_cite_existing_ids():
    items = (
        gauge("replica_lag_seconds", 5),
        gauge("replica_lag_bytes", 1000),
        gauge("replica_replay_paused", 1),
        gauge("primary_healthy", 1),
    )
    before = [item.model_dump_json() for item in items]
    first = correlate(items)
    assert first == correlate(items) == correlate(tuple(reversed(items)))
    assert [item.model_dump_json() for item in items] == before
    assert all(set(result.evidence_ids) <= {item.evidence_id for item in items} for result in first)


def test_error_spike_does_not_compare_different_services_or_label_series():
    first = gauge("error_rate", 1)
    other_service = gauge("error_rate", 4, 1).model_copy(update={"service": "orders-api"})
    assert not ErrorSpikeRule.apply((first, other_service))
    other_route = ev(
        "metric",
        {"metric_name": "error_rate", "value": 4, "labels_json": {"route": "/different"}},
        1,
    )
    assert not ErrorSpikeRule.apply((first, other_route))


def test_error_spike_latency_compares_matching_operations():
    spans = tuple(
        ev("trace", {"status": "0", "operation": "read", "duration_ms": 2 if i < 2 else 300}, i)
        for i in range(4)
    )
    assert ErrorSpikeRule.apply(spans)
    mismatched = tuple(
        e.model_copy(update={"payload": {**e.payload, "operation": "write"}}) if i >= 2 else e
        for i, e in enumerate(spans)
    )
    assert not ErrorSpikeRule.apply(mismatched)


def test_error_spike_does_not_dilute_db_failures_with_successful_http():
    samples = tuple(
        ev(
            "trace",
            {
                "operation": "postgres.select_order",
                "status": "0" if i < 4 else "2",
                "duration_ms": 200,
            },
            i,
        )
        for i in range(8)
    )
    successful = tuple(
        ev("trace", {"operation": "GET /orders", "status": "0", "duration_ms": 200}, i)
        for i in range(30)
    )
    signals = ErrorSpikeRule.apply(samples + successful)
    assert signals and set(signals[0].evidence_ids) == {e.evidence_id for e in samples}
    assert not ErrorSpikeRule.apply(successful)
