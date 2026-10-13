"""Validated investigation inputs, hypotheses and reports; no hidden label fields."""

from typing import Literal
from uuid import UUID

from aipi_telemetry.evidence import Evidence, TimelineItem
from aipi_tools.correlators import Signal
from aipi_tools.scope import Incident
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class AgentInput(StrictModel):
    incident: Incident
    items: tuple[Evidence, ...]
    signals: tuple[Signal, ...]
    truncated: bool = False

    @model_validator(mode="after")
    def scoped(self) -> "AgentInput":
        ids = {e.evidence_id for e in self.items}
        if any(
            e.service not in self.incident.services
            or not self.incident.start_time <= e.timestamp <= self.incident.end_time
            for e in self.items
        ):
            raise ValueError("Agent evidence exceeds the incident scope")
        if any(not set(s.evidence_ids) <= ids for s in self.signals):
            raise ValueError("Signal citation is missing from scoped evidence")
        return self


Category = Literal["termination", "replica_lag", "primary_outage", "dependency", "insufficient"]


class Hypothesis(StrictModel):
    id: str
    statement: str
    category: Category
    falsification_condition: str = Field(min_length=1)
    expected_evidence: tuple[str, ...] = Field(min_length=1)
    for_ids: tuple[str, ...] = Field(default=(), alias="for")
    against: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    rank: int = Field(default=0, ge=0)
    confidence: float = Field(default=0, ge=0, le=1)


class Proposal(StrictModel):
    """The model cannot submit a confidence or fabricate verification evidence."""

    id: str
    statement: str
    category: Category
    falsification_condition: str = Field(min_length=1)
    expected_evidence: tuple[str, ...] = Field(min_length=1)


class Proposals(StrictModel):
    items: tuple[Proposal, ...] = Field(min_length=2, max_length=5)

    @model_validator(mode="after")
    def unique(self) -> "Proposals":
        if len({h.id for h in self.items}) != len(self.items):
            raise ValueError("Hypothesis identifiers must be unique")
        return self


class RootCause(StrictModel):
    statement: str
    hypothesis_id: str
    confidence: float = Field(ge=0, le=1)


class Claim(StrictModel):
    claim_id: str
    kind: Literal["fact", "hypothesis", "recommendation"]
    text: str
    evidence_ids: tuple[str, ...] = Field(min_length=1)


class Recommendation(StrictModel):
    id: str
    statement: str
    evidence_ids: tuple[str, ...] = Field(min_length=1)
    requires_approval: Literal[True] = True
    executed: Literal[False] = False
    approval_status: Literal["pending"] = "pending"


class Report(StrictModel):
    root_cause: RootCause
    claims: tuple[Claim, ...]
    timeline: tuple[TimelineItem, ...]
    ranked_hypotheses: tuple[Hypothesis, ...] = Field(min_length=2, max_length=5)
    unresolved_questions: tuple[str, ...]
    recommendations: tuple[Recommendation, ...]
    markdown: str

    @model_validator(mode="after")
    def ranking(self) -> "Report":
        hypotheses = self.ranked_hypotheses
        if [h.rank for h in hypotheses] != list(range(1, len(hypotheses) + 1)):
            raise ValueError("Hypothesis ranks must be contiguous")
        top = hypotheses[0]
        if (
            self.root_cause.hypothesis_id,
            self.root_cause.statement,
            self.root_cause.confidence,
        ) != (top.id, top.statement, top.confidence):
            raise ValueError("Root cause must match the ranked top hypothesis")
        return self


def cited_ids(report: Report) -> frozenset[str]:
    return frozenset(
        [eid for c in report.claims for eid in c.evidence_ids]
        + [eid for h in report.ranked_hypotheses for eid in h.for_ids + h.against]
        + [eid for r in report.recommendations for eid in r.evidence_ids]
        + [eid for t in report.timeline for eid in t.evidence_ids]
    )


class InvestigationState(StrictModel):
    investigation_id: UUID
    input: AgentInput
    symptoms: tuple[str, ...] = ()
    plan: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    hypotheses: tuple[Hypothesis, ...] = ()
    tool_calls: tuple[UUID, ...] = ()
    ranked_causes: tuple[Hypothesis, ...] = ()
    unresolved_questions: tuple[str, ...] = ()
    report: Report | None = None
    report_attempts: int = Field(default=0, ge=0, le=2)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
