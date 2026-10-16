"""Serialized scenario execution with recovery and restricted audit writes."""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb
from pydantic import JsonValue

from chaos.scenarios.contracts import ChaosError, ScenarioResult, ScenarioSpec
from chaos.scenarios.lab import Lab, now

LOCK_ID = 1095323721


@dataclass
class Run:
    id: UUID
    spec: ScenarioSpec
    injection_ts: datetime | None = None
    recovery_ts: datetime | None = None
    data: dict[str, Any] = field(default_factory=dict)
    observations: dict[str, JsonValue] = field(default_factory=dict)


Step = Callable[[Lab, Run], None]


def save_start(db: psycopg.Connection, run: Run) -> None:
    spec = run.spec
    db.execute(
        "INSERT INTO ground_truth.scenarios "
        "(id,name,description,injected_fault,expected_root_cause,spec_json) "
        "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO UPDATE SET "
        "name=EXCLUDED.name, description=EXCLUDED.description, "
        "injected_fault=EXCLUDED.injected_fault, "
        "expected_root_cause=EXCLUDED.expected_root_cause, spec_json=EXCLUDED.spec_json",
        (
            spec.scenario_id,
            spec.name,
            spec.description,
            spec.ground_truth.injected_fault,
            spec.ground_truth.expected_root_cause,
            Jsonb(spec.model_dump(mode="json")),
        ),
    )
    db.execute(
        "INSERT INTO ground_truth.chaos_runs "
        "(id,scenario_id,seed,started_at,target,expected_root_cause,"
        "scenario_snapshot_json,status,recovery_status) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,'running','pending')",
        (
            run.id,
            spec.scenario_id,
            spec.seed,
            now(),
            spec.target,
            spec.ground_truth.expected_root_cause,
            Jsonb(spec.model_dump(mode="json")),
        ),
    )


def run_scenario(spec: ScenarioSpec, inject: Step, recover: Step, verify: Step) -> ScenarioResult:
    """Only chaos_admin writes labels; recovery precedes verification on every path."""
    lab = Lab(spec.seed)
    run = Run(id=uuid4(), spec=spec)
    passed = False
    error: str | None = None
    recovery_status: Literal["verified", "failed", "not_needed"] = "not_needed"
    try:
        with lab.connect("chaos_admin") as db:
            locked = db.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_ID,)).fetchone()
            if not locked or not locked[0]:
                raise ChaosError("Another chaos run is active; no fault injected")
            try:
                save_start(db, run)
                try:
                    lab.preconditions()
                    run.injection_ts = now()
                    db.execute(
                        "UPDATE ground_truth.chaos_runs SET injection_ts=%s WHERE id=%s",
                        (run.injection_ts, run.id),
                    )
                    inject(lab, run)
                except BaseException as exc:
                    error = str(exc) if isinstance(exc, ChaosError) else type(exc).__name__
                finally:
                    if run.injection_ts is not None:
                        try:
                            recover(lab, run)
                            run.recovery_ts = now()
                            recovery_status = "verified"
                        except BaseException as exc:
                            recovery_status = "failed"
                            error = "Recovery failed: " + (
                                str(exc) if isinstance(exc, ChaosError) else type(exc).__name__
                            )
                if error is None:
                    try:
                        verify(lab, run)
                        passed = True
                    except BaseException as exc:
                        error = str(exc) if isinstance(exc, ChaosError) else type(exc).__name__
                if error:
                    run.observations["error"] = error
                status = (
                    "completed"
                    if passed
                    else ("failed" if run.injection_ts else "precondition_failed")
                )
                db.execute(
                    "UPDATE ground_truth.chaos_runs SET status=%s, recovery_status=%s, "
                    "recovery_ts=%s, completed_at=%s, error=%s, observations_json=%s WHERE id=%s",
                    (
                        status,
                        recovery_status,
                        run.recovery_ts,
                        now(),
                        error,
                        Jsonb(run.observations),
                        run.id,
                    ),
                )
            finally:
                db.execute("SELECT pg_advisory_unlock(%s)", (LOCK_ID,))
    finally:
        lab.close()
    return ScenarioResult(
        run_id=run.id,
        scenario_id=spec.scenario_id,
        passed=passed,
        recovery_status=recovery_status,
        observations=run.observations,
    )


def cli(spec: ScenarioSpec, inject: Step, recover: Step, verify: Step) -> None:
    """Print observable verification only; suppress driver traceback credential locals."""
    try:
        result = run_scenario(spec, inject, recover, verify)
        print(json.dumps(result.model_dump(mode="json"), indent=2))
        raise SystemExit(0 if result.passed else 1)
    except Exception as exc:
        safe = str(exc) if isinstance(exc, ChaosError) else type(exc).__name__
        print(json.dumps({"passed": False, "error": safe}))
        raise SystemExit(1) from None
