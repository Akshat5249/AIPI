"""Credential-free observable replay process; stdin contains scoped telemetry only."""

import json
import sys
from pathlib import Path
from uuid import uuid4

from aipi_tools.audit import MemoryAudit
from aipi_tools.backend import FixtureBackend
from aipi_tools.registry import ToolRunner
from pydantic import BaseModel, ConfigDict

from aipi_agents.schemas import AgentInput, InvestigationState
from aipi_agents.workflow import Workflow


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid")
    context: AgentInput
    runbooks: str


def main() -> None:
    request = Request.model_validate_json(sys.stdin.read())
    context = request.context
    audit = MemoryAudit(uuid4())
    runner = ToolRunner(
        FixtureBackend(context.incident, context.items, Path(request.runbooks)),
        audit,
        audit.investigation_id,
        context.incident.id,
    )
    result = Workflow(runner, audit).run(
        InvestigationState(investigation_id=audit.investigation_id, input=context)
    )
    print(json.dumps({"state": result.model_dump(mode="json"), "tool_calls": len(audit.calls)}))


if __name__ == "__main__":
    main()
