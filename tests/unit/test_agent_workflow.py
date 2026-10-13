"""Graph repair, output isolation, empty retrieval and explicit observability tests."""

from pathlib import Path
from uuid import uuid4

import pytest
from aipi_agents.reporting import ReportValidationError
from aipi_agents.schemas import AgentInput, InvestigationState, cited_ids
from aipi_agents.workflow import Workflow
from aipi_tools.audit import MemoryAudit
from aipi_tools.backend import FixtureBackend
from aipi_tools.registry import ToolRunner
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from tests.golden.test_agents import context


def workflow(data, producer=None):
    audit = MemoryAudit(uuid4())
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("graph-test")
    runner = ToolRunner(
        FixtureBackend(data.incident, data.items, Path("runbooks")),
        audit,
        audit.investigation_id,
        data.incident.id,
        tracer,
    )
    graph = Workflow(runner, audit, tracer=tracer, producer=producer)
    state = InvestigationState(investigation_id=audit.investigation_id, input=data)
    return graph, state, audit, exporter


def test_graph_unknown_markdown_citation_repair_once():
    seen = []

    def producer(report, repair):
        seen.append(repair)
        value = report.model_dump()
        if not repair:
            value["markdown"] += " ev_0000000000000000"
        return value

    graph, state, audit, exporter = workflow(context("scn-001"), producer)
    result = graph.run(state)
    assert result.report and result.report_attempts == 2 and seen == [False, True]
    assert sum(e.kind == "report_repair" for e in audit.events) == 1
    spans = exporter.get_finished_spans()
    assert sum(s.name == "agent.Reporter" for s in spans) == 2
    root = next(s for s in spans if s.name == "investigation")
    assert all(s.context.trace_id == root.context.trace_id for s in spans)
    assert any(s.name.startswith("tool.") for s in spans)


def test_graph_invalid_report_fails_after_one_repair():
    seen = []

    def producer(report, repair):
        seen.append(repair)
        value = report.model_dump()
        value["timeline"][0]["evidence_ids"] = ["ev_unknown"]
        return value

    graph, state, audit, _ = workflow(context("scn-002"), producer)
    with pytest.raises(ReportValidationError, match="one repair"):
        graph.run(state)
    assert seen == [False, True] and audit.events[-1].kind == "node_failed"


def test_empty_retrieval_reports_insufficiency_without_scope_widening():
    data = context("scn-001")
    empty = AgentInput(incident=data.incident, items=(), signals=())
    graph, state, audit, _ = workflow(empty)
    result = graph.run(state)
    assert result.report.root_cause.confidence == 0
    assert result.report.ranked_hypotheses[0].category == "insufficient"
    assert not result.report.claims and not result.report.recommendations
    assert all(c.args_json["incident_id"] == str(data.incident.id) for c in audit.calls)
    assert cited_ids(result.report) <= set(result.evidence_ids)


def test_every_fact_preserves_full_correlator_witnesses():
    data = context("scn-002")
    graph, state, _, _ = workflow(data)
    report = graph.run(state).report
    for index, signal in enumerate(data.signals):
        fact = next(c for c in report.claims if c.claim_id == f"fact_{index}")
        assert set(fact.evidence_ids) == set(signal.evidence_ids)


@pytest.mark.parametrize("tamper", ["confidence", "recommendation"])
def test_reporter_cannot_override_deterministic_confidence_or_checks(tamper):
    attempts = []

    def producer(report, repair):
        attempts.append(repair)
        value = report.model_dump()
        if tamper == "confidence":
            value["ranked_hypotheses"][0]["confidence"] = 0.999
            value["root_cause"]["confidence"] = 0.999
        else:
            value["recommendations"][0]["statement"] = "Restart the service"
        return value

    graph, state, _, _ = workflow(context("scn-001"), producer)
    with pytest.raises(ReportValidationError, match="one repair"):
        graph.run(state)
    assert attempts == [False, True]
