"""Validated scenario templates and operator verification output."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue

ScenarioID = Literal["SCN-001", "SCN-002"]


class GroundTruth(BaseModel):
    model_config = ConfigDict(extra="forbid")
    injected_fault: str = Field(min_length=1)
    expected_root_cause: str = Field(min_length=1)


class ScenarioSpec(BaseModel):
    """Static templates are stored as registry records only in ground_truth."""

    model_config = ConfigDict(extra="forbid")
    scenario_id: ScenarioID
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    target: Literal["checkout-api", "postgres-replica"]
    preconditions: list[str] = Field(min_length=1)
    injection: str = Field(min_length=1)
    ground_truth: GroundTruth
    expected_signals: list[str] = Field(min_length=1)
    expected_false_leads: list[str] = Field(min_length=1)
    recovery: str = Field(min_length=1)
    evaluation_thresholds: dict[str, float]
    seed: int = Field(default=42, ge=0, le=2**31 - 1)


class ScenarioResult(BaseModel):
    """Operator output contains observed checks, not hidden causal labels."""

    model_config = ConfigDict(extra="forbid")
    run_id: UUID
    scenario_id: ScenarioID
    passed: bool
    recovery_status: Literal["verified", "failed", "not_needed"]
    observations: dict[str, JsonValue]


class ChaosError(RuntimeError):
    """A safe operator error; never include credentials or raw driver output."""
