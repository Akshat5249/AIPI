"""Deterministic entailment for the MVP claim vocabulary; no model judges itself."""

from aipi_agents.reasoning import http_status, is_metric, request_symptom
from aipi_telemetry.evidence import Evidence
from aipi_tools.correlators import RULES, value


def feature(e: Evidence, name: str) -> bool:
    attributes = e.payload.get("attributes_json")
    attributes = attributes if isinstance(attributes, dict) else {}
    return {
        "die_137": e.type == "event"
        and e.payload.get("event_name") == "die"
        and str(attributes.get("exit_code")) == "137",
        "recovery": e.type == "event" and e.payload.get("event_name") in {"start", "restart"},
        "http_5xx": is_metric(e, "requests_total")
        and value(e) > 0
        and http_status(e) in {"500", "502", "503", "504"},
        "failed_span": e.type == "trace"
        and str(e.payload.get("status")) in {"2", "STATUS_CODE_ERROR"},
        "gateway_error": e.type == "log"
        and e.service == "gateway"
        and e.payload.get("severity") in {"ERROR", "FATAL"},
        "lag_seconds": is_metric(e, "replica_lag_seconds") and value(e) > 2,
        "wal_backlog": is_metric(e, "replica_lag_bytes") and value(e) > 0,
        "replay_paused": is_metric(e, "replica_replay_paused") and value(e) == 1,
        "healthy_primary": is_metric(e, "primary_healthy")
        and value(e, "min") == value(e, "max") == 1,
        "stale_read": e.type == "log"
        and "stale replica read" in str(e.payload.get("body", e.summary)).lower(),
        "timeout": e.type in {"log", "trace"} and "timeout" in str(e.payload).lower(),
    }.get(name, False)


def hypothesis_support(category: str, e: Evidence, stance: str) -> bool:
    if stance == "against":
        if category == "primary_outage":
            return feature(e, "healthy_primary")
        if category == "dependency":
            return feature(e, "die_137") or feature(e, "replay_paused")
        if category == "replica_lag":
            return is_metric(e, "primary_healthy") and value(e, "min") != 1
        return False
    if category == "termination":
        return (
            e.type == "event"
            and e.payload.get("event_name") in {"die", "start", "restart"}
            or feature(e, "http_5xx")
            or feature(e, "failed_span")
            or e.type == "log"
            and e.payload.get("severity") in {"ERROR", "FATAL"}
        )
    if category == "replica_lag":
        return any(
            feature(e, name)
            for name in ("lag_seconds", "wal_backlog", "replay_paused", "stale_read", "timeout")
        )
    if category in {"primary_outage", "dependency"}:
        return request_symptom(e)
    return False


def fact_support(text: str, items: tuple[Evidence, ...]) -> set[str]:
    # A conjunction is supported by its witnesses, not by any arbitrary existing ID.
    for rule in RULES:
        for signal in rule(items):
            if text == signal.statement:
                return set(signal.evidence_ids)
    return set()


STATEMENTS = {
    "termination": "Checkout service process terminated",
    "replica_lag": "Replica WAL replay paused, causing replication lag and stale reads",
    "primary_outage": "Primary outage caused read failures",
    "dependency": "Downstream dependency failure caused request symptoms",
    "insufficient": "Insufficient evidence to establish a root cause",
}
RECOMMENDATION = (
    "Review scoped lifecycle, replay and dependency evidence "
    "with the service owner before any remediation"
)
