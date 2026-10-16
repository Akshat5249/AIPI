"""Host-only lab demo: fixed kill, scoped investigation, scorer-backed live replay."""

import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from typing import Any

import httpx
from aipi_agents.schemas import Report
from aipi_api.investigation_repository import Investigation
from aipi_evaluation.contracts import EvaluationJob
from aipi_tools.scope import Incident

from chaos.scenarios.contracts import ScenarioResult
from chaos.scenarios.target import LabTarget


def request(client: httpx.Client, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    """Validate HTTP success without dumping submitted data in errors."""
    response = client.request(method, path, **kwargs)
    if not response.is_success:
        raise RuntimeError(
            f"{method} {path}: HTTP {response.status_code} "
            f"request_id={response.headers.get('x-request-id', 'unavailable')}"
        )
    data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError("Expected an API object")
    return data


def completed(client: httpx.Client, resource: str, job: dict[str, Any]) -> dict[str, Any]:
    """Bounded polling with actionable job diagnostics on timeout or failure."""
    schema = Investigation if resource == "investigations" else EvaluationJob
    job = schema.model_validate(job).model_dump(mode="json")
    started = time.monotonic()
    while job["status"] in {"queued", "running"} and time.monotonic() - started < 120:
        time.sleep(0.25)
        job = schema.model_validate(
            request(client, "GET", f"/api/{resource}/{job['id']}")
        ).model_dump(mode="json")
    elapsed = time.monotonic() - started
    print(f"{resource}: id={job['id']} status={job['status']} elapsed={elapsed:.2f}s", flush=True)
    if job["status"] != "completed":
        raise RuntimeError(f"{resource} failed or timed out: {job['id']} status={job['status']}")
    return job


def main() -> None:
    target = LabTarget.from_env()
    start = datetime.now(UTC)
    print("Collecting 30 seconds of healthy baseline traffic...", flush=True)
    time.sleep(30)
    run = subprocess.run(
        [sys.executable, "-m", "chaos.scenarios.scn_001_service_kill"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if run.returncode:
        print(run.stdout, flush=True)
        raise SystemExit("Chaos verification failed; inspect the recovered lab before retrying")
    observed = ScenarioResult.model_validate_json(run.stdout).model_dump(mode="json")
    if not observed["passed"] or observed["recovery_status"] != "verified":
        raise SystemExit("Chaos run did not pass with verified recovery")
    end = datetime.now(UTC)
    print(json.dumps({"start": start.isoformat(), "end": end.isoformat(), **observed}), flush=True)
    with httpx.Client(base_url=target.api, timeout=30) as client:
        incident = request(
            client,
            "POST",
            "/api/incidents",
            json={
                "title": "Demo: observed checkout failures",
                "service": "checkout-api",
                "related_services": ["gateway"],
                "start_time": start.isoformat(),
                "end_time": end.isoformat(),
                "symptom": "Gateway checkout requests returned errors",
            },
        )
        identifier = str(Incident.model_validate(incident).id)
        print(f"Incident ID: {identifier}", flush=True)
        print(f"UI URL: {target.web}/#/incidents/{identifier}", flush=True)
        job = completed(
            client,
            "investigations",
            request(client, "POST", f"/api/incidents/{identifier}/investigate", json={}),
        )
        report = request(client, "GET", f"/api/incidents/{identifier}/report")
        report = Report.model_validate(report).model_dump(mode="json")
        print(f"Root cause: {report['root_cause']['statement']}", flush=True)
        evaluation = completed(
            client,
            "evaluations",
            request(
                client,
                "POST",
                "/api/evaluations/replay",
                json={
                    "scenario_id": "SCN-001",
                    "mode": "recorded",
                    "incident_id": identifier,
                    "chaos_run_id": observed["run_id"],
                },
            ),
        )
        card = evaluation["scorecard"]
        print(
            json.dumps(
                {
                    "investigation_id": job["id"],
                    "passed": card["passed"],
                    "scores": card["scores"],
                    "failures": card["failures"],
                }
            ),
            flush=True,
        )
        print(
            f"Evaluation URL: {target.web}/#/evaluations?evaluation={evaluation['id']}"
            f"&incident={identifier}",
            flush=True,
        )
        if not card["passed"]:
            raise SystemExit("Live evaluation gate failed")


if __name__ == "__main__":
    main()
