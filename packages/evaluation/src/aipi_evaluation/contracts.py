"""Public score/replay contracts contain metrics, never protected causal labels."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

ScenarioID = Literal["SCN-001", "SCN-002"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ReplayRequest(Strict):
    scenario_id: ScenarioID
    mode: Literal["golden", "recorded"] = "golden"
    incident_id: UUID | None = None
    chaos_run_id: UUID | None = None

    @model_validator(mode="after")
    def inputs(self) -> "ReplayRequest":
        if (self.incident_id is None or self.chaos_run_id is None) and self.mode == "recorded":
            raise ValueError("Recorded replay needs incident and protected run references")
        if self.mode == "golden" and (self.incident_id or self.chaos_run_id):
            raise ValueError("Golden replay takes only the scenario identifier")
        return self


class Experiment(Strict):
    provider: str = "mock"
    model: str = "deterministic-mock-v1"
    prompt_version: str
    tool_version: str
    code_commit: str
    seed: int
    retrieval_params: dict[str, str | int | bool]
    fixture_digest: str | None = None


class Scores(Strict):
    top1: float = Field(ge=0, le=1)
    top3_recall: float = Field(ge=0, le=1)
    evidence_precision: float = Field(ge=0, le=1)
    evidence_coverage: float = Field(ge=0, le=1)
    unsupported_claim_rate: float = Field(ge=0, le=1)
    contradiction_handling: float = Field(ge=0, le=1)
    latency_ms: float = Field(ge=0)
    useful_evidence_per_tool_call: float = Field(ge=0)
    useful_evidence_per_token: float | None = None
    citation_pairs: int = Field(ge=0)
    supported_pairs: int = Field(ge=0)
    material_claims: int = Field(ge=0)
    unsupported_claims: int = Field(ge=0)
    critical_unsupported_claims: int = Field(ge=0)
    covered_features: tuple[str, ...]
    required_feature_count: int = Field(ge=1)
    tool_calls: int = Field(ge=0)
    tokens: int = Field(ge=0)


class Scorecard(Strict):
    scenario_id: ScenarioID
    passed: bool
    scores: Scores
    experiment: Experiment
    failures: tuple[str, ...] = ()
    mode: Literal["synthetic", "golden", "recorded"]
    investigation_id: UUID | None = None
    created_at: datetime


class EvaluationJob(Strict):
    id: UUID
    scenario_id: ScenarioID
    investigation_id: UUID | None = None
    status: Literal["queued", "running", "completed", "failed"]
    created_at: datetime
    completed_at: datetime | None = None
    scorecard: Scorecard | None = None
    error: str | None = None
