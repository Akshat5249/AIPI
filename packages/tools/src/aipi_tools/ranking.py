"""Telemetry-only relevance tiers and deterministic capped candidate selection."""

from collections.abc import Sequence

from aipi_telemetry.evidence import Evidence

RETRIEVAL_VERSION = "relevance-v1"
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
)
ERROR_SEVERITIES = ("ERROR", "FATAL", "WARN", "WARNING")


def relevance(item: Evidence, error_trace_ids: frozenset[str] = frozenset()) -> int:
    """Use names/severity only; value, status, age, and causal labels never rank."""
    if item.type == "event" and item.payload.get("event_name") in RUNTIME_NAMES:
        return 0
    if item.type == "metric" and item.payload.get("metric_name") in RULE_METRICS:
        return 1
    if item.type == "log" and item.payload.get("severity") in ERROR_SEVERITIES:
        return 2
    if item.type == "trace" and item.payload.get("trace_id") in error_trace_ids:
        # A trace inherits only the severity of a linked, scoped log.
        return 2
    return 3


def rank_candidates(items: Sequence[Evidence]) -> tuple[tuple[int, Evidence], ...]:
    """Pure counterpart to SQL ranking, useful for offline captured telemetry."""
    linked = frozenset(
        str(item.payload["trace_id"])
        for item in items
        if item.type == "log"
        and item.payload.get("trace_id")
        and item.payload.get("severity") in ERROR_SEVERITIES
    )
    return tuple((relevance(item, linked), item) for item in items)


def select_ranked(
    candidates: Sequence[tuple[int, Evidence]], limit: int = 50
) -> tuple[Evidence, ...]:
    """The same stable relevance/time/source key is used before and after SQL caps."""
    if not 1 <= limit <= 50:
        raise ValueError("Evidence cap must be between 1 and 50")
    ordered = sorted(
        candidates, key=lambda entry: (entry[0], entry[1].timestamp, entry[1].source_ref)
    )
    return tuple(item for _, item in ordered[:limit])
