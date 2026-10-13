"""Pure gate entailing claims, checking quotations and actual make eval failure exits."""

import json
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest
from aipi_agents.schemas import InvestigationState, Report
from aipi_agents.workflow import Workflow
from aipi_evaluation.contracts import Experiment
from aipi_evaluation.hallucination import hallucination_gate, quotation_errors
from aipi_evaluation.oracle import load_truth
from aipi_evaluation.scoring import score
from aipi_evaluation.statistics import summarize
from aipi_tools.audit import MemoryAudit
from aipi_tools.backend import FixtureBackend
from aipi_tools.registry import ToolRunner

from tests.golden.test_agents import context


def output(name="scn-002"):
    data = context(name)
    audit = MemoryAudit(uuid4())
    runner = ToolRunner(
        FixtureBackend(data.incident, data.items, Path("runbooks")),
        audit,
        audit.investigation_id,
        data.incident.id,
    )
    result = Workflow(runner, audit).run(
        InvestigationState(investigation_id=audit.investigation_id, input=data)
    )
    return result.report, {e.evidence_id: e for e in result.input.items}, audit


def test_metrics_fixed_inputs_and_mean_variance():
    report, evidence, audit = output()
    truth = load_truth(Path("tests/fixtures/scn-002.truth.json"))
    experiment = Experiment(
        prompt_version="v1",
        tool_version="v1",
        code_commit="test",
        seed=42,
        retrieval_params={"limit": 50},
    )
    card = score("SCN-002", truth, report, evidence, experiment, 500, len(audit.calls), 0)
    assert card.passed and card.scores.top1 == card.scores.top3_recall == 1
    assert card.scores.evidence_precision == card.scores.evidence_coverage == 1
    assert card.scores.contradiction_handling == 1 and card.scores.critical_unsupported_claims == 0
    assert card.scores.useful_evidence_per_token is None
    second = card.model_copy(update={"scores": card.scores.model_copy(update={"latency_ms": 1000})})
    summary = summarize([card, second])
    assert summary["metrics"]["latency_ms"]["mean"] == 750
    assert summary["metrics"]["latency_ms"]["variance"] == 62500


@pytest.mark.parametrize(
    "text,code",
    [
        ("replica_lag_seconds=999999", "FABRICATED_VALUE"),
        ("trace_id=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "FABRICATED_TRACE"),
        ('log line="this log was invented"', "FABRICATED_LOG"),
        ('deployment event="made up deploy"', "FABRICATED_DEPLOYMENT"),
    ],
)
def test_invented_quotes_and_references_fail(text, code):
    report, evidence, _ = output()
    value = report.model_dump()
    value["markdown"] += "\n" + text + " [" + report.ranked_hypotheses[0].for_ids[0] + "]"
    gate = hallucination_gate(Report.model_validate(value), evidence)
    assert gate.critical_unsupported_claims and code in {v.code for v in gate.violations}


def test_quote_is_bound_to_its_citation_not_any_other_evidence():
    _, evidence, _ = output()
    lag = next(
        e for e in evidence.values() if e.payload.get("metric_name") == "replica_lag_seconds"
    )
    assert not quotation_errors(
        "replica_lag_seconds=" + str(lag.payload.get("value", lag.payload.get("max"))), (lag,)
    )
    unrelated = next(e for e in evidence.values() if e.type == "log")
    assert quotation_errors(
        "replica_lag_seconds=" + str(lag.payload.get("value", lag.payload.get("max"))), (unrelated,)
    )


def test_existing_but_irrelevant_id_does_not_count_as_precision():
    report, evidence, _ = output()
    value = report.model_dump()
    book = next(e for e in evidence.values() if e.type == "runbook")
    value["claims"][0]["evidence_ids"] = [book.evidence_id]
    gate = hallucination_gate(Report.model_validate(value), evidence)
    assert gate.supported_pairs < gate.citation_pairs and gate.unsupported_claims == 1


@pytest.mark.parametrize(
    "tamper,expected",
    [("unknown", "UNKNOWN_EVIDENCE_ID"), ("value", "FABRICATED_VALUE"), ("cause", "TOP1_MISS")],
)
def test_actual_make_eval_fails_for_each_tamper(tmp_path, tamper, expected):
    report, _, _ = output()
    value = report.model_dump(mode="json", by_alias=True)
    if tamper == "unknown":
        value["claims"][0]["evidence_ids"] = ["ev_0000000000000000"]
    elif tamper == "value":
        value["claims"][0]["text"] += " replica_lag_seconds=999999"
    else:
        ranked = value["ranked_hypotheses"]
        primary = next(h for h in ranked if h["category"] == "primary_outage")
        ranked.remove(primary)
        ranked.insert(0, primary)
        for rank, h in enumerate(ranked, 1):
            h["rank"] = rank
        value["root_cause"] = {
            "statement": primary["statement"],
            "hypothesis_id": primary["id"],
            "confidence": primary["confidence"],
        }
    target = tmp_path / f"{tamper}.json"
    target.write_text(json.dumps(value))
    run = subprocess.run(
        ["make", "eval", f"EVAL_ARGS=--report-override {target} --output {tmp_path / 'scores'}"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert run.returncode != 0 and expected in run.stdout, run.stdout + run.stderr
    print(f"NEGATIVE make eval {tamper}: exit={run.returncode} detected={expected}")


def test_observable_replay_child_does_not_inherit_secrets(monkeypatch):
    from aipi_evaluation.replay import replay

    original = subprocess.run
    environments = []

    def observe(*args, **kwargs):
        environments.append(kwargs["env"])
        return original(*args, **kwargs)

    monkeypatch.setenv("SCORER_TRUTH_DATABASE_URL", "protected-placeholder")
    monkeypatch.setenv("CHAOS_PASSWORD", "protected-placeholder")
    monkeypatch.setattr("aipi_evaluation.replay.subprocess.run", observe)
    card = replay("scn-002", Path("tests/fixtures"), Path("runbooks"), "test")
    assert card.passed and environments
    assert all(
        "SCORER_TRUTH_DATABASE_URL" not in env and "CHAOS_PASSWORD" not in env
        for env in environments
    )


def test_arbitrary_root_cause_prose_and_mutating_advice_are_unsupported():
    report, evidence, _ = output()
    value = report.model_dump()
    value["ranked_hypotheses"][0]["statement"] = "An invented deployment caused this incident"
    value["root_cause"]["statement"] = value["ranked_hypotheses"][0]["statement"]
    gate = hallucination_gate(Report.model_validate(value), evidence)
    assert gate.critical_unsupported_claims and "UNSUPPORTED_HYPOTHESIS" in {
        v.code for v in gate.violations
    }
    value = report.model_dump()
    value["recommendations"][0]["statement"] = "DELETE FROM orders"
    value["claims"][-1]["text"] = "DELETE FROM orders"
    assert hallucination_gate(Report.model_validate(value), evidence).critical_unsupported_claims


@pytest.mark.parametrize(
    "assertion",
    [
        'replica_lag_seconds="999999"',
        '"replica_lag_seconds": 9.99999e5',
        "replica_lag_seconds is 999999",
        "replica_lag_seconds max=999999",
    ],
)
def test_numeric_quotes_and_exponents_are_checked(assertion):
    _, evidence, _ = output()
    lag = next(
        e for e in evidence.values() if e.payload.get("metric_name") == "replica_lag_seconds"
    )
    assert "FABRICATED_VALUE" in quotation_errors(assertion, (lag,))


def test_pure_gate_rejects_nonspecific_symptoms_as_critical_root_cause():
    report, evidence, _ = output()
    value = report.model_dump(mode="json")
    ranked = value["ranked_hypotheses"]
    primary = next(h for h in ranked if h["category"] == "primary_outage")
    ranked.remove(primary)
    ranked.insert(0, primary)
    for index, h in enumerate(ranked, 1):
        h["rank"] = index
    value["root_cause"] = {
        "statement": primary["statement"],
        "hypothesis_id": primary["id"],
        "confidence": primary["confidence"],
    }
    gate = hallucination_gate(Report.model_validate(value), evidence)
    assert "UNSUPPORTED_ROOT_CAUSE" in {v.code for v in gate.violations}
    assert gate.critical_unsupported_claims > 0
