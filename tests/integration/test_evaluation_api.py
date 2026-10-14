"""Live scorer isolation, durable replay APIs and public score-only contracts."""

import json
import subprocess
import time
from uuid import uuid4

import httpx
import psycopg
import pytest
from aipi_evaluation.contracts import EvaluationJob

from chaos.scenarios.lab import Lab
from tests.integration.test_incidents import API, admin

pytestmark = pytest.mark.docker


@pytest.mark.parametrize("scenario", ["SCN-001", "SCN-002"])
def test_golden_replay_api_and_persisted_metrics(scenario):
    with httpx.Client(base_url=API, timeout=20) as client:
        response = client.post("/api/evaluations/replay", json={"scenario_id": scenario})
        assert response.status_code == 202, response.text
        job = EvaluationJob.model_validate(response.json())
        assert job.status == "queued"
        deadline = time.monotonic() + 30
        while job.status in {"queued", "running"} and time.monotonic() < deadline:
            time.sleep(0.1)
            job = EvaluationJob.model_validate(client.get(f"/api/evaluations/{job.id}").json())
        assert job.status == "completed" and job.scorecard and job.scorecard.passed
        assert job.scorecard.scores.top1 == job.scorecard.scores.evidence_precision == 1
        public = job.model_dump_json()
        assert all(
            key not in public
            for key in (
                "expected_root_cause",
                "expected_category",
                "injected_fault",
                "truth_database_url",
            )
        )
        assert client.get(f"/api/evaluations/{job.id}").json() == job.model_dump(mode="json")
        disclosure = client.get(f"/api/evaluations/{job.id}/ground-truth")
        assert disclosure.status_code == 200, disclosure.text
        truth = disclosure.json()
        assert truth["evaluation_id"] == str(job.id) and truth["source"] == "golden"
        assert truth["expected_root_cause"] and truth["required_evidence"]
        assert "ground_truth" not in client.get("/api/scenarios").text
        assert client.get(f"/api/evaluations/{uuid4()}").status_code == 404
        for body in (
            {"scenario_id": "SCN-999"},
            {"scenario_id": scenario, "expected_root_cause": "secret"},
            {"scenario_id": scenario, "mode": "recorded"},
        ):
            invalid = client.post(
                "/api/evaluations/replay", json=body, headers={"X-Request-ID": "eval-validation"}
            )
            assert (
                invalid.status_code == 422
                and invalid.json()["error"]["request_id"] == "eval-validation"
            )
        print(
            f"REPLAY API {scenario}: completed Top-1=1 precision=1 "
            "scorecard persisted no truth fields"
        )
    lab = Lab()
    with admin(lab) as db:
        row = db.execute(
            "SELECT metrics_json FROM evaluation_runs WHERE id=%s", (job.id,)
        ).fetchone()
        assert row and row[0] == job.scorecard.model_dump(mode="json")
    with lab.connect("investigator_ro") as db:
        assert db.execute(
            "SELECT metrics_json FROM evaluation_runs WHERE id=%s", (job.id,)
        ).fetchone()[0]
        for statement in (
            "UPDATE evaluation_runs SET status='completed'",
            "SELECT * FROM ground_truth.scenarios",
        ):
            with pytest.raises(
                (psycopg.errors.InsufficientPrivilege, psycopg.errors.ReadOnlySqlTransaction)
            ):
                db.execute(statement)
    lab.close()


def test_api_container_has_no_scorer_secret_or_truth_fixtures():
    command = [
        "docker",
        "compose",
        "--env-file",
        ".env",
        "-f",
        "infra/docker/compose.yml",
        "exec",
        "-T",
        "api",
        "python",
        "-c",
        "import os; from pathlib import Path; "
        "assert 'SCORER_TRUTH_DATABASE_URL' not in os.environ; "
        "assert 'CHAOS_PASSWORD' not in os.environ; "
        "assert not Path('/app/tests/fixtures/scn-001.truth.json').exists(); "
        "print('API has no truth credentials or fixture files')",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=20)
    assert result.returncode == 0, result.stdout
    print(result.stdout.strip())


def test_recorded_replay_checks_protected_run_window_and_exports_metrics():
    lab = Lab()
    with lab.connect("investigator_ro") as db:
        row = db.execute(
            "SELECT request_json FROM evaluation_runs "
            "WHERE request_json->>'mode'='recorded' AND status='completed' "
            "ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    if row is None:
        # Fresh CI has no recording corpus yet; create one recovered run in a real window.
        import sys
        from datetime import UTC, datetime, timedelta

        from tests.integration.test_incidents import create

        start = datetime.now(UTC) - timedelta(seconds=30)
        run = subprocess.run(
            [sys.executable, "-m", "chaos.scenarios.scn_002_replica_lag"],
            capture_output=True,
            text=True,
            check=False,
            timeout=100,
        )
        assert run.returncode == 0, run.stdout
        with httpx.Client(base_url=API, timeout=30) as client:
            incident = create(
                client, start, datetime.now(UTC), "orders-api", ("pg-lag-probe", "checkout-api")
            )
            response = client.post(f"/api/incidents/{incident.id}/investigate", json={})
            job = response.json()
            deadline = time.monotonic() + 60
            while job["status"] in {"queued", "running"} and time.monotonic() < deadline:
                time.sleep(0.2)
                job = client.get(f"/api/investigations/{job['id']}").json()
            assert job["status"] == "completed"
        body = {
            "scenario_id": "SCN-002",
            "mode": "recorded",
            "incident_id": str(incident.id),
            "chaos_run_id": json.loads(run.stdout)["run_id"],
        }
    else:
        body = row[0]
    with httpx.Client(base_url=API, timeout=30) as client:
        response = client.post("/api/evaluations/replay", json=body)
        assert response.status_code == 202, response.text
        identifier = response.json()["id"]
        job = response.json()
        deadline = time.monotonic() + 60
        while job["status"] in {"queued", "running"} and time.monotonic() < deadline:
            time.sleep(0.2)
            job = client.get(f"/api/evaluations/{identifier}").json()
        assert job["status"] == "completed" and job["scorecard"]["passed"]
        assert job["scorecard"]["mode"] == "recorded" and job["scorecard"]["investigation_id"]
        bad = {**body, "scenario_id": "SCN-001" if body["scenario_id"] == "SCN-002" else "SCN-002"}
        response = client.post("/api/evaluations/replay", json=bad)
        wrong = response.json()
        deadline = time.monotonic() + 30
        while wrong["status"] in {"queued", "running"} and time.monotonic() < deadline:
            time.sleep(0.2)
            wrong = client.get(f"/api/evaluations/{wrong['id']}").json()
        assert wrong["status"] == "failed" and wrong["error"] == "EVALUATION_FAILED"
    deadline = time.monotonic() + 15
    found = False
    with lab.connect("investigator_ro") as db:
        while time.monotonic() < deadline:
            found = bool(
                db.execute(
                    "SELECT 1 FROM telemetry_metrics WHERE service='scorer' "
                    "AND metric_name='evaluation.top1.count' LIMIT 1"
                ).fetchone()
            )
            if found:
                break
            time.sleep(0.3)
    assert found, "Scorer OTel evaluation metric was not exported"
    print(
        "Recorded replay scored through protected oracle; wrong run/scenario denied; "
        "evaluation OTel metric persisted"
    )
    lab.close()
