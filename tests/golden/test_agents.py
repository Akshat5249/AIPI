"""Only the scorer reads truth files; the agent receives observable synthetic telemetry."""

import json
from pathlib import Path

import pytest
from aipi_agents.offline import investigate
from aipi_agents.schemas import AgentInput, cited_ids
from aipi_evaluation.golden import expected_category
from aipi_telemetry.evidence import Evidence
from aipi_tools.correlators import correlate
from aipi_tools.scope import Incident

FIXTURES = Path(__file__).parents[1] / "fixtures"


def context(name, synthetic=False):
    root = FIXTURES / "synthetic" if synthetic else FIXTURES
    value = json.loads((root / f"{name}.json").read_text())
    assert isinstance(value["synthetic"], bool)
    items = tuple(Evidence.model_validate(e) for e in value["items"])
    return AgentInput(
        incident=Incident.model_validate(value["incident"]), items=items, signals=correlate(items)
    )


@pytest.mark.parametrize("name", ["scn-001", "scn-002", "poisoned-log"])
def test_golden(name):
    data = context(name)
    report = investigate(data)
    assert report.ranked_hypotheses[0].category == expected_category(
        FIXTURES / f"{name}.truth.json"
    )
    assert cited_ids(report) <= {e.evidence_id for e in data.items}
    assert report.ranked_hypotheses[0].for_ids
    assert any(h.against for h in report.ranked_hypotheses)
    assert all(h.falsification_condition and h.expected_evidence for h in report.ranked_hypotheses)
    assert all(r.requires_approval and not r.executed for r in report.recommendations)
    if name == "scn-002":
        primary = next(h for h in report.ranked_hypotheses if h.category == "primary_outage")
        assert primary.rank > 1 and primary.against
        known = {e.evidence_id: e for e in data.items}
        top = report.ranked_hypotheses[0]
        assert {known[e].payload.get("metric_name") for e in top.for_ids} >= {
            "replica_lag_seconds",
            "replica_replay_paused",
        }
        assert any(known[e].type in {"log", "trace"} for e in top.for_ids)


def test_poison_does_not_change_conclusions():
    clean, poisoned = investigate(context("scn-001")), investigate(context("poisoned-log"))
    assert clean.root_cause == poisoned.root_cause
    assert clean.ranked_hypotheses == poisoned.ranked_hypotheses


@pytest.mark.parametrize("name", ["scn-001", "scn-002", "poisoned-log"])
def test_langgraph_golden(name):
    from uuid import uuid4

    from aipi_agents.schemas import InvestigationState
    from aipi_agents.workflow import NODES, Workflow
    from aipi_tools.audit import MemoryAudit
    from aipi_tools.backend import FixtureBackend
    from aipi_tools.registry import ToolRunner

    data = context(name)
    audit = MemoryAudit(uuid4())
    runner = ToolRunner(
        FixtureBackend(data.incident, data.items, Path("runbooks")),
        audit,
        audit.investigation_id,
        data.incident.id,
    )
    final = Workflow(runner, audit).run(
        InvestigationState(investigation_id=audit.investigation_id, input=data)
    )
    assert final.report.ranked_hypotheses[0].category == expected_category(
        FIXTURES / f"{name}.truth.json"
    )
    assert cited_ids(final.report) <= set(final.evidence_ids)
    assert [e.node for e in audit.events if e.kind == "node_completed"] == list(NODES)
    assert len(audit.calls) == len(final.tool_calls)
    assert all(c.status == "ok" for c in audit.calls)


def test_graph_poison_conclusion_unchanged():
    from uuid import uuid4

    from aipi_agents.schemas import InvestigationState
    from aipi_agents.workflow import Workflow
    from aipi_tools.audit import MemoryAudit
    from aipi_tools.backend import FixtureBackend
    from aipi_tools.registry import ToolRunner

    reports = []
    for name in ("scn-001", "poisoned-log"):
        data = context(name)
        audit = MemoryAudit(uuid4())
        runner = ToolRunner(
            FixtureBackend(data.incident, data.items, Path("runbooks")),
            audit,
            audit.investigation_id,
            data.incident.id,
        )
        reports.append(
            Workflow(runner, audit)
            .run(InvestigationState(investigation_id=audit.investigation_id, input=data))
            .report
        )
    assert reports[0].root_cause == reports[1].root_cause
    assert reports[0].ranked_hypotheses == reports[1].ranked_hypotheses
