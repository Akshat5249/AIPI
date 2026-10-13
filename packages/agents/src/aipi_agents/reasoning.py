"""Pure verification and ranking grounded in observable evidence, not fixture labels."""

from aipi_telemetry.evidence import Evidence
from aipi_tools.correlators import value

from aipi_agents.schemas import AgentInput, Hypothesis, Proposal
from aipi_agents.scoring_config import ScoreFeatures, confidence


def http_status(e: Evidence) -> str:
    labels = e.payload.get("labels_json")
    return str(labels.get("status")) if isinstance(labels, dict) else ""


def is_metric(e: Evidence, name: str) -> bool:
    return e.type == "metric" and e.payload.get("metric_name") == name


def request_symptom(e: Evidence) -> bool:
    if e.type not in {"log", "trace"}:
        return False
    return (
        "timeout" in str(e.payload).lower()
        or "stale replica read" in e.summary.lower()
        or e.payload.get("severity") in {"ERROR", "FATAL"}
        or str(e.payload.get("status")) in {"2", "STATUS_CODE_ERROR"}
    )


def verify(proposal: Proposal, context: AgentInput) -> Hypothesis:
    rules = {s.rule for s in context.signals}
    items = sorted(context.items, key=lambda e: (e.timestamp, e.source_ref))
    for_items: list[Evidence] = []
    against: list[Evidence] = []
    missing: list[str] = []
    if proposal.category == "termination":
        for_items = [
            e
            for e in items
            if e.type == "event"
            and e.payload.get("event_name") in {"die", "start", "restart"}
            or is_metric(e, "requests_total")
            and value(e) > 0
            and http_status(e) in {"500", "502", "503", "504"}
            or e.type == "trace"
            and str(e.payload.get("status")) in {"2", "STATUS_CODE_ERROR"}
            or e.type == "log"
            and e.payload.get("severity") in {"ERROR", "FATAL"}
        ]
        if "ProcessExitRule" not in rules:
            missing.append("Correlated exit, HTTP failure and failed-span check")
    elif proposal.category == "replica_lag":
        for_items = [
            e
            for e in items
            if is_metric(e, "replica_lag_seconds")
            and value(e) > 2
            or is_metric(e, "replica_lag_bytes")
            and value(e) > 0
            or is_metric(e, "replica_replay_paused")
            and value(e) == 1
            or e.type == "log"
            and "stale replica read" in e.summary.lower()
            or e.type == "trace"
            and "timeout" in str(e.payload).lower()
        ]
        against = [e for e in items if is_metric(e, "primary_healthy") and value(e, "min") != 1]
        if "ReplicaLagRule" not in rules:
            missing.append("Pause, lag, WAL backlog and healthy-primary conjunction")
    elif proposal.category == "primary_outage":
        for_items = [e for e in items if request_symptom(e)]
        against = [
            e
            for e in items
            if is_metric(e, "primary_healthy") and value(e, "min") == value(e, "max") == 1
        ]
        missing.append("Direct primary failure evidence; read symptoms are nonspecific")
    elif proposal.category == "dependency":
        for_items = [e for e in items if request_symptom(e)]
        against = [
            e
            for e in items
            if e.type == "event"
            and e.payload.get("event_name") == "die"
            or is_metric(e, "replica_replay_paused")
            and value(e) == 1
        ]
        missing.append("Independent dependency failure beyond secondary request symptoms")
    else:
        missing.append("Direct causal evidence inside the authorized incident boundary")

    # Keep one observation per type/metric/event family, not every repeated sample.
    def witnesses(evidence: list[Evidence]) -> tuple[str, ...]:
        found: dict[tuple[str, str], str] = {}
        for e in evidence:
            family = (e.type, str(e.payload.get("metric_name", e.payload.get("event_name", ""))))
            found.setdefault(family, e.evidence_id)
        return tuple(found.values())

    return Hypothesis.model_validate(
        {
            **proposal.model_dump(),
            "for": witnesses(for_items),
            "against": witnesses(against),
            "missing": tuple(missing),
        }
    )


def rank(hypotheses: tuple[Hypothesis, ...], context: AgentInput) -> tuple[Hypothesis, ...]:
    rules = {s.rule for s in context.signals}
    scored = []
    for h in hypotheses:
        direct = (
            h.category == "termination"
            and "ProcessExitRule" in rules
            or h.category == "replica_lag"
            and "ReplicaLagRule" in rules
        )
        features = ScoreFeatures(
            evidence_coverage=1 if direct else 0.4 if h.for_ids else 0,
            causal_proximity=1 if direct else 0.2 if h.for_ids else 0,
            retrieval_quality=0.8 if context.truncated else 1,
            deterministic_check_score=1 if direct else 0,
            n_material_contradicting_evidence=len(set(h.against)),
        )
        if not h.for_ids:
            features = features.model_copy(update={"retrieval_quality": 0})
        scored.append(h.model_copy(update={"confidence": confidence(features)}))
    ordered = sorted(scored, key=lambda h: (-h.confidence, h.category != "insufficient", h.id))
    return tuple(h.model_copy(update={"rank": i}) for i, h in enumerate(ordered, 1))
