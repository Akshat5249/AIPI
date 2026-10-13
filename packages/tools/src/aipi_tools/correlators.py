"""Five pure, evidence-citing rules; correlation never consults causal labels."""

import json
from collections.abc import Callable
from typing import Literal

from aipi_telemetry.evidence import Evidence
from pydantic import BaseModel, ConfigDict


class Signal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    rule: str
    statement: str
    stance: Literal["for", "against"] = "for"
    kind: Literal["observation", "false_lead", "contradiction"] = "observation"
    evidence_ids: tuple[str, ...]
    contradicts: str | None = None


def metric(item: Evidence, name: str) -> bool:
    return item.type == "metric" and item.payload.get("metric_name") == name


def value(item: Evidence, aggregate: str = "max") -> float:
    number = item.payload.get(aggregate, item.payload.get("value"))
    return float(number) if isinstance(number, (int, float)) else 0


def signal(rule: str, statement: str, items: tuple[Evidence, ...], **kwargs: object) -> Signal:
    return Signal.model_validate(
        {
            "rule": rule,
            "statement": statement,
            "evidence_ids": sorted({item.evidence_id for item in items}),
            **kwargs,
        }
    )


class ProcessExitRule:
    @staticmethod
    def apply(items: tuple[Evidence, ...]) -> tuple[Signal, ...]:
        exits = tuple(
            e for e in items if e.type == "event" and e.payload.get("event_name") == "die"
        )
        errors = tuple(
            e
            for e in items
            if metric(e, "requests_total")
            and value(e) > 0
            and isinstance(labels := e.payload.get("labels_json"), dict)
            and str(labels.get("status")) in {"500", "502", "503", "504"}
        )
        spans = tuple(
            e
            for e in items
            if e.type == "trace" and str(e.payload.get("status")) in {"2", "STATUS_CODE_ERROR"}
        )
        if exits and errors and spans:
            return (
                signal(
                    "ProcessExitRule",
                    "Service terminated with correlated HTTP failures",
                    exits + errors + spans,
                ),
            )
        return ()


class ErrorSpikeRule:
    @staticmethod
    def apply(items: tuple[Evidence, ...]) -> tuple[Signal, ...]:
        # Compare the same metric series/service within the scoped window.
        for name in ("error_rate", "latency_p95", "request_duration_ms"):
            groups: dict[tuple[str, str], list[Evidence]] = {}
            for item in items:
                if metric(item, name):
                    key = (
                        item.service,
                        json.dumps(item.payload.get("labels_json", {}), sort_keys=True),
                    )
                    groups.setdefault(key, []).append(item)
            for key in sorted(groups):
                samples = sorted(groups[key], key=lambda e: (e.timestamp, e.evidence_id))
                if len(samples) == 1 and samples[0].payload.get("aggregation") == "series_summary":
                    item = samples[0]
                    if (
                        isinstance(item.payload["sample_count"], int)
                        and item.payload["sample_count"] >= 2
                        and value(item, "last") > value(item, "first") * 2
                        and value(item, "last") > 0
                    ):
                        return (
                            signal(
                                "ErrorSpikeRule", f"{name} exceeds early-window baseline", (item,)
                            ),
                        )
                if len(samples) >= 2:
                    first, last = samples[0], samples[-1]
                    if value(last) > value(first) * 2 and value(last) > 0:
                        return (
                            signal(
                                "ErrorSpikeRule",
                                f"{name} exceeds early-window baseline",
                                (first, last),
                            ),
                        )
        for service in sorted({item.service for item in items if item.type == "trace"}):
            spans = sorted(
                (e for e in items if e.type == "trace" and e.service == service),
                key=lambda e: (e.timestamp, e.evidence_id),
            )
            if len(spans) >= 4:
                half = len(spans) // 2

                def rate(group: list[Evidence]) -> float:
                    return sum(
                        str(e.payload.get("status")) in {"2", "STATUS_CODE_ERROR"} for e in group
                    ) / len(group)

                if rate(spans[half:]) - rate(spans[:half]) >= 0.25:
                    return (
                        signal(
                            "ErrorSpikeRule",
                            "Failed-span rate rises versus early-window baseline",
                            tuple(spans),
                        ),
                    )
        # Latency compares matching operations, never a mix of HTTP and DB spans.
        groups_latency: dict[tuple[str, str], list[Evidence]] = {}
        for item in items:
            if item.type == "trace":
                key = (item.service, str(item.payload.get("operation", "")))
                groups_latency.setdefault(key, []).append(item)
        for key in sorted(groups_latency):
            samples = sorted(groups_latency[key], key=lambda e: (e.timestamp, e.source_ref))
            if len(samples) < 4:
                continue
            half = len(samples) // 2

            def p95(group: list[Evidence]) -> float:
                values = sorted(
                    float(str(e.payload.get("duration_ms", 0)))
                    for e in group
                    if isinstance(e.payload.get("duration_ms", 0), (float, int))
                )
                return values[min(len(values) - 1, int(len(values) * 0.95))] if values else 0

            baseline, later = p95(samples[:half]), p95(samples[half:])
            if baseline > 0 and later >= 250 and later > baseline * 2:
                return (
                    signal(
                        "ErrorSpikeRule",
                        "Span latency p95 rises versus early-window baseline",
                        tuple(samples),
                    ),
                )
        return ()


class ReplicaLagRule:
    @staticmethod
    def apply(items: tuple[Evidence, ...]) -> tuple[Signal, ...]:
        lag = tuple(e for e in items if metric(e, "replica_lag_seconds") and value(e) > 2)
        backlog = tuple(e for e in items if metric(e, "replica_lag_bytes") and value(e) > 0)
        paused = tuple(e for e in items if metric(e, "replica_replay_paused") and value(e) == 1)
        health = tuple(e for e in items if metric(e, "primary_healthy"))
        if (
            lag
            and backlog
            and paused
            and health
            and all(value(e, "min") == value(e, "max") == 1 for e in health)
        ):
            return (
                signal(
                    "ReplicaLagRule",
                    "Replica replay paused with WAL backlog and healthy primary",
                    lag + backlog + paused + health,
                ),
            )
        return ()


class DownstreamTimeoutRule:
    @staticmethod
    def apply(items: tuple[Evidence, ...]) -> tuple[Signal, ...]:
        symptoms = tuple(
            e
            for e in items
            if e.type in {"log", "trace"}
            and ("timeout" in str(e.payload).lower() or "stale replica read" in e.summary.lower())
        )
        if symptoms:
            return (
                signal(
                    "DownstreamTimeoutRule",
                    "Downstream timeout or stale-read symptom; cause unproven",
                    symptoms,
                    kind="false_lead",
                ),
            )
        return ()


class PrimaryHealthRule:
    @staticmethod
    def apply(items: tuple[Evidence, ...]) -> tuple[Signal, ...]:
        health = tuple(e for e in items if metric(e, "primary_healthy"))
        if health and all(value(e, "min") == value(e, "max") == 1 for e in health):
            return (
                signal(
                    "PrimaryHealthRule",
                    "Observed primary health contradicts primary outage",
                    health,
                    stance="against",
                    kind="contradiction",
                    contradicts="primary outage",
                ),
            )
        return ()


RULES: tuple[Callable[[tuple[Evidence, ...]], tuple[Signal, ...]], ...] = (
    ProcessExitRule.apply,
    ErrorSpikeRule.apply,
    ReplicaLagRule.apply,
    DownstreamTimeoutRule.apply,
    PrimaryHealthRule.apply,
)


def correlate(items: tuple[Evidence, ...]) -> tuple[Signal, ...]:
    return tuple(result for rule in RULES for result in rule(items))
