"""Real Docker chaos and restricted causal-label gate, run sequentially."""

import json
import os
import subprocess
import sys

import psycopg
import pytest
import yaml

from chaos.scenarios.contracts import ScenarioResult
from chaos.scenarios.lab import ROOT, Lab
from chaos.scenarios.signals import die_then_start, scalar

pytestmark = pytest.mark.docker


@pytest.mark.parametrize("module", ["scn_001_service_kill", "scn_002_replica_lag"])
def test_live_scenario_runs_and_recovers(module) -> None:
    command = subprocess.run(
        [sys.executable, "-m", f"chaos.scenarios.{module}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=100,
        check=False,
    )
    assert command.returncode == 0, command.stdout  # CLI sanitizes failures and omits labels.
    result = ScenarioResult.model_validate(json.loads(command.stdout))
    assert result.passed and result.recovery_status == "verified"
    lab = Lab()
    try:
        with lab.connect("chaos_admin") as db:
            row = db.execute(
                "SELECT scenario_id,injection_ts,target,expected_root_cause,recovery_status,status "
                "FROM ground_truth.chaos_runs WHERE id=%s",
                (result.run_id,),
            ).fetchone()
            assert row and row[0] == result.scenario_id and row[1] and row[3]
            assert row[4:] == ("verified", "completed")
        if result.scenario_id == "SCN-001":
            assert die_then_start(result.observations["runtime_events"])
            assert result.observations["gateway_5xx_requests"] > 0
        else:
            samples = result.observations["lag_samples"]
            assert samples[-1]["seconds"] > samples[0]["seconds"]
            assert result.observations["primary_healthy_samples"] >= 3
            assert all(result.observations["direct_primary_health_samples"])
        assert lab.healthy_checkout()
    finally:
        lab.close()


def test_ground_truth_and_replay_control_are_restricted() -> None:
    lab = Lab()
    try:
        with lab.connect("investigator_ro") as db:
            assert (
                scalar(
                    db,
                    "SELECT count(*) FROM information_schema.tables WHERE "
                    "table_schema='public' AND table_name IN ('scenarios','chaos_runs')",
                )
                == 0
            )
        for role, key in [
            ("investigator_ro", "INVESTIGATOR_PASSWORD"),
            ("telemetry_writer", "TELEMETRY_WRITER_PASSWORD"),
            ("app_rw", "APP_RW_PASSWORD"),
            ("app_ro", "APP_RO_PASSWORD"),
        ]:
            try:
                db = psycopg.connect(
                    host="127.0.0.1",
                    port=5432,
                    dbname="aipi",
                    user=role,
                    password=lab.env[key],
                    autocommit=True,
                )
            except psycopg.Error:
                pytest.fail("Lab role connection unavailable", pytrace=False)
            with db:
                for table in ("scenarios", "chaos_runs"):
                    with pytest.raises(psycopg.errors.InsufficientPrivilege):
                        db.execute(f"SELECT * FROM ground_truth.{table}")
                for fn in ("pg_wal_replay_pause", "pg_wal_replay_resume"):
                    assert not scalar(
                        db,
                        "SELECT has_function_privilege(current_user,%s,'EXECUTE')",
                        (f"pg_catalog.{fn}()",),
                    )
        # API/demo identities receive no chaos credential even through container configuration.
        from dotenv import dotenv_values

        compose_text = (ROOT / "infra/docker/compose.yml").read_text()
        services = yaml.safe_load(compose_text)["services"]
        for service in (
            "api",
            "gateway",
            "checkout-api",
            "orders-api",
            "pg-lag-probe",
            "event-watcher",
            "traffic",
        ):
            assert "CHAOS_PASSWORD" not in services[service].get("environment", {})
        assert os.getenv("CHAOS_PASSWORD") is None
        assert dotenv_values(ROOT / ".env")["CHAOS_PASSWORD"]
    finally:
        lab.close()
