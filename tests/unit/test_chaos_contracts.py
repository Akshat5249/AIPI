"""Scenario contracts and failure-path recovery guarantees."""

import json
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from chaos.scenarios import runner
from chaos.scenarios.contracts import ChaosError, ScenarioSpec
from chaos.scenarios.lab import ROOT
from chaos.scenarios.scn_001_service_kill import SPEC
from chaos.scenarios.signals import die_then_start


def test_scenario_schema_and_extra_fields() -> None:
    assert json.loads((ROOT / "chaos/scenarios/scenario.schema.json").read_text()) == (
        ScenarioSpec.model_json_schema()
    )
    assert ScenarioSpec.model_validate(SPEC.model_dump()) == SPEC
    with pytest.raises(ValidationError):
        ScenarioSpec.model_validate({**SPEC.model_dump(), "unvalidated": True})
    with pytest.raises(ValidationError):
        ScenarioSpec.model_validate({**SPEC.model_dump(), "target": "unrelated-production"})


@pytest.mark.parametrize(
    "events,expected",
    [
        ([{"event": "die", "exit_code": "137"}, {"event": "start"}], True),
        ([{"event": "start"}, {"event": "die", "exit_code": "137"}], False),
        ([{"event": "die", "exit_code": "0"}, {"event": "start"}], False),
    ],
)
def test_die_start_requires_order_and_sigkill(events, expected) -> None:
    assert die_then_start(events) == expected


@pytest.mark.parametrize("stage", ["preconditions", "inject", "recover", "verify"])
def test_failure_recovers_and_records_restricted_audit(monkeypatch, stage) -> None:
    lab = MagicMock()
    db = lab.connect.return_value.__enter__.return_value
    db.execute.return_value.fetchone.return_value = (True,)
    monkeypatch.setattr(runner, "Lab", lambda seed: lab)
    calls = []

    def step(name):
        def action(*args):
            calls.append(name)
            if stage == name:
                raise ChaosError("controlled failure")

        return action

    lab.preconditions.side_effect = step("preconditions")
    result = runner.run_scenario(SPEC, step("inject"), step("recover"), step("verify"))
    assert not result.passed
    assert ("recover" in calls) == (stage != "preconditions")
    assert result.recovery_status == (
        "not_needed" if stage == "preconditions" else "failed" if stage == "recover" else "verified"
    )
    if stage == "inject":
        assert "verify" not in calls
    lab.close.assert_called_once()
    audit_writes = [
        c.args[0] for c in db.execute.call_args_list if c.args[0].startswith(("INSERT", "UPDATE"))
    ]
    assert audit_writes and all("ground_truth." in sql for sql in audit_writes)
    assert SPEC.ground_truth.expected_root_cause not in result.model_dump_json()


def test_overlapping_run_never_injects(monkeypatch) -> None:
    lab = MagicMock()
    lab.connect.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = (
        False,
    )
    monkeypatch.setattr(runner, "Lab", lambda seed: lab)
    inject = MagicMock()
    with pytest.raises(ChaosError, match="Another chaos run"):
        runner.run_scenario(SPEC, inject, MagicMock(), MagicMock())
    inject.assert_not_called()
    lab.close.assert_called_once()


@pytest.mark.parametrize("status", [404, 200, 503])
def test_replica_pause_probes_every_new_order_and_requires_stale_reads(monkeypatch, status):
    from uuid import uuid4

    from aipi_demo.contracts import Order

    from chaos.scenarios import scn_002_replica_lag as scenario
    from chaos.scenarios.runner import Run

    lab = MagicMock()
    lab.create_order.side_effect = [
        Order(id=uuid4(), product="book", quantity=1) for _ in range(10)
    ]
    lab.client.get.return_value.status_code = status
    monkeypatch.setattr(
        scenario, "scalar", lambda db, sql: "paused" if "pause_state" in sql else True
    )
    monkeypatch.setattr(scenario.time, "sleep", lambda seconds: None)
    run = Run(id=uuid4(), spec=scenario.SPEC)
    if status == 404:
        scenario.inject(lab, run)
        assert lab.client.get.call_count == 10
        assert run.observations["stale_read_probes"] == 10
        assert all(run.observations["direct_primary_health_samples"])
    else:
        with pytest.raises(ChaosError, match="expected stale read"):
            scenario.inject(lab, run)
