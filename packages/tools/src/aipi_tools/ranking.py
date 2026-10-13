"""Telemetry-only relevance tiers and deterministic capped candidate selection."""

from collections.abc import Sequence

from aipi_telemetry.evidence import Evidence

RETRIEVAL_VERSION = "series-floors-v2"
RUNTIME_NAMES = ("die", "start", "restart", "deploy")
RULE_METRICS = (
    "replica_lag_seconds",
    "replica_lag_bytes",
    "replica_replay_paused",
    "primary_healthy",
    "requests_total",
    "error_rate",
    "latency_p95",
    "request_duration_ms",
    "request_duration_ms.sum",
    "request_duration_ms.count",
)
ERROR_SEVERITIES = ("ERROR", "FATAL", "WARN", "WARNING")


SLOW_TRACE_MS = 250.0
SEVERITY_ORDER = {"FATAL": 0, "ERROR": 1, "WARN": 2, "WARNING": 2}


def error_or_slow(item: Evidence) -> bool:
    duration = item.payload.get("duration_ms", 0)
    return item.type == "trace" and (
        str(item.payload.get("status")) in {"2", "STATUS_CODE_ERROR"}
        or isinstance(duration, (float, int))
        and duration >= SLOW_TRACE_MS
    )


def severity(item: Evidence, linked: dict[str, int] | None = None) -> int:
    if item.type == "log":
        return SEVERITY_ORDER.get(str(item.payload.get("severity")), 3)
    if item.type == "trace":
        inherited = (linked or {}).get(str(item.payload.get("trace_id")), 3)
        if str(item.payload.get("status")) in {"2", "STATUS_CODE_ERROR"}:
            inherited = min(inherited, 1)
        duration = item.payload.get("duration_ms", 0)
        if isinstance(duration, (float, int)) and duration >= SLOW_TRACE_MS:
            inherited = min(inherited, 2)
        return inherited
    return 3


def relevance(item: Evidence, error_trace_ids: frozenset[str] = frozenset()) -> int:
    """Fixed names, severity and error/slow trace features; never causal labels."""
    if item.type == "event" and item.payload.get("event_name") in RUNTIME_NAMES:
        return 0
    if item.type == "metric" and item.payload.get("metric_name") in RULE_METRICS:
        return 1
    if severity(item, dict.fromkeys(error_trace_ids, 1)) < 3:
        return 2
    return 3


def rank_candidates(items: Sequence[Evidence]) -> tuple[tuple[int, Evidence], ...]:
    linked = frozenset(
        str(item.payload["trace_id"])
        for item in items
        if item.type == "log" and item.payload.get("trace_id") and severity(item) < 3
    )
    return tuple((relevance(item, linked), item) for item in items)


def select_ranked(
    candidates: Sequence[tuple[int, Evidence]], limit: int = 50
) -> tuple[Evidence, ...]:
    """Reserve up to ten severe logs and five error/slow traces within the cap."""
    if not 1 <= limit <= 50:
        raise ValueError("Evidence cap must be between 1 and 50")
    linked: dict[str, int] = {}
    for _, item in candidates:
        if item.type == "log" and item.payload.get("trace_id"):
            key = str(item.payload["trace_id"])
            linked[key] = min(linked.get(key, 3), severity(item))
    ordered = sorted(
        candidates,
        key=lambda entry: (
            entry[0],
            severity(entry[1], linked),
            entry[1].timestamp,
            entry[1].source_ref,
        ),
    )
    logs = [e for _, e in ordered if e.type == "log" and severity(e) < 3][:10]
    traces = [e for _, e in ordered if error_or_slow(e)][:5]
    reserved = (logs + traces)[:limit]
    protected = [e for rank, e in ordered if rank < 2][: limit - len(reserved)]
    chosen = {e.evidence_id for e in protected + reserved}
    for _, item in ordered:
        if len(chosen) >= limit:
            break
        chosen.add(item.evidence_id)
    return tuple(e for _, e in ordered if e.evidence_id in chosen)
