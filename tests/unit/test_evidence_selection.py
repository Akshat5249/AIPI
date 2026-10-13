"""Full-scope correlation is invariant to capped presentation, including adverse windows."""

from datetime import timedelta
from uuid import uuid4

from aipi_tools.correlators import correlate
from aipi_tools.metric_summaries import summarize_metrics
from aipi_tools.ranking import rank_candidates, select_ranked
from aipi_tools.retrieval import build_snapshot
from aipi_tools.scope import Incident, ScopePolicy, ScopeRequest

from tests.unit.test_evidence_ranking import STAMP, item


def boundary():
    incident = Incident(
        id=uuid4(),
        title="Synthetic",
        service="checkout-api",
        related_services=("gateway", "pg-lag-probe"),
        symptom="Failures",
        start_time=STAMP,
        end_time=STAMP + timedelta(hours=1),
        created_at=STAMP,
    )
    return incident, ScopePolicy().authorize(incident, ScopeRequest(incident_id=incident.id))


def test_oldest_decisive_series_summarize_with_floors_and_identical_rules():
    raw = [
        item("event", "telemetry_events:die", 0, {"event_name": "die"}),
        item("event", "telemetry_events:start", 1, {"event_name": "start"}),
    ]
    for name, values, labels in (
        ("replica_lag_seconds", [0, 9, 0], {}),
        ("replica_lag_bytes", [0, 100, 0], {}),
        ("replica_replay_paused", [0, 1, 0], {}),
        ("primary_healthy", [1, 1, 1], {}),
        ("requests_total", [0, 4, 4], {"status": "503"}),
        ("error_rate", [1, 4, 5], {}),
    ):
        for i, value in enumerate(values):
            raw.append(
                item(
                    "metric",
                    f"telemetry_metrics:{name}:{i}",
                    i,
                    {"metric_name": name, "value": value, "labels_json": labels},
                )
            )
    raw += [
        item(
            "log",
            f"telemetry_logs:warning:{i:03}",
            i,
            {"severity": "WARN", "body": "stale replica read", "error.type": "ReplicaReadTimeout"},
            "gateway",
        )
        for i in range(12)
    ]
    raw += [
        item("trace", f"telemetry_spans:error:{i:03}", i, {"status": "2", "duration_ms": 500})
        for i in range(8)
    ]
    # A long series compresses to one item rather than consuming the cap.
    raw += [
        item(
            "metric",
            f"telemetry_metrics:noise:{i:03}",
            i + 10,
            {"metric_name": "ordinary", "value": i},
        )
        for i in range(100)
    ]
    raw += [
        item("log", f"telemetry_logs:info:{i:03}", i + 20, {"severity": "INFO"}) for i in range(100)
    ]
    incident, scope = boundary()
    before = correlate(tuple(raw))
    snapshot = build_snapshot(incident, scope, tuple(raw))
    bundle = snapshot.bundle
    assert len(bundle.items) == 50 and bundle.truncated
    assert {s.rule for s in before} == {s.rule for s in bundle.signals} == set(bundle.capped_rules)
    assert (
        len([e for e in bundle.items if e.type == "log" and e.payload.get("severity") == "WARN"])
        >= 10
    )
    assert len([e for e in bundle.items if e.type == "trace"]) >= 5
    assert bundle.raw_counts.metric == 118 and bundle.available_counts.metric == 7
    again = build_snapshot(incident, scope, tuple(reversed(raw)))
    assert [e.evidence_id for e in bundle.items] == [e.evidence_id for e in again.bundle.items]
    assert bundle.signals == again.bundle.signals
    assert {eid for s in bundle.signals for eid in s.evidence_ids} <= {
        e.evidence_id for e in snapshot.witnesses
    }
    summaries = {e.payload["metric_name"]: e for e in bundle.items if e.type == "metric"}
    paused = summaries["replica_replay_paused"].payload
    assert (
        paused["first"],
        paused["last"],
        paused["min"],
        paused["max"],
        paused["sample_count"],
    ) == (0, 0, 0, 1, 3)
    assert [(t["from"], t["to"]) for t in paused["transitions"]] == [(0, 1), (1, 0)]
    assert summaries["primary_healthy"].payload["transitions"] == []


def test_full_scope_keeps_rule_when_floor_cannot_keep_its_witness():
    # All 50 earlier ERROR logs precede the only timeout log. Full correlation must still fire.
    raw = tuple(item("log", f"telemetry_logs:{i:03}", i, {"severity": "ERROR"}) for i in range(60))
    raw += (
        item(
            "log", "telemetry_logs:timeout", 90, {"severity": "WARN", "error.type": "ReadTimeout"}
        ),
    )
    incident, scope = boundary()
    snapshot = build_snapshot(incident, scope, raw)
    assert not correlate(snapshot.bundle.items)
    assert {s.rule for s in snapshot.bundle.signals} == {"DownstreamTimeoutRule"}
    assert snapshot.bundle.signals == correlate(raw)
    assert snapshot.witnesses == raw[-1:]


def test_summary_series_separation_conflicting_health_and_source_version():
    raw = (
        item("metric", "telemetry_metrics:a", 0, {"metric_name": "primary_healthy", "value": 1}),
        item("metric", "telemetry_metrics:b", 1, {"metric_name": "primary_healthy", "value": 0}),
        item(
            "metric",
            "telemetry_metrics:c",
            2,
            {"metric_name": "primary_healthy", "value": 1, "labels_json": {"node": "other"}},
        ),
    )
    summary = summarize_metrics(raw)
    assert len(summary) == 2
    assert not correlate(raw) and not correlate(summary)
    assert summarize_metrics(raw[::-1]) == summary
    assert summary[0].evidence_id != summarize_metrics(raw[:1])[0].evidence_id


def test_overflow_protected_types_respects_floors_and_cap():
    raw = tuple(
        item("event", f"telemetry_events:{i:03}", i, {"event_name": "die"}) for i in range(60)
    )
    raw += tuple(item("log", f"telemetry_logs:{i:03}", i, {"severity": "ERROR"}) for i in range(10))
    raw += tuple(item("trace", f"telemetry_spans:{i:03}", i, {"status": "2"}) for i in range(5))
    chosen = select_ranked(rank_candidates(raw))
    assert len(chosen) == 50
    assert sum(e.type == "event" for e in chosen) == 35
    assert sum(e.type == "log" for e in chosen) == 10
    assert sum(e.type == "trace" for e in chosen) == 5


def test_histogram_payload_is_sample_data_not_a_series_dimension():
    samples = tuple(
        item(
            "metric",
            f"telemetry_metrics:hist:{i}",
            i,
            {
                "metric_name": "request_duration_ms.sum",
                "value": i + 1,
                "labels_json": {
                    "route": "/orders",
                    "histogram": {"count": i + 1, "timeUnixNano": str(i), "bucketCounts": [i, 1]},
                },
            },
        )
        for i in range(100)
    )
    summaries = summarize_metrics(samples)
    assert len(summaries) == 1 and summaries[0].payload["sample_count"] == 100
    assert summaries[0].payload["labels_json"] == {"route": "/orders"}
    assert summaries[0].payload["first"] == 1 and summaries[0].payload["last"] == 100
    assert summaries == summarize_metrics(samples[::-1])
