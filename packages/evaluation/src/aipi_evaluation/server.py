"""Isolated scoring service: only this process receives the protected truth URL."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from aipi_telemetry.instrumentation import configure
from aipi_tools.scope import Incident
from fastapi import BackgroundTasks, FastAPI, HTTPException
from opentelemetry import metrics
from psycopg.types.json import Jsonb
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from aipi_evaluation.contracts import EvaluationJob, EvaluationTruth, ReplayRequest
from aipi_evaluation.live import live_replay
from aipi_evaluation.oracle import TruthReader, load_truth
from aipi_evaluation.replay import replay, write_scorecard


class ScorerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SCORER_", env_file=None, extra="ignore")
    truth_database_url: SecretStr
    writer_database_url: SecretStr
    api_url: str = "http://api:8000"
    fixtures: str = "/app/tests/fixtures"
    runbooks: str = "/app/runbooks"
    output: str = "/app/eval_reports"
    otel_endpoint: str | None = None


class Scorer:
    def __init__(self, config: ScorerSettings) -> None:
        self.config = config
        self.telemetry = configure("scorer", config.otel_endpoint) if config.otel_endpoint else None
        meter = (
            self.telemetry.metrics.get_meter("aipi.evaluation")
            if self.telemetry
            else metrics.get_meter("aipi.evaluation")
        )
        self.top1 = meter.create_histogram("evaluation.top1")
        self.precision = meter.create_histogram("evaluation.evidence_precision")
        self.unsupported = meter.create_histogram("evaluation.unsupported_claim_rate")
        self.truth = TruthReader(config.truth_database_url.get_secret_value())
        url = config.writer_database_url.get_secret_value()
        if make_url(url).username != "telemetry_writer":
            raise ValueError("Unexpected scorer artifact writer")
        self.writer = create_engine(url, hide_parameters=True, connect_args={"connect_timeout": 5})

    def start(self, request: ReplayRequest) -> EvaluationJob:
        job = EvaluationJob(
            id=uuid4(),
            scenario_id=request.scenario_id,
            status="queued",
            created_at=datetime.now(UTC),
        )
        with self.writer.begin() as db:
            db.execute(
                text(
                    "INSERT INTO evaluation_runs(id,scenario_id,chaos_run_id,status,"
                    "created_at,request_json) "
                    "VALUES(:id,:scenario_id,:chaos_run_id,'queued',:created_at,:request_json)"
                ),
                {
                    "id": job.id,
                    "scenario_id": job.scenario_id,
                    "chaos_run_id": request.chaos_run_id,
                    "created_at": job.created_at,
                    "request_json": Jsonb(request.model_dump(mode="json")),
                },
            )
        return job

    def get(self, identifier: UUID) -> EvaluationJob:
        with self.writer.connect() as db:
            row = (
                db.execute(
                    text(
                        "SELECT id,scenario_id,investigation_id,status,created_at,completed_at,"
                        "metrics_json,error FROM evaluation_runs WHERE id=:id"
                    ),
                    {"id": identifier},
                )
                .mappings()
                .first()
            )
        if row is None:
            raise HTTPException(404, "Evaluation not found")
        values = dict(row)
        values["scorecard"] = values.pop("metrics_json")
        return EvaluationJob.model_validate(values)

    def disclosure(self, identifier: UUID) -> EvaluationTruth:
        """Read oracle only for an already scored terminal evaluation, through this route."""
        job = self.get(identifier)
        if job.status not in {"completed", "failed"} or job.scorecard is None:
            raise HTTPException(409, "Ground truth unavailable until scoring completes")
        with self.writer.connect() as db:
            body = db.scalar(
                text("SELECT request_json FROM evaluation_runs WHERE id=:id"),
                {"id": identifier},
            )
        request = ReplayRequest.model_validate(body)
        if request.mode == "golden":
            name = "scn-001" if request.scenario_id == "SCN-001" else "scn-002"
            oracle = load_truth(Path(self.config.fixtures) / f"{name}.truth.json")
            label = {
                "termination": "checkout-api process/container forcibly terminated",
                "replica_lag": "PostgreSQL replica WAL replay paused, causing replication lag",
            }[oracle.expected_category]
        else:
            if request.incident_id is None or request.chaos_run_id is None:
                raise HTTPException(409, "Invalid scored run")
            with httpx.Client(base_url=self.config.api_url, timeout=15) as client:
                response = client.get(f"/api/incidents/{request.incident_id}")
                response.raise_for_status()
                incident = Incident.model_validate(response.json())
            protected = self.truth.run(
                request.chaos_run_id, request.scenario_id, incident.start_time, incident.end_time
            )
            oracle = protected.truth()
            label = protected.expected_root_cause
        return EvaluationTruth(
            evaluation_id=identifier,
            scenario_id=job.scenario_id,
            expected_root_cause=label,
            required_evidence=oracle.required_features,
            seed=oracle.seed,
            source=request.mode,
        )

    def run(self, identifier: UUID, request: ReplayRequest) -> None:
        try:
            with self.writer.begin() as db:
                db.execute(
                    text("UPDATE evaluation_runs SET status='running' WHERE id=:id"),
                    {"id": identifier},
                )
            if request.mode == "golden":
                name = "scn-001" if request.scenario_id == "SCN-001" else "scn-002"
                card = replay(
                    name,
                    Path(self.config.fixtures),
                    Path(self.config.runbooks),
                    os.getenv("AIPI_CODE_COMMIT", "working-tree"),
                )
            else:
                card = live_replay(request, self.config.api_url, self.truth)
            write_scorecard(card, Path(self.config.output), str(identifier))
            attributes = {"scenario": card.scenario_id, "provider": card.experiment.provider}
            self.top1.record(card.scores.top1, attributes)
            self.precision.record(card.scores.evidence_precision, attributes)
            self.unsupported.record(card.scores.unsupported_claim_rate, attributes)
            with self.writer.begin() as db:
                db.execute(
                    text(
                        "UPDATE evaluation_runs SET status=:status,completed_at=:completed,"
                        "investigation_id=:investigation,metrics_json=:metrics,error=:error "
                        "WHERE id=:id"
                    ),
                    {
                        "id": identifier,
                        "status": "completed" if card.passed else "failed",
                        "completed": datetime.now(UTC),
                        "investigation": card.investigation_id,
                        "metrics": Jsonb(card.model_dump(mode="json")),
                        "error": None if card.passed else "EVALUATION_GATE_FAILED",
                    },
                )
        except Exception:
            with self.writer.begin() as db:
                db.execute(
                    text(
                        "UPDATE evaluation_runs SET status='failed',completed_at=:completed,"
                        "error='EVALUATION_FAILED' WHERE id=:id"
                    ),
                    {"id": identifier, "completed": datetime.now(UTC)},
                )


def create_app(config: ScorerSettings | None = None) -> FastAPI:
    scorer = Scorer(config or ScorerSettings())  # type: ignore[call-arg]

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        with scorer.writer.begin() as db:
            db.execute(
                text(
                    "UPDATE evaluation_runs SET status='failed',completed_at=:now,"
                    "error='PROCESS_INTERRUPTED' WHERE status IN ('queued','running')"
                ),
                {"now": datetime.now(UTC)},
            )
        yield
        scorer.writer.dispose()
        scorer.truth.engine.dispose()
        if scorer.telemetry:
            scorer.telemetry.shutdown()

    app = FastAPI(title="AIPI isolated scorer", lifespan=lifespan)
    app.state.scorer = scorer

    @app.get("/readyz")
    def ready() -> dict[str, str]:
        with scorer.writer.connect() as db:
            db.execute(text("SELECT 1 FROM evaluation_runs LIMIT 1"))
        with scorer.truth.engine.connect() as db:
            db.execute(text("SELECT 1 FROM ground_truth.scenarios LIMIT 1"))
        return {"status": "ready"}

    @app.post("/replay", response_model=EvaluationJob, status_code=202)
    def start(request: ReplayRequest, background: BackgroundTasks) -> EvaluationJob:
        job = scorer.start(request)
        background.add_task(scorer.run, job.id, request)
        return job

    @app.get("/evaluations/{identifier}", response_model=EvaluationJob)
    def get(identifier: UUID) -> EvaluationJob:
        return scorer.get(identifier)

    @app.get("/evaluations/{identifier}/ground-truth", response_model=EvaluationTruth)
    def disclosure(identifier: UUID) -> EvaluationTruth:
        return scorer.disclosure(identifier)

    return app
