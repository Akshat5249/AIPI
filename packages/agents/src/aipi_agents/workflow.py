"""Inspectable six-node LangGraph with validated state and one report repair edge."""

import time
from collections.abc import Callable
from typing import Any

from aipi_tools.audit import AuditSink
from aipi_tools.contracts import (
    LogsInput,
    MetricInput,
    ReplicationInput,
    RunbookInput,
    RuntimeInput,
    ToolInput,
    ToolName,
    TraceInput,
)
from aipi_tools.registry import ToolRunner
from langchain_core.runnables import RunnableConfig, RunnableLambda
from langgraph.graph import END, START, StateGraph
from opentelemetry import trace
from pydantic import ValidationError

from aipi_agents.adapters import Adapter, MockAdapter
from aipi_agents.offline import propose
from aipi_agents.reasoning import rank, verify
from aipi_agents.reporting import ReportValidationError, template, validate_report
from aipi_agents.schemas import AgentInput, Hypothesis, InvestigationState, Proposal, Report

NODES = ("Triage", "Retriever", "Hypothesis", "Verifier", "Ranker", "Reporter")
ReportProducer = Callable[[Report, bool], object]


class Workflow:
    def __init__(
        self,
        runner: ToolRunner,
        audit: AuditSink,
        adapter: Adapter | None = None,
        tracer: trace.Tracer | None = None,
        producer: ReportProducer | None = None,
    ) -> None:
        self.runner = runner
        self.audit = audit
        self.adapter = adapter or MockAdapter()
        self.tracer = tracer or trace.get_tracer("aipi.agents")
        self.producer = producer
        graph = StateGraph(InvestigationState)
        for name, function in zip(
            NODES,
            (self.triage, self.retrieve, self.hypothesize, self.verify, self.rank, self.report),
            strict=True,
        ):
            graph.add_node(
                name, RunnableLambda(self.observed(name, function)), input_schema=InvestigationState
            )
        graph.add_edge(START, "Triage")
        for left, right in zip(NODES[:-1], NODES[1:], strict=True):
            graph.add_edge(left, right)
        graph.add_conditional_edges(
            "Reporter", self.report_route, {"repair": "Reporter", "done": END}
        )
        self.graph = graph.compile()

    def observed(
        self, name: str, function: Callable[[InvestigationState], dict[str, Any]]
    ) -> Callable[[InvestigationState], dict[str, Any]]:
        def node(state: InvestigationState) -> dict[str, Any]:
            state = InvestigationState.model_validate(state.model_dump())
            self.audit.emit("node_started", name, {})
            started = time.monotonic()
            with self.tracer.start_as_current_span("agent." + name):
                try:
                    changes = function(state)
                    validated = InvestigationState.model_validate({**state.model_dump(), **changes})
                    self.audit.emit(
                        "node_completed", name, {"latency_ms": (time.monotonic() - started) * 1000}
                    )
                    return {key: getattr(validated, key) for key in changes}
                except Exception:
                    self.audit.emit("node_failed", name, {"error": "NODE_FAILED"})
                    raise

        return node

    def run(self, state: InvestigationState) -> InvestigationState:
        with self.tracer.start_as_current_span("investigation") as span:
            span.set_attribute("incident.id", str(state.input.incident.id))
            span.set_attribute("investigation.id", str(state.investigation_id))
            config: RunnableConfig = {"recursion_limit": 12}
            result = self.graph.invoke(state, config)
        return InvestigationState.model_validate(result)

    def triage(self, state: InvestigationState) -> dict[str, Any]:
        return {
            "symptoms": tuple(s.statement for s in state.input.signals),
            "plan": (
                "Inspect lifecycle and failures",
                "Inspect replay and primary health",
                "Verify competing causes with scoped sources",
                "Review runbook next checks",
            ),
        }

    def query(
        self, state: InvestigationState, calls: tuple[tuple[ToolName, ToolInput], ...], actor: str
    ) -> dict[str, Any]:
        items = {e.evidence_id: e for e in state.input.items}
        call_ids = list(state.tool_calls)
        questions = list(state.unresolved_questions)
        for name, args in calls:
            result = self.runner.call(name, args, actor)
            call_ids.append(result.call_id)
            items.update({e.evidence_id: e for e in result.items})
            if result.status != "ok":
                questions.append(f"{name} evidence unavailable ({result.error})")
        context = AgentInput(
            incident=state.input.incident,
            items=tuple(sorted(items.values(), key=lambda e: (e.timestamp, e.source_ref))),
            signals=state.input.signals,
            truncated=state.input.truncated,
        )
        return {
            "input": context,
            "evidence_ids": tuple(items),
            "tool_calls": tuple(call_ids),
            "unresolved_questions": tuple(dict.fromkeys(questions)),
        }

    def retrieve(self, state: InvestigationState) -> dict[str, Any]:
        identifier = state.input.incident.id
        self.audit.emit(
            "correlator_signals",
            "Retriever",
            {"source": "full_scope", "rules": [s.rule for s in state.input.signals]},
        )
        return self.query(
            state,
            (
                ("runtime_events_query", RuntimeInput(incident_id=identifier)),
                ("logs_query", LogsInput(incident_id=identifier)),
                ("trace_lookup", TraceInput(incident_id=identifier, errors_only=True)),
                ("metric_query", MetricInput(incident_id=identifier, metric_name="requests_total")),
                ("db_replication_status", ReplicationInput(incident_id=identifier)),
                (
                    "runbook_search",
                    RunbookInput(
                        incident_id=identifier, query="replica replay lag process exit timeout"
                    ),
                ),
            ),
            "Retriever",
        )

    def hypothesize(self, state: InvestigationState) -> dict[str, Any]:
        result = propose(state.input, self.adapter)
        return {
            "hypotheses": tuple(
                Hypothesis.model_validate(h.model_dump()) for h in result.output.items
            ),
            "input_tokens": state.input_tokens + result.input_tokens,
            "output_tokens": state.output_tokens + result.output_tokens,
        }

    def verify(self, state: InvestigationState) -> dict[str, Any]:
        calls: list[tuple[ToolName, ToolInput]] = []
        for h in state.hypotheses:
            identifier = state.input.incident.id
            if h.category == "termination":
                calls.append(("runtime_events_query", RuntimeInput(incident_id=identifier)))
            elif h.category in {"replica_lag", "primary_outage"}:
                calls.append(("db_replication_status", ReplicationInput(incident_id=identifier)))
            elif h.category == "dependency":
                calls.append(("logs_query", LogsInput(incident_id=identifier, text="timeout")))
        updates = self.query(state, tuple(calls), "Verifier")
        context = AgentInput.model_validate(updates["input"])
        proposals = tuple(
            Proposal.model_validate(
                {k: v for k, v in h.model_dump().items() if k in Proposal.model_fields}
            )
            for h in state.hypotheses
        )
        updates["hypotheses"] = tuple(verify(p, context) for p in proposals)
        return updates

    def rank(self, state: InvestigationState) -> dict[str, Any]:
        ranked = rank(state.hypotheses, state.input)
        return {
            "ranked_causes": ranked,
            "unresolved_questions": tuple(
                dict.fromkeys(
                    state.unresolved_questions + tuple(q for h in ranked for q in h.missing)
                )
            ),
        }

    def report(self, state: InvestigationState) -> dict[str, Any]:
        canonical = template(state.input, state.ranked_causes).model_copy(
            update={"unresolved_questions": state.unresolved_questions}
        )
        attempt = state.report_attempts + 1
        try:
            output = (
                self.producer(canonical, attempt > 1) if self.producer else canonical.model_dump()
            )
            report = Report.model_validate(output)
            validate_report(report, state.input)
            if (
                report.ranked_hypotheses != state.ranked_causes
                or report.recommendations != canonical.recommendations
            ):
                raise ReportValidationError("Report changed verified ranking or read-only checks")
            return {"report": report, "report_attempts": attempt}
        except (ValidationError, ReportValidationError) as exc:
            if attempt >= 2:
                raise ReportValidationError("Report invalid after one repair") from exc
            self.audit.emit("report_repair", "Reporter", {"error": "UNKNOWN_OR_INVALID_EVIDENCE"})
            return {"report": None, "report_attempts": attempt}

    def report_route(self, state: InvestigationState) -> str:
        return "done" if state.report else "repair"
