"""Pure metric scoring with a private oracle and observable report/evidence inputs."""

from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import UUID

from aipi_agents.schemas import Report, cited_ids
from aipi_telemetry.evidence import Evidence

from aipi_evaluation.claims import feature
from aipi_evaluation.contracts import Experiment, ScenarioID, Scorecard, Scores
from aipi_evaluation.hallucination import hallucination_gate
from aipi_evaluation.oracle import Truth


def score(
    scenario_id: ScenarioID,
    truth: Truth,
    report: Report,
    evidence: Mapping[str, Evidence],
    experiment: Experiment,
    latency_ms: float,
    tool_calls: int,
    tokens: int,
    mode: str = "golden",
    investigation_id: UUID | None = None,
) -> Scorecard:
    gate = hallucination_gate(report, evidence)
    ids = cited_ids(report)
    covered = tuple(
        name
        for name in truth.required_features
        if any(feature(evidence[eid], name) for eid in ids if eid in evidence)
    )
    top1 = float(report.ranked_hypotheses[0].category == truth.expected_category)
    top3 = float(any(h.category == truth.expected_category for h in report.ranked_hypotheses[:3]))
    primary = next((h for h in report.ranked_hypotheses if h.category == "primary_outage"), None)
    if truth.expected_category == "replica_lag":
        contradiction = float(
            bool(
                primary
                and primary.rank > 1
                and primary.against
                and any(
                    eid in evidence and feature(evidence[eid], "healthy_primary")
                    for eid in primary.against
                )
            )
        )
    else:
        contradiction = float(
            any(
                h.rank > 1
                and any(eid in evidence and feature(evidence[eid], "die_137") for eid in h.against)
                for h in report.ranked_hypotheses
            )
        )
    scores = Scores(
        top1=top1,
        top3_recall=top3,
        evidence_precision=gate.supported_pairs / gate.citation_pairs if gate.citation_pairs else 0,
        evidence_coverage=len(covered) / len(truth.required_features),
        unsupported_claim_rate=gate.unsupported_claims / gate.material_claims
        if gate.material_claims
        else 0,
        contradiction_handling=contradiction,
        latency_ms=latency_ms,
        useful_evidence_per_tool_call=len(gate.useful_ids) / tool_calls if tool_calls else 0,
        useful_evidence_per_token=len(gate.useful_ids) / tokens if tokens else None,
        citation_pairs=gate.citation_pairs,
        supported_pairs=gate.supported_pairs,
        material_claims=gate.material_claims,
        unsupported_claims=gate.unsupported_claims,
        critical_unsupported_claims=gate.critical_unsupported_claims,
        covered_features=covered,
        required_feature_count=len(truth.required_features),
        tool_calls=tool_calls,
        tokens=tokens,
    )
    failures = tuple(sorted(set(v.code for v in gate.violations)))
    if not top1:
        failures += ("TOP1_MISS",)
    if len(covered) < len(truth.required_features):
        failures += ("EVIDENCE_COVERAGE_MISS",)
    if scores.evidence_precision < 0.9:
        failures += ("EVIDENCE_PRECISION_MISS",)
    if not contradiction:
        failures += ("CONTRADICTION_MISS",)
    return Scorecard.model_validate(
        dict(
            scenario_id=scenario_id,
            passed=not failures,
            scores=scores,
            experiment=experiment,
            failures=failures,
            mode=mode,
            investigation_id=investigation_id,
            created_at=datetime.now(UTC),
        )
    )
