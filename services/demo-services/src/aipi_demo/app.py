"""Instrumented gateway, checkout and replica reads, plus health for lab workers."""

import asyncio
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import httpx
import psycopg
from aipi_telemetry.instrumentation import configure
from fastapi import FastAPI, HTTPException
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.trace import Status, StatusCode

from aipi_demo.contracts import Checkout, Order
from aipi_demo.workers import run_worker


def create_app() -> FastAPI:
    """Use SERVICE_NAME to select one of six isolated Compose processes."""
    service = os.environ["SERVICE_NAME"]
    telemetry = configure(
        service, os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    )
    tracer = telemetry.traces.get_tracer(__name__)
    meter = telemetry.metrics.get_meter(__name__)
    counter = meter.create_counter("requests_total")
    latency = meter.create_histogram("request_duration_ms")
    client = httpx.AsyncClient(timeout=5)
    HTTPXClientInstrumentor().instrument_client(client, tracer_provider=telemetry.traces)
    db = os.getenv("DEMO_DATABASE_URL")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        task = asyncio.create_task(run_worker(service, telemetry, app))
        app.state.worker_task = task
        try:
            yield
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await client.aclose()
            await asyncio.to_thread(telemetry.shutdown)

    app = FastAPI(title=service, lifespan=lifespan)
    app.state.worker_ready = service not in ("pg-lag-probe", "event-watcher", "traffic")
    app.state.worker_error = None

    @app.get("/healthz")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": service}

    @app.get("/readyz")
    async def ready() -> dict[str, str]:
        if service == "gateway":
            try:
                for upstream in ("checkout-api", "orders-api"):
                    response = await client.get(f"http://{upstream}:8000/readyz")
                    response.raise_for_status()
            except httpx.HTTPError as exc:
                raise HTTPException(503, "Upstream service unavailable") from exc
        if db:
            try:
                async with await psycopg.AsyncConnection.connect(
                    db, connect_timeout=3
                ) as connection:
                    await connection.execute("SELECT 1")
            except psycopg.Error as exc:
                raise HTTPException(503, "Database unavailable") from exc
        if not app.state.worker_ready or (
            service in ("pg-lag-probe", "event-watcher", "traffic") and app.state.worker_task.done()
        ):
            raise HTTPException(503, "Worker has not completed its first successful cycle")
        return {"status": "ready"}

    @app.post("/checkout", response_model=Order)
    async def checkout(body: Checkout) -> Order:
        started = time.monotonic()
        status = 200
        try:
            if service == "gateway":
                response = await client.post(
                    "http://checkout-api:8000/checkout", json=body.model_dump()
                )
                response.raise_for_status()
                order = Order.model_validate(response.json())
                telemetry.logger.info(
                    "gateway request completed", extra={"order.id": str(order.id)}
                )
                return order
            if service != "checkout-api" or not db:
                raise HTTPException(404, "Route unavailable for this service")
            order = Order(id=uuid4(), product=body.product, quantity=body.quantity)
            with tracer.start_as_current_span(
                "postgres.insert_order", attributes={"db.system": "postgresql"}
            ):
                async with await psycopg.AsyncConnection.connect(db) as connection:
                    await connection.execute(
                        "INSERT INTO orders (id, product, quantity, status) VALUES (%s,%s,%s,%s)",
                        (order.id, order.product, order.quantity, order.status),
                    )
            telemetry.logger.info("order created", extra={"order.id": str(order.id)})
            return order
        except HTTPException as exc:
            status = exc.status_code
            raise
        except (httpx.HTTPError, psycopg.Error) as exc:
            status = 503
            telemetry.logger.error(
                "checkout dependency failed", extra={"error.type": type(exc).__name__}
            )
            raise HTTPException(503, "Checkout dependency unavailable") from exc
        finally:
            counter.add(1, {"route": "/checkout", "status": status})
            latency.record((time.monotonic() - started) * 1000, {"route": "/checkout"})

    @app.get("/orders/{order_id}", response_model=Order)
    async def read_order(order_id: UUID) -> Order:
        started = time.monotonic()
        status = 200
        try:
            if service == "gateway":
                response = await client.get(f"http://orders-api:8000/orders/{order_id}")
                if response.status_code == 404:
                    raise HTTPException(404, "Order not visible on replica")
                response.raise_for_status()
                order = Order.model_validate(response.json())
                telemetry.logger.info(
                    "gateway request completed", extra={"order.id": str(order.id)}
                )
                return order
            if service != "orders-api" or not db:
                raise HTTPException(404, "Route unavailable for this service")
            with tracer.start_as_current_span(
                "postgres.select_order", attributes={"db.system": "postgresql"}
            ) as span:
                # Bounded retries make stale reads observable while the primary remains healthy.
                for attempt in range(3):
                    async with await psycopg.AsyncConnection.connect(db) as connection:
                        cursor = await connection.execute(
                            "SELECT id, product, quantity, status FROM orders WHERE id=%s",
                            (order_id,),
                        )
                        row = await cursor.fetchone()
                    if row:
                        telemetry.logger.info(
                            "order read", extra={"order.id": str(order_id), "retry.count": attempt}
                        )
                        return Order(id=row[0], product=row[1], quantity=row[2], status=row[3])
                    await asyncio.sleep(0.1)
                span.set_status(Status(StatusCode.ERROR, "Replica read retry deadline exceeded"))
                span.set_attribute("error.type", "ReplicaReadTimeout")
                telemetry.logger.warning(
                    "stale replica read",
                    extra={
                        "order.id": str(order_id),
                        "error.type": "ReplicaReadTimeout",
                        "retry.count": 3,
                    },
                )
                raise HTTPException(404, "Order not visible on replica")
        except HTTPException as exc:
            status = exc.status_code
            raise
        except (httpx.HTTPError, psycopg.Error) as exc:
            status = 503
            telemetry.logger.error(
                "order dependency failed", extra={"error.type": type(exc).__name__}
            )
            raise HTTPException(503, "Orders dependency unavailable") from exc
        finally:
            counter.add(1, {"route": "/orders", "status": status})
            latency.record((time.monotonic() - started) * 1000, {"route": "/orders"})

    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=telemetry.traces,
        meter_provider=telemetry.metrics,
        excluded_urls="healthz,readyz",
    )
    return app
