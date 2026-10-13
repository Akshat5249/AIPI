"""Real M4b chaos-to-report gate and scoped citation resolution beyond the cap."""

import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from aipi_agents.schemas import Report, cited_ids
from aipi_agents.workflow import NODES
from aipi_tools.retrieval import EvidenceBundle

from chaos.scenarios.lab import ROOT, Lab
from tests.integration.test_incidents import API, admin, create

pytestmark = pytest.mark.docker


@pytest.mark.parametrize(
    "module,service,related,category",
    [
        ("scn_001_service_kill", "checkout-api", ("gateway",), "termination"),
        ("scn_002_replica_lag", "orders-api", ("pg-lag-probe", "checkout-api"), "replica_lag"),
    ],
)
def test_live_mock_investigation(module, service, related, category):
    time.sleep(30)
    start = datetime.now(UTC) - timedelta(seconds=30)
    chaos = subprocess.run(
        [sys.executable, "-m", f"chaos.scenarios.{module}"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=100,
        check=False,
    )
    assert chaos.returncode == 0, chaos.stdout
    assert json.loads(chaos.stdout)["recovery_status"] == "verified"
    end = datetime.now(UTC)
    lab = Lab()
    marker = "hidden-investigation-" + uuid4().hex
    with admin(lab) as db:
        db.execute("CREATE TABLE IF NOT EXISTS ground_truth.agent_probe(label text)")
        db.execute("INSERT INTO ground_truth.agent_probe(label) VALUES (%s)", (marker,))
    with httpx.Client(base_url=API, timeout=30) as client:
        incident = create(client, start, end, service, related)
        path = f"/api/incidents/{incident.id}"
        bundle = EvidenceBundle.model_validate(client.get(path + "/evidence").json())
        assert bundle == EvidenceBundle.model_validate(client.get(path + "/evidence").json())
        response = client.post(path + "/investigate", json={})
        assert response.status_code == 202, response.text
        initial = response.json()
        assert initial["status"] == "queued" and initial["provider"] == "mock"
        job = initial
        deadline = time.monotonic() + 60
        while job["status"] in {"queued", "running"} and time.monotonic() < deadline:
            time.sleep(0.1)
            job = client.get(f"/api/investigations/{initial['id']}").json()
        assert job["status"] == "completed", job
        assert job["input_tokens"] == job["output_tokens"] == job["estimated_cost"] == 0
        response = client.get(path + "/report")
        assert response.status_code == 200, response.text
        report = Report.model_validate(response.json())
        assert report.ranked_hypotheses[0].category == category
        assert report.ranked_hypotheses[0].for_ids and any(
            h.against for h in report.ranked_hypotheses
        )
        assert client.get(path + "/report").json() == response.json()
        assert client.get(path + "/hypotheses").json() == response.json()["ranked_hypotheses"]
        assert client.get(path + "/recommendations").json() == response.json()["recommendations"]
        assert all(r.requires_approval and not r.executed for r in report.recommendations)
        resolved = {}
        for eid in sorted(cited_ids(report)):
            result = client.get(path + "/evidence/" + eid)
            assert result.status_code == 200, (eid, result.text)
            evidence = result.json()
            assert evidence["service"] in incident.services
            assert (
                start <= datetime.fromisoformat(evidence["timestamp"].replace("Z", "+00:00")) <= end
            )
            resolved[eid] = evidence
        selected = {e.evidence_id for e in bundle.items}
        outside = sorted(cited_ids(report) - selected)
        witnesses = {eid for s in bundle.signals for eid in s.evidence_ids}
        assert outside and set(outside) & witnesses
        assert any(resolved[e]["type"] == "runbook" for e in outside)
        assert any(
            e.type in {"log", "trace"} and e.evidence_id in cited_ids(report) for e in bundle.items
        )
        if category == "replica_lag":
            top = report.ranked_hypotheses[0]
            metrics = {resolved[e]["payload"].get("metric_name") for e in top.for_ids}
            assert {"replica_lag_seconds", "replica_replay_paused"} <= metrics
            assert any(resolved[e]["type"] in {"log", "trace"} for e in top.for_ids)
            assert any(
                resolved[e]["type"] == "log" and "stale replica read" in resolved[e]["summary"]
                for e in cited_ids(report)
            )
            primary = next(h for h in report.ranked_hypotheses if h.category == "primary_outage")
            assert primary.rank > 1 and primary.confidence < top.confidence and primary.against
            assert any(
                resolved[e]["payload"].get("metric_name") == "primary_healthy"
                for e in primary.against
            )
        else:
            assert any(
                e["payload"].get("event_name") == "die"
                and e["payload"]["attributes_json"].get("exit_code") == "137"
                for e in resolved.values()
            )
            assert any(e["payload"].get("event_name") == "start" for e in resolved.values())
        snapshot = client.get(f"/api/investigations/{initial['id']}/events?format=json").json()
        assert snapshot["status"] == "completed"
        assert [e["node"] for e in snapshot["events"] if e["kind"] == "node_completed"] == list(
            NODES
        )
        assert len([e for e in snapshot["events"] if e["kind"] == "tool_completed"]) >= 8
        assert [e["seq"] for e in snapshot["events"]] == list(range(1, len(snapshot["events"]) + 1))
        with client.stream("GET", f"/api/investigations/{initial['id']}/events") as stream:
            assert stream.status_code == 200 and stream.headers["content-type"].startswith(
                "text/event-stream"
            )
            text = "\n".join(stream.iter_lines())
        assert "event: done" in text and "event: node_completed" in text
        after = snapshot["last_seq"]
        assert (
            client.get(
                f"/api/investigations/{initial['id']}/events?format=json&after={after}"
            ).json()["events"]
            == []
        )
        public = json.dumps({"report": response.json(), "events": snapshot, "status": job})
        assert marker not in public and all(
            k not in public for k in ("expected_root_cause", "injected_fault", "injection_ts")
        )
        foreign = create(client, start, end, "api")
        assert client.get(f"/api/incidents/{foreign.id}/evidence/{outside[0]}").status_code == 404
        assert (
            client.get(
                path + "/evidence/" + outside[0], params={"service": "ground_truth"}
            ).status_code
            == 403
        )
        assert (
            client.post(path + "/investigate", json={"service": "ground_truth"}).status_code == 422
        )
        artifact = {
            "module": module,
            "incident_id": str(incident.id),
            "investigation_id": job["id"],
            "status": job["status"],
            "latency_ms": job["latency_ms"],
            "bundle_count": len(selected),
            "cited_count": len(resolved),
            "cited_outside_bundle": outside,
            "outside_rule_witnesses": sorted(set(outside) & witnesses),
            "ranked_categories": [h.category for h in report.ranked_hypotheses],
            "report": response.json(),
            "resolved_evidence": resolved,
        }
        output = os.getenv("AIPI_M4_VERIFICATION_DIR")
        if output:
            destination = Path(output)
            destination.mkdir(parents=True, exist_ok=True)
            (destination / f"{module}.json").write_text(json.dumps(artifact, indent=2) + "\n")
        print(
            json.dumps(
                {
                    "module": module,
                    "incident_id": str(incident.id),
                    "investigation_id": job["id"],
                    "status": job["status"],
                    "latency_ms": job["latency_ms"],
                    "bundle_count": len(selected),
                    "cited_count": len(resolved),
                    "outside_count": len(outside),
                    "outside_rule_witness_count": len(set(outside) & witnesses),
                    "outside_ids_file": f"{module}.json",
                    "outside_first_five": outside[:5],
                    "ranked_categories": [h.category for h in report.ranked_hypotheses],
                }
            )
        )
    lab.close()


def test_failed_job_and_interrupted_recovery_are_durable(monkeypatch):
    from aipi_agents.reporting import ReportValidationError
    from aipi_api.config import Settings
    from aipi_api.incidents import IncidentCore
    from aipi_api.investigation_repository import InvestigationUnavailable
    from aipi_api.investigations import Investigator

    from tests.integration.test_incidents import url

    lab = Lab()
    core = IncidentCore(url(lab, "investigator_ro"), url(lab, "telemetry_writer"))
    config = Settings(
        _env_file=None,
        database_url=url(lab, "investigator_ro"),
        telemetry_database_url=url(lab, "telemetry_writer"),
        model_provider="mock",
    )
    supervisor = Investigator(core, config)
    with httpx.Client(base_url=API, timeout=20) as client:
        incident = create(
            client, datetime(2020, 1, 1, tzinfo=UTC), datetime(2020, 1, 1, 0, 1, tzinfo=UTC), "api"
        )
    try:
        queued = supervisor.start(incident.id)
        supervisor.recover_interrupted()
        assert supervisor.get(queued.id).status == "failed"
        assert supervisor.get(queued.id).error == "PROCESS_INTERRUPTED"
        failed = supervisor.start(incident.id)

        def invalid(*args):
            raise ReportValidationError("Invalid citation after one repair")

        monkeypatch.setattr("aipi_api.investigations.Workflow.run", invalid)
        supervisor.run(failed.id)
        state = supervisor.get(failed.id)
        assert state.status == "failed" and state.error == "REPORT_VALIDATION_FAILED"
        assert supervisor.events(failed.id).events[-1].kind == "investigation_failed"
        with pytest.raises(InvestigationUnavailable):
            supervisor.report(incident.id)
        with httpx.Client(base_url=API, timeout=20) as client:
            response = client.get(
                f"/api/incidents/{incident.id}/report", headers={"X-Request-ID": "failed-job"}
            )
            assert (
                response.status_code == 500
                and response.json()["error"]["code"] == "INVESTIGATION_FAILED"
            )
            assert response.json()["error"]["request_id"] == "failed-job"
            missing = client.get(f"/api/investigations/{uuid4()}/events?format=json")
            assert missing.status_code == 404 and missing.json()["error"]["code"] == "NOT_FOUND"
            assert (
                client.get(
                    f"/api/investigations/{failed.id}/events", headers={"Last-Event-ID": "-1"}
                ).status_code
                == 422
            )
            assert (
                client.get(f"/api/investigations/{failed.id}/events?format=invalid").status_code
                == 422
            )
        print(
            "M4b failure gates: report rejection persisted; request IDs preserved; "
            "interrupted jobs failed; invalid cursors rejected"
        )
    finally:
        supervisor.close()
        core.close()
        lab.close()
