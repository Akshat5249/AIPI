"""Scorer-only file/database truth; typed private labels never passed to agents."""

import json
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from aipi_evaluation.contracts import ScenarioID, Strict


class Truth(Strict):
    expected_category: Literal["termination", "replica_lag"]
    seed: int = 42
    required_features: tuple[str, ...] = ()


FEATURES = {
    "termination": ("die_137", "recovery", "http_5xx", "failed_span", "gateway_error"),
    "replica_lag": (
        "lag_seconds",
        "wal_backlog",
        "replay_paused",
        "healthy_primary",
        "stale_read",
        "timeout",
    ),
}


def load_truth(path: Path) -> Truth:
    if not path.name.endswith(".truth.json"):
        raise ValueError("Scorer truth must be a separate file")
    result = Truth.model_validate(json.loads(path.read_text()))
    return result.model_copy(
        update={"required_features": result.required_features or FEATURES[result.expected_category]}
    )


class ProtectedRun(Strict):
    id: UUID
    scenario_id: ScenarioID
    seed: int
    injection_ts: AwareDatetime
    completed_at: AwareDatetime
    expected_root_cause: str = Field(exclude=True)
    status: str
    recovery_status: str

    def truth(self) -> Truth:
        # Derive from the protected causal label, never from observable scenario tags.
        if "terminated" in self.expected_root_cause:
            category: Literal["termination", "replica_lag"] = "termination"
        elif "WAL replay" in self.expected_root_cause:
            category = "replica_lag"
        else:
            raise ValueError("Unsupported protected root-cause category")
        return Truth(
            expected_category=category, seed=self.seed, required_features=FEATURES[category]
        )


class TruthReader:
    def __init__(self, url: str) -> None:
        if make_url(url).username != "chaos_admin":
            raise ValueError("Scorer requires the restricted truth identity")
        self.engine = create_engine(
            url,
            hide_parameters=True,
            pool_pre_ping=True,
            connect_args={
                "connect_timeout": 5,
                "options": "-c default_transaction_read_only=on -c statement_timeout=5000",
            },
        )

    def run(
        self, identifier: UUID, scenario_id: ScenarioID, start: datetime, end: datetime
    ) -> ProtectedRun:
        with self.engine.connect() as db:
            if db.scalar(text("SELECT current_user")) != "chaos_admin":
                raise ValueError("Unexpected scorer identity")
            row = (
                db.execute(
                    text(
                        "SELECT id,scenario_id,seed,injection_ts,completed_at,"
                        "expected_root_cause,status,recovery_status "
                        "FROM ground_truth.chaos_runs WHERE id=:id"
                    ),
                    {"id": identifier},
                )
                .mappings()
                .first()
            )
        if row is None:
            raise ValueError("Protected run not found")
        run = ProtectedRun.model_validate(dict(row))
        if (
            run.scenario_id != scenario_id
            or run.status != "completed"
            or run.recovery_status != "verified"
        ):
            raise ValueError("Run identity or recovery mismatch")
        if not start <= run.injection_ts <= run.completed_at <= end:
            raise ValueError("Incident does not cover the protected run window")
        return run
