"""Provider interface and deterministic offline mock; optional live providers omitted."""

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from aipi_agents.context import Prompt
from aipi_agents.schemas import Proposals


class ModelResult[T: BaseModel](BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    output: T
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    latency_ms: float = Field(default=0, ge=0)
    provider: str = "mock"
    model: str = "deterministic-mock-v1"


class Adapter(Protocol):
    def generate_structured[T: BaseModel](
        self, prompt: Prompt, schema: type[T]
    ) -> ModelResult[T]: ...


class MockAdapter:
    def generate_structured[T: BaseModel](self, prompt: Prompt, schema: type[T]) -> ModelResult[T]:
        rules = {signal.rule for signal in prompt.signals}
        candidates = []
        if "ProcessExitRule" in rules:
            candidates.append(
                dict(
                    id="h_termination",
                    category="termination",
                    statement="Checkout service process terminated",
                    falsification_condition="Show the target stayed alive during failed requests",
                    expected_evidence=[
                        "runtime exit and recovery",
                        "correlated failed HTTP requests",
                    ],
                )
            )
        if "ReplicaLagRule" in rules:
            candidates.append(
                dict(
                    id="h_replica_lag",
                    category="replica_lag",
                    statement="Replica WAL replay paused, causing replication lag and stale reads",
                    falsification_condition="Show unpaused replay during stale reads",
                    expected_evidence=[
                        "lag and WAL backlog",
                        "paused replay",
                        "stale read log or trace",
                    ],
                )
            )
            candidates.append(
                dict(
                    id="h_primary_outage",
                    category="primary_outage",
                    statement="Primary outage caused read failures",
                    falsification_condition="Show healthy primary with successful writes",
                    expected_evidence=["primary failure", "failed application reads"],
                )
            )
        candidates.append(
            dict(
                id="h_dependency",
                category="dependency",
                statement="Downstream dependency failure caused request symptoms",
                falsification_condition="Show lifecycle or replay failure explains symptoms",
                expected_evidence=["timeout or latency symptom", "independent dependency failure"],
            )
        )
        if len(candidates) < 2:
            candidates.append(
                dict(
                    id="h_insufficient",
                    category="insufficient",
                    statement="Insufficient evidence to establish a root cause",
                    falsification_condition="Collect direct lifecycle or replay telemetry",
                    expected_evidence=["direct causal telemetry"],
                )
            )
        proposal = Proposals.model_validate({"items": candidates[:5]})
        output = schema.model_validate(proposal.model_dump())
        return ModelResult(output=output)


def adapter_for(provider: str) -> Adapter:
    if provider != "mock":
        raise ValueError("Only the mock provider is implemented in this local release")
    return MockAdapter()
