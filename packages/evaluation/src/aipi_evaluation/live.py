"""Scorer-side live replay: observable HTTP artifacts and protected run oracle stay separate."""

from uuid import UUID

import httpx
from aipi_agents.schemas import Report, cited_ids
from aipi_telemetry.evidence import Evidence
from aipi_tools.retrieval import EvidenceBundle
from aipi_tools.scope import Incident

from aipi_evaluation.contracts import Experiment, ReplayRequest, Scorecard
from aipi_evaluation.oracle import TruthReader
from aipi_evaluation.scoring import score


def live_replay(request: ReplayRequest, api: str, reader: TruthReader) -> Scorecard:
    if request.incident_id is None or request.chaos_run_id is None:
        raise ValueError("Missing recorded replay references")
    with httpx.Client(base_url=api, timeout=30) as client:
        path = f"/api/incidents/{request.incident_id}"

        def get(suffix: str) -> object:
            response = client.get(suffix)
            response.raise_for_status()
            return response.json()

        incident = Incident.model_validate(get(path))
        report = Report.model_validate(get(path + "/report"))
        # The scorer cannot trust arbitrary evidence objects from a request.
        evidence = {
            eid: Evidence.model_validate(get(path + "/evidence/" + eid))
            for eid in sorted(cited_ids(report))
        }
        for item in evidence.values():
            if (
                item.service not in incident.services
                or not incident.start_time <= item.timestamp <= incident.end_time
            ):
                raise ValueError("Evidence outside incident scope")
        bundle = EvidenceBundle.model_validate(get(path + "/evidence"))
        # Find the report's completed owner from its latest incident events.
        jobs_response = client.get("/api/incidents/" + str(incident.id) + "/investigation")
        jobs_response.raise_for_status()
        job = jobs_response.json()
        events_response = client.get(f"/api/investigations/{job['id']}/events?format=json")
        events_response.raise_for_status()
        events = events_response.json()["events"]
    protected = reader.run(
        request.chaos_run_id, request.scenario_id, incident.start_time, incident.end_time
    )
    experiment = Experiment(
        provider=job["provider"],
        model=job["model"],
        prompt_version=job["prompt_version"],
        tool_version=job["tool_version"],
        code_commit=job["code_commit"],
        seed=protected.seed,
        retrieval_params={
            "limit": 50,
            "version": bundle.retrieval_version,
            "services": ",".join(incident.services),
            "start_time": incident.start_time.isoformat(),
            "end_time": incident.end_time.isoformat(),
        },
    )
    return score(
        request.scenario_id,
        protected.truth(),
        report,
        evidence,
        experiment,
        job["latency_ms"],
        sum(e["kind"] == "tool_completed" for e in events),
        job["input_tokens"] + job["output_tokens"],
        "recorded",
        UUID(job["id"]),
    )
