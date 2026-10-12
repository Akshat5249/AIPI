"""Schema-validated OTLP JSON normalization, including histogram metrics and runtime events."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, JsonValue, model_validator

from aipi_telemetry.redaction import redact


def nanoseconds(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError("Expected an integer nanosecond timestamp")
    result = int(value)
    if result <= 0:
        raise ValueError("Timestamp must be positive")
    return result


Timestamp = Annotated[int, BeforeValidator(nanoseconds)]
TraceID = Annotated[str, Field(pattern=r"^[a-fA-F0-9]{32}$")]
SpanID = Annotated[str, Field(pattern=r"^[a-fA-F0-9]{16}$")]


class OTLPModel(BaseModel):
    """Allow protocol extensions while validating fields consumed by the normalizer."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class AnyValue(OTLPModel):
    stringValue: str | None = None
    boolValue: bool | None = None
    intValue: int | None = None
    doubleValue: float | None = Field(default=None, allow_inf_nan=False)
    arrayValue: dict[str, list["AnyValue"]] | None = None
    kvlistValue: dict[str, list["Attribute"]] | None = None
    bytesValue: str | None = None

    @model_validator(mode="after")
    def one_value(self) -> "AnyValue":
        if sum(getattr(self, key) is not None for key in type(self).model_fields) > 1:
            raise ValueError("AnyValue must contain at most one typed value")
        return self

    def native(self) -> JsonValue:
        if self.arrayValue is not None:
            return [value.native() for value in self.arrayValue.get("values", [])]
        if self.kvlistValue is not None:
            return attributes(self.kvlistValue.get("values", []))
        for key in ("stringValue", "boolValue", "intValue", "doubleValue", "bytesValue"):
            value = getattr(self, key)
            if value is not None:
                return value  # type: ignore[no-any-return]
        return None


class Attribute(OTLPModel):
    key: str
    value: AnyValue


class Resource(OTLPModel):
    attributes: list[Attribute] = Field(default_factory=list)


class LogRecord(OTLPModel):
    timeUnixNano: Timestamp | None = None
    observedTimeUnixNano: Timestamp | None = None
    severityText: str = "INFO"
    severityNumber: int = 9
    body: AnyValue = Field(default_factory=AnyValue)
    attributes: list[Attribute] = Field(default_factory=list)
    traceId: TraceID | Literal[""] = ""
    spanId: SpanID | Literal[""] = ""

    @model_validator(mode="after")
    def timestamp_present(self) -> "LogRecord":
        if self.timeUnixNano is None and self.observedTimeUnixNano is None:
            raise ValueError("A log timestamp is required")
        return self


class Span(OTLPModel):
    traceId: TraceID
    spanId: SpanID
    parentSpanId: SpanID | Literal[""] = ""
    name: str
    startTimeUnixNano: Timestamp
    endTimeUnixNano: Timestamp
    attributes: list[Attribute] = Field(default_factory=list)
    status: dict[str, JsonValue] = Field(default_factory=dict)
    events: list[dict[str, JsonValue]] = Field(default_factory=list)
    links: list[dict[str, JsonValue]] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_duration(self) -> "Span":
        if self.endTimeUnixNano < self.startTimeUnixNano:
            raise ValueError("Span end precedes start")
        return self


class Point(OTLPModel):
    timeUnixNano: Timestamp
    attributes: list[Attribute] = Field(default_factory=list)
    asDouble: float | None = Field(default=None, allow_inf_nan=False)
    asInt: int | None = None
    sum: float | None = Field(default=None, allow_inf_nan=False)
    count: int | None = Field(default=None, ge=0)
    bucketCounts: list[int] = Field(default_factory=list)
    explicitBounds: list[float] = Field(default_factory=list)


class MetricData(OTLPModel):
    dataPoints: list[Point] = Field(default_factory=list)


class Metric(OTLPModel):
    name: str
    gauge: MetricData | None = None
    sum: MetricData | None = None
    histogram: MetricData | None = None
    exponentialHistogram: MetricData | None = None

    @model_validator(mode="after")
    def one_data(self) -> "Metric":
        if (
            sum(
                getattr(self, key) is not None
                for key in ("gauge", "sum", "histogram", "exponentialHistogram")
            )
            != 1
        ):
            raise ValueError("Metric must contain exactly one supported data type")
        return self


class Scope(OTLPModel):
    logRecords: list[LogRecord] = Field(default_factory=list)
    spans: list[Span] = Field(default_factory=list)
    metrics: list[Metric] = Field(default_factory=list)


class Batch(OTLPModel):
    resource: Resource = Field(default_factory=Resource)
    scopeLogs: list[Scope] = Field(default_factory=list)
    scopeSpans: list[Scope] = Field(default_factory=list)
    scopeMetrics: list[Scope] = Field(default_factory=list)


class Envelope(OTLPModel):
    resourceLogs: list[Batch] = Field(default_factory=list)
    resourceSpans: list[Batch] = Field(default_factory=list)
    resourceMetrics: list[Batch] = Field(default_factory=list)


def attributes(items: list[Attribute]) -> dict[str, JsonValue]:
    """Decode protocol AnyValue objects into recursive JSON data."""
    return {item.key: item.value.native() for item in items}


def ts(nano: int) -> datetime:
    return datetime.fromtimestamp(nano // 1_000_000_000, UTC) + timedelta(
        microseconds=(nano % 1_000_000_000) // 1000
    )


def stable_id(row: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(row, sort_keys=True, default=str).encode()).hexdigest()


def normalize(
    kind: str, payload: dict[str, Any], *, emails: bool = True
) -> dict[str, list[dict[str, Any]]]:
    """Validate an entire batch before returning sanitized rows for a single transaction."""
    envelope = Envelope.model_validate(payload)
    batch_key, scope_key = {
        "logs": ("resourceLogs", "scopeLogs"),
        "traces": ("resourceSpans", "scopeSpans"),
        "metrics": ("resourceMetrics", "scopeMetrics"),
    }[kind]
    if batch_key not in payload:
        raise ValueError(f"Missing {batch_key}")
    result: dict[str, list[dict[str, Any]]] = {kind: [], "events": []}
    for batch in getattr(envelope, batch_key):
        resource = attributes(batch.resource.attributes)
        service = resource.get("service.name")
        if not isinstance(service, str) or not service:
            raise ValueError("resource service.name is required")
        for scope in getattr(batch, scope_key):
            records = getattr(
                scope, {"logs": "logRecords", "traces": "spans", "metrics": "metrics"}[kind]
            )
            for record in records:
                raw: dict[str, JsonValue] = {
                    "resource": resource,
                    "record": record.model_dump(mode="json", exclude_none=True),
                }
                clean, markers = redact(raw, emails=emails)
                assert isinstance(clean, dict)
                clean_resource = clean["resource"]
                assert isinstance(clean_resource, dict)
                sanitized = type(record).model_validate(clean["record"])
                attrs = (
                    {**clean_resource, **attributes(sanitized.attributes)}
                    if kind != "metrics"
                    else clean_resource
                )
                base: dict[str, Any] = {
                    "service": clean_resource["service.name"],
                    "redactions": markers,
                }
                if kind == "logs":
                    body = sanitized.body.native()
                    row = {
                        **base,
                        "ts": ts(sanitized.timeUnixNano or sanitized.observedTimeUnixNano),
                        "severity": sanitized.severityText or str(sanitized.severityNumber),
                        "body": body if isinstance(body, str) else json.dumps(body),
                        "trace_id": sanitized.traceId.lower(),
                        "span_id": sanitized.spanId.lower(),
                        "attributes_json": attrs,
                        "container": attrs.get("container.name", attrs.get("host.name")),
                    }
                    row["id"] = stable_id(row)
                    result[kind].append(row)
                    if attrs.get("event.domain") in ("runtime", "deployment"):
                        event_ns = attrs.get("event.timestamp_ns")
                        event_ts = (
                            ts(event_ns)
                            if isinstance(event_ns, int) and event_ns > 0
                            else row["ts"]
                        )
                        event = {
                            **base,
                            "service": attrs.get("container.name", base["service"]),
                            "ts": event_ts,
                            "event_domain": attrs["event.domain"],
                            "event_name": attrs.get("event.name", "unknown"),
                            "attributes_json": attrs,
                        }
                        event["id"] = stable_id(event)
                        result["events"].append(event)
                elif kind == "traces":
                    attrs = {
                        **attrs,
                        "span.events": sanitized.events,
                        "span.links": sanitized.links,
                        "span.status": sanitized.status,
                    }
                    result[kind].append(
                        {
                            **base,
                            "trace_id": sanitized.traceId.lower(),
                            "span_id": sanitized.spanId.lower(),
                            "parent_span_id": sanitized.parentSpanId.lower(),
                            "operation": sanitized.name,
                            "status": str(sanitized.status.get("code", 0)),
                            "start_ts": ts(sanitized.startTimeUnixNano),
                            "duration_ms": (sanitized.endTimeUnixNano - sanitized.startTimeUnixNano)
                            / 1e6,
                            "attributes_json": attrs,
                        }
                    )
                else:
                    for key in ("gauge", "sum", "histogram", "exponentialHistogram"):
                        data = getattr(sanitized, key)
                        if data is None:
                            continue
                        for point in data.dataPoints:
                            if key in ("gauge", "sum") and (
                                (point.asDouble is None) == (point.asInt is None)
                            ):
                                raise ValueError("Numeric point needs exactly one scalar value")
                            if key in ("histogram", "exponentialHistogram") and point.count is None:
                                raise ValueError("Histogram count is required")
                            labels = {**attrs, **attributes(point.attributes)}
                            values = [
                                (
                                    sanitized.name,
                                    point.asDouble if point.asDouble is not None else point.asInt,
                                )
                            ]
                            if "Histogram" in key or key == "histogram":
                                labels = {
                                    **labels,
                                    "histogram": point.model_dump(mode="json", exclude_none=True),
                                }
                                values = [
                                    (sanitized.name + ".sum", point.sum),
                                    (sanitized.name + ".count", point.count),
                                ]
                            for name, value in values:
                                if value is None:
                                    continue
                                row = {
                                    **base,
                                    "ts": ts(point.timeUnixNano),
                                    "metric_name": name,
                                    "value": float(value),
                                    "labels_json": labels,
                                }
                                row["id"] = stable_id(row)
                                result[kind].append(row)
    return result
