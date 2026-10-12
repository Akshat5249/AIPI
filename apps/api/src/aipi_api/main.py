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


class Health(BaseModel):
    status: str


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create the app with explicit settings for isolated component tests."""
    config = settings or Settings()  # type: ignore[call-arg]
    store = TelemetryStore(config.telemetry_database_url.get_secret_value())

    telemetry = (
        configure("api", config.otel_exporter_otlp_endpoint) if config.otel_enabled else None
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        store.engine.dispose()
        if telemetry:
            await run_in_threadpool(telemetry.shutdown)

    app = FastAPI(title="AIPI", lifespan=lifespan)
    app.state.store = store

    @app.get("/healthz")
    def health() -> Health:
        return Health(status="ok")

    @app.get("/readyz")
    def ready() -> Health:
        try:
            with store.engine.connect() as connection:
                connection.execute(text("SELECT 1 FROM telemetry_logs LIMIT 1"))
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
