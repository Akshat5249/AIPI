"""Synthetic-first reasoning gate without database, network or truth-file access."""

from pydantic import ValidationError

from aipi_agents.adapters import Adapter, MockAdapter, ModelResult
from aipi_agents.context import Prompt, data_block
from aipi_agents.reasoning import rank, verify
from aipi_agents.reporting import write_report
from aipi_agents.schemas import AgentInput, Proposals, Report


class ModelOutputInvalid(Exception):
    pass


def propose(context: AgentInput, adapter: Adapter) -> ModelResult[Proposals]:
    prompt = Prompt(
        data_block=data_block([e.model_dump(mode="json") for e in context.items[:50]]),
        signals=context.signals,
    )
    for attempt in range(2):
        try:
            result = adapter.generate_structured(prompt, Proposals)
            return ModelResult[Proposals].model_validate(result.model_dump())
        except (ValueError, ValidationError) as exc:
            if attempt:
                raise ModelOutputInvalid("Model output invalid after one correction") from exc
            prompt = prompt.model_copy(update={"repair": True})
    raise AssertionError("Unreachable")


def investigate(context: AgentInput, adapter: Adapter | None = None) -> Report:
    result = propose(context, adapter or MockAdapter())
    hypotheses = tuple(verify(h, context) for h in result.output.items)
    report, _ = write_report(context, rank(hypotheses, context))
    return report
