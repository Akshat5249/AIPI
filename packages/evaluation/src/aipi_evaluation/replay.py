"""Offline replay loads observable bundles before the scorer opens their truth files."""

import hashlib
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

from aipi_agents.context import PROMPT_VERSION
from aipi_agents.schemas import AgentInput, InvestigationState, Report
from aipi_telemetry.evidence import Evidence
from aipi_tools.contracts import TOOL_VERSION
from aipi_tools.correlators import correlate
from aipi_tools.scope import Incident
from pydantic import BaseModel, ConfigDict

from aipi_evaluation.contracts import Experiment, ScenarioID, Scorecard
from aipi_evaluation.oracle import load_truth
from aipi_evaluation.scoring import score


class ObservableBundle(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    synthetic: bool
    incident: Incident
    items: tuple[Evidence, ...]


def load_bundle(path: Path) -> AgentInput:
    value = ObservableBundle.model_validate_json(path.read_text())
    return AgentInput(
        incident=value.incident,
        items=value.items,
        signals=correlate(value.items),
        truncated=len(value.items) > 50,
    )


def replay(
    name: str,
    fixtures: Path,
    runbooks: Path,
    code_commit: str,
    report_transform: Callable[[Report], Report] | None = None,
) -> Scorecard:
    if name not in {"scn-001", "scn-002", "poisoned-log"}:
        raise ValueError("Fixture outside allowlist")
    context = load_bundle(fixtures / f"{name}.json")
    started = time.monotonic()
    # Only observable JSON enters a separate child. No scorer/DB/model secrets are inherited.
    child_env = {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "PYTHONPATH", "LANG", "LC_ALL", "SYSTEMROOT"}
    }
    child_env["LANGSMITH_TRACING"] = "false"
    child = subprocess.run(
        [sys.executable, "-m", "aipi_agents.fixture_runner"],
        input=json.dumps(
            {"context": context.model_dump(mode="json"), "runbooks": str(runbooks.resolve())}
        ),
        env=child_env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if child.returncode:
        raise ValueError("Observable replay failed")
    observed = json.loads(child.stdout)
    result = InvestigationState.model_validate(observed["state"])
    elapsed = (time.monotonic() - started) * 1000
    if result.report is None:
        raise ValueError("Missing replay report")
    report = report_transform(result.report) if report_transform else result.report
    # Labels become available only here, after the observable agent workflow finishes.
    truth = load_truth(fixtures / f"{name}.truth.json")
    scenario: ScenarioID = "SCN-002" if name == "scn-002" else "SCN-001"
    experiment = Experiment(
        prompt_version=PROMPT_VERSION,
        tool_version=TOOL_VERSION,
        code_commit=code_commit,
        seed=truth.seed,
        retrieval_params={
            "limit": 50,
            "fixture": name,
            "services": ",".join(context.incident.services),
            "start_time": context.incident.start_time.isoformat(),
            "end_time": context.incident.end_time.isoformat(),
        },
        fixture_digest=hashlib.sha256((fixtures / f"{name}.json").read_bytes()).hexdigest(),
    )
    return score(
        scenario,
        truth,
        report,
        {e.evidence_id: e for e in result.input.items},
        experiment,
        elapsed,
        int(observed["tool_calls"]),
        result.input_tokens + result.output_tokens,
        "synthetic"
        if json.loads((fixtures / f"{name}.json").read_text())["synthetic"]
        else "golden",
    )


def write_scorecard(card: Scorecard, directory: Path, name: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    # Write atomically so readers never observe partial scorecards.
    target = directory / f"{name}.json"
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(card.model_dump_json(indent=2) + "\n")
    os.replace(temporary, target)
    values = card.scores
    markdown = (
        f"# {card.scenario_id} evaluation\n\nPassed: {card.passed}\n\n"
        "| Metric | Value |\n|---|---|\n"
        + "\n".join(f"| {key} | {value} |" for key, value in values.model_dump().items())
        + "\n\nExperiment:\n\n```json\n"
        + card.experiment.model_dump_json(indent=2)
        + "\n```\n\nFailures: "
        + (", ".join(card.failures) or "none")
        + "\n"
    )
    (directory / f"{name}.md").write_text(markdown)
