"""Shared OTel SDK setup and JSON logging with trace/span correlation."""

import json
import logging
import os
import socket
from dataclasses import dataclass

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


class JsonFormatter(logging.Formatter):
    """Console logs share the active SDK context with OTLP records."""

    def format(self, record: logging.LogRecord) -> str:
        context = trace.get_current_span().get_span_context()
        return json.dumps(
            {
                "severity": record.levelname,
                "body": record.getMessage(),
                "service": os.getenv("SERVICE_NAME", "api"),
                "trace_id": f"{context.trace_id:032x}",
                "span_id": f"{context.span_id:016x}",
            }
        )


@dataclass
class Telemetry:
    """Providers owned by a service; callers flush and shut down on exit."""

    traces: TracerProvider
    metrics: MeterProvider
    logs: LoggerProvider
    logger: logging.Logger

    def shutdown(self) -> None:
        self.traces.shutdown()
        self.metrics.shutdown()
        self.logs.shutdown()  # type: ignore[no-untyped-call]


def configure(service: str, endpoint: str) -> Telemetry:
    """Create explicit providers so independent apps can be tested in one process."""
    resource = Resource.create(
        {
            "service.name": service,
            "service.version": "0.1.0",
            "deployment.environment": os.getenv("APP_ENV", "local"),
            "host.name": socket.gethostname(),
            "container.name": service,
        }
    )
    traces = TracerProvider(resource=resource)
    traces.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=endpoint + "/v1/traces"), schedule_delay_millis=500
        )
    )
    metrics = MeterProvider(
        resource=resource,
        metric_readers=[
            PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=endpoint + "/v1/metrics"), export_interval_millis=2000
            )
        ],
    )
    logs = LoggerProvider(resource=resource)
    logs.add_log_record_processor(
        BatchLogRecordProcessor(
            OTLPLogExporter(endpoint=endpoint + "/v1/logs"), schedule_delay_millis=500
        )
    )
    logger = logging.getLogger("aipi." + service)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers.clear()
    logger.addHandler(LoggingHandler(logger_provider=logs))
    console = logging.StreamHandler()
    console.setFormatter(JsonFormatter())
    logger.addHandler(console)
    return Telemetry(traces, metrics, logs, logger)
