"""Old decisive telemetry survives a crowded window without hidden-label ranking."""

import re
from datetime import UTC, datetime, timedelta
from itertools import permutations
from pathlib import Path

import pytest
from aipi_telemetry.evidence import Evidence, evidence_id
from aipi_tools.ranking import rank_candidates, relevance, select_ranked

STAMP = datetime(2026, 10, 13, tzinfo=UTC)


def item(kind, reference, offset, payload, service="checkout-api"):
    return Evidence(
        evidence_id=evidence_id(kind, reference),
        type=kind,
        service=service,
        timestamp=STAMP + timedelta(seconds=offset),
        source_ref=reference,
        summary="synthetic",
        payload=payload,
    )


def test_oldest_decisive_items_survive_more_than_fifty_and_replay_identically():
    decisive = (
        item(
            "event",
            "telemetry_events:die",
            0,
            {"event_name": "die", "attributes_json": {"exit_code": "137"}},
        ),
        item("event", "telemetry_events:start", 0, {"event_name": "start"}),
        item(
            "metric",
            "telemetry_metrics:lag",
            0,
            {"metric_name": "replica_lag_seconds", "value": 8},
            "pg-lag-probe",
        ),
        item(
            "metric",
            "telemetry_metrics:paused",
            0,
            {"metric_name": "replica_replay_paused", "value": 1},
            "pg-lag-probe",
        ),
    )
    noise = tuple(
        item("log", f"telemetry_logs:{i:03}", i + 1, {"severity": "INFO"}) for i in range(100)
    )
    chosen = select_ranked(rank_candidates(noise + decisive))
    assert len(chosen) == 50
    assert set(e.evidence_id for e in decisive) <= {e.evidence_id for e in chosen}
    assert chosen[:4] == decisive
    assert chosen == select_ranked(rank_candidates(tuple(reversed(noise + decisive))))
    assert [e.evidence_id for e in chosen] == [
        e.evidence_id for e in select_ranked(rank_candidates(noise + decisive))
    ]


def test_relevance_then_timestamp_then_source_reference_not_evidence_id():
    examples = (
        item("log", "telemetry_logs:a", 1, {"severity": "INFO"}),
        item("log", "telemetry_logs:z", 0, {"severity": "INFO"}),
        item("log", "telemetry_logs:b", 1, {"severity": "INFO"}),
        item("log", "telemetry_logs:error", 9, {"severity": "ERROR"}),
    )
    expected = (examples[3], examples[1], examples[0], examples[2])
    for order in permutations(examples):
        assert select_ranked(rank_candidates(order)) == expected


def test_values_status_and_hidden_labels_never_affect_rank():
    first = item(
        "metric", "telemetry_metrics:a", 0, {"metric_name": "replica_lag_seconds", "value": 0}
    )
    changed = first.model_copy(
        update={
            "payload": {
                "metric_name": "replica_lag_seconds",
                "value": 999,
                "scenario_id": "never-rank-this",
                "expected_root_cause": "untrusted label",
            }
        }
    )
    assert relevance(first) == relevance(changed) == 1
    trace = item("trace", "telemetry_spans:a:b", 0, {"trace_id": "a", "status": "2"})
    assert relevance(trace) == relevance(trace.model_copy(update={"payload": {"status": "0"}})) == 3
    error = item("log", "telemetry_logs:error", 1, {"trace_id": "a", "severity": "ERROR"})
    assert [rank for rank, _ in rank_candidates((trace, error))] == [2, 2]
    with pytest.raises(ValueError):
        select_ranked(rank_candidates((first,)), limit=51)


def test_progress_table_and_recorded_decisions_are_complete():
    decisions = Path("docs/DECISIONS.md").read_text()
    defined = set(re.findall(r"^(?:- |## )ADR-(\d{3})[: —]", decisions, re.MULTILINE))
    assert {f"{number:03}" for number in range(7, 16)} <= defined
    progress = Path("PROGRESS.md").read_text()
    assert "`60790a4`" in next(line for line in progress.splitlines() if line.startswith("| M3 |"))
    table = progress.split("## 4. DECISIONS AND DEVIATIONS", 1)[1].split("---\n\n## 5.", 1)[0]
    rows = [line for line in table.splitlines() if line.startswith("|")]
    assert all(len(line.split("|")) == 7 for line in rows)
    assert "ADR-013 |\n| 4" in table
