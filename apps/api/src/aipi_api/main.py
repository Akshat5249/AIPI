"""Internal OTLP ingestion and health endpoints for the foundation phase."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Literal

from aipi_telemetry.instrumentation import configure
from aipi_telemetry.otlp import normalize
from aipi_telemetry.storage import TelemetryStore
from fastapi import FastAPI, HTTPException
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from pydantic import BaseModel, ValidationError
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool

from aipi_api.config import Settings
from aipi_api.errors import ErrorEnvelope, install_errors
from aipi_api.incidents import IncidentCore
from aipi_api.investigation_routes import router as investigation_router
from aipi_api.investigations import Investigator
from aipi_api.routes import router


class Health(BaseModel):
    status: str


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create the app with explicit settings for isolated component tests."""
    config = settings or Settings()  # type: ignore[call-arg]
    store = TelemetryStore(config.telemetry_database_url.get_secret_value())

    core = IncidentCore(
        config.database_url.get_secret_value(), config.telemetry_database_url.get_secret_value()
    )

    telemetry = (
        configure("api", config.otel_exporter_otlp_endpoint) if config.otel_enabled else None
    )

    investigator = Investigator(
        core,
        config,
        telemetry.traces.get_tracer("aipi.investigations") if telemetry else None,
        telemetry.metrics.get_meter("aipi.investigations") if telemetry else None,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await run_in_threadpool(investigator.recover_interrupted)
        yield
        investigator.close()
        store.engine.dispose()
        core.close()
        if telemetry:
            await run_in_threadpool(telemetry.shutdown)

    app = FastAPI(
        title="AIPI",
        lifespan=lifespan,
        responses={code: {"model": ErrorEnvelope} for code in (400, 403, 404, 422, 500, 503)},
    )
    app.state.store = store
    app.state.core = core
    app.state.investigator = investigator
    install_errors(app)
    app.include_router(router)
    app.include_router(investigation_router)

    @app.get("/healthz")
    def health() -> Health:
        return Health(status="ok")

    @app.get("/readyz")
    def ready() -> Health:
        try:
            with store.engine.connect() as connection:
                connection.execute(text("SELECT 1 FROM telemetry_logs LIMIT 1"))
            with core.reader.engine.connect() as connection:
                connection.execute(text("SELECT 1 FROM incidents LIMIT 1"))
        except Exception as exc:
            raise HTTPException(503, "Telemetry database unavailable") from exc
        return Health(status="ready")

    @app.post("/internal/otlp/v1/{kind}", response_model=dict[str, Any])
    async def ingest(
        kind: Literal["logs", "traces", "metrics"], payload: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            rows = normalize(kind, payload, emails=config.redact_emails)
        except (ValidationError, ValueError, OverflowError) as exc:
            raise HTTPException(400, "Invalid OTLP JSON payload") from exc
        await run_in_threadpool(store.persist, rows)
        return {}  # OTLP Export*ServiceResponse; success without partialSuccess.

    if telemetry:
        FastAPIInstrumentor.instrument_app(
            app,
            tracer_provider=telemetry.traces,
            meter_provider=telemetry.metrics,
            excluded_urls="healthz,readyz,internal/otlp",
        )
    return app
