"""Read-only replication and runtime probes, and seeded demo traffic."""

import asyncio
import json
import os
import random
from typing import Any

import httpx
import psycopg
from aipi_telemetry.instrumentation import Telemetry
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

from aipi_demo.contracts import DockerEvent, Order


async def probe(telemetry: Telemetry, app: Any) -> None:
    meter = telemetry.metrics.get_meter(__name__)
    gauges = {
        name: meter.create_gauge(name)
        for name in (
            "replica_lag_seconds",
            "replica_lag_bytes",
            "replica_replay_paused",
            "primary_healthy",
        )
    }
    while True:
        with telemetry.traces.get_tracer(__name__).start_as_current_span("replica.status"):
            async with await psycopg.AsyncConnection.connect(
                os.environ["PRIMARY_PROBE_URL"]
            ) as primary:
                cursor = await primary.execute("SELECT pg_current_wal_lsn()::text")
                row = await cursor.fetchone()
                assert row
                lsn = row[0]
            async with await psycopg.AsyncConnection.connect(
                os.environ["REPLICA_PROBE_URL"]
            ) as replica:
                cursor = await replica.execute(
                    "SELECT pg_wal_lsn_diff(%s::pg_lsn, pg_last_wal_replay_lsn()), "
                    "pg_is_wal_replay_paused(), "
                    "extract(epoch FROM now() - pg_last_xact_replay_timestamp())",
                    (lsn,),
                )
                row = await cursor.fetchone()
                assert row
            lag_bytes, paused, elapsed = row
            values = {
                "replica_lag_bytes": max(0, float(lag_bytes or 0)),
                "replica_lag_seconds": max(0, float(elapsed or 0)) if lag_bytes else 0,
                "replica_replay_paused": int(paused),
                "primary_healthy": 1,
            }
            for name, value in values.items():
                gauges[name].set(value)
            telemetry.logger.info("replica status sampled", extra=values)
            if values["replica_lag_seconds"] > 2 or paused:
                telemetry.logger.warning("replica replay delayed", extra=values)
        app.state.worker_ready = True
        await asyncio.sleep(2)


async def watch(telemetry: Telemetry, app: Any) -> None:
    filters = json.dumps(
        {"label": ["com.docker.compose.project=aipi"], "event": ["die", "start", "restart"]}
    )
    counter = telemetry.metrics.get_meter(__name__).create_counter("runtime_events_total")
    transport = httpx.AsyncHTTPTransport(uds="/var/run/docker.sock")
    async with httpx.AsyncClient(transport=transport, timeout=None) as client:
        # Prove the socket is usable before marking the worker ready.
        response = await client.get("http://docker/_ping")
        response.raise_for_status()
        app.state.worker_ready = True
        async with client.stream(
            "GET", "http://docker/events", params={"filters": filters}
        ) as stream:
            stream.raise_for_status()
            async for line in stream.aiter_lines():
                if not line:
                    continue
                event = DockerEvent.model_validate_json(line)
                attributes = event.actor.attributes
                with telemetry.traces.get_tracer(__name__).start_as_current_span("runtime.event"):
                    counter.add(1, {"event.name": event.action})
                    telemetry.logger.info(
                        "container lifecycle event",
                        extra={
                            "event.domain": "runtime",
                            "event.name": event.action,
                            "container.name": attributes.get(
                                "com.docker.compose.service", "unknown"
                            ),
                            "container.id": event.actor.id,
                            "exit_code": attributes.get("exitCode", ""),
                            "event.timestamp_ns": event.timestamp_ns,
                        },
                    )


async def traffic(telemetry: Telemetry, app: Any) -> None:
    rng = random.Random(int(os.getenv("TRAFFIC_SEED", "42")))
    rate = float(os.getenv("TRAFFIC_RPS", "2"))
    if rate <= 0:
        raise ValueError("TRAFFIC_RPS must be positive")
    requests = telemetry.metrics.get_meter(__name__).create_counter("traffic_requests_total")
    async with httpx.AsyncClient(timeout=5) as client:
        HTTPXClientInstrumentor().instrument_client(client, tracer_provider=telemetry.traces)
        while True:
            with telemetry.traces.get_tracer(__name__).start_as_current_span("traffic.checkout"):
                try:
                    result = await client.post(
                        "http://gateway:8000/checkout",
                        json={
                            "product": rng.choice(["book", "keyboard", "coffee"]),
                            "quantity": rng.randint(1, 3),
                        },
                    )
                    requests.add(1, {"status": result.status_code})
                    if result.is_success:
                        order = Order.model_validate(result.json())
                        await client.get("http://gateway:8000/orders/" + str(order.id))
                        app.state.worker_ready = True
                    telemetry.logger.info(
                        "traffic cycle", extra={"http.status_code": result.status_code}
                    )
                except httpx.HTTPError as exc:
                    telemetry.logger.warning(
                        "traffic dependency unavailable", extra={"error.type": type(exc).__name__}
                    )
                    requests.add(1, {"status": 503})
            await asyncio.sleep(1 / rate)


async def run_worker(service: str, telemetry: Telemetry, app: Any) -> None:
    """Retry transient dependencies; failed probes make worker readiness fail."""
    if service not in ("pg-lag-probe", "event-watcher", "traffic"):
        return
    while True:
        try:
            if service == "pg-lag-probe":
                await probe(telemetry, app)
            elif service == "event-watcher":
                await watch(telemetry, app)
                app.state.worker_ready = False
                await asyncio.sleep(2)
            else:
                await traffic(telemetry, app)
        except (httpx.HTTPError, psycopg.Error, OSError, ValueError) as exc:
            app.state.worker_ready = False
            telemetry.logger.warning(
                "worker dependency unavailable", extra={"error.type": type(exc).__name__}
            )
            await asyncio.sleep(2)
