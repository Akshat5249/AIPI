"""Evidence-backed report assembly, full citation validation and exactly one repair."""

import re
from collections.abc import Callable

from aipi_telemetry.evidence import build_timeline
from pydantic import ValidationError

from aipi_agents.schemas import (
    AgentInput,
    Claim,
    Hypothesis,
    Recommendation,
    Report,
    RootCause,
    cited_ids,
)


class ReportValidationError(Exception):
    pass


def template(context: AgentInput, ranked: tuple[Hypothesis, ...]) -> Report:
    claims = []
    for i, result in enumerate(context.signals):
        if result.evidence_ids:
            claims.append(
                Claim(
                    claim_id=f"fact_{i}",
                    kind="fact",
                    text=result.statement,
                    evidence_ids=result.evidence_ids,
                )
            )
    for h in ranked:
        citations = h.for_ids + h.against
        if citations:
            claims.append(
                Claim(
                    claim_id=h.id,
                    kind="hypothesis",
                    text=h.statement,
                    evidence_ids=tuple(dict.fromkeys(citations)),
                )
            )
    recs: tuple[Recommendation, ...] = ()
    if ranked[0].for_ids:
        recs = (
            Recommendation(
                id="rec_review",
                statement=(
                    "Review scoped lifecycle, replay and dependency evidence "
                    "with the service owner before any remediation"
                ),
                evidence_ids=ranked[0].for_ids
                + tuple(e.evidence_id for e in context.items if e.type == "runbook")[:1],
            ),
        )
        claims.append(
            Claim(
                claim_id="rec_review",
                kind="recommendation",
                text=recs[0].statement,
                evidence_ids=recs[0].evidence_ids,
            )
        )
    facts = "\n".join(
        f"- {c.text} [{', '.join(c.evidence_ids)}]" for c in claims if c.kind == "fact"
    )
    hypotheses = "\n".join(
        (
            f"- {h.rank}. {h.statement} (confidence {h.confidence:.3f}); "
            f"FOR [{', '.join(h.for_ids)}]; AGAINST [{', '.join(h.against)}]; "
            f"missing: {'; '.join(h.missing) or 'No contrary observation found'}"
        )
        for h in ranked
    )
    recommendations = "\n".join(
        f"- {r.statement}. Requires human approval [{', '.join(r.evidence_ids)}]" for r in recs
    )
    return Report(
        root_cause=RootCause(
            statement=ranked[0].statement,
            hypothesis_id=ranked[0].id,
            confidence=ranked[0].confidence,
        ),
        claims=tuple(claims),
        timeline=build_timeline(
            tuple(
                e
                for e in context.items
                if e.evidence_id in {eid for h in ranked for eid in h.for_ids + h.against}
            )
        ),
        ranked_hypotheses=ranked,
        unresolved_questions=tuple(dict.fromkeys(q for h in ranked for q in h.missing)),
        recommendations=recs,
        markdown=(
            f"## Facts\n{facts}\n\n## Hypotheses\n{hypotheses}\n"
            f"\n## Recommendations\n{recommendations}\n"
        ),
    )


def validate_report(report: Report, context: AgentInput) -> None:
    markdown_ids = set(re.findall(r"ev_[A-Za-z0-9_]+", report.markdown))
    if not markdown_ids <= cited_ids(report):
        raise ReportValidationError("Markdown references unregistered evidence")
    if not cited_ids(report) <= {e.evidence_id for e in context.items}:
        raise ReportValidationError("Report references unknown or out-of-scope evidence")


def write_report(
    context: AgentInput,
    ranked: tuple[Hypothesis, ...],
    producer: Callable[[Report, bool], object] | None = None,
) -> tuple[Report, int]:
    canonical = template(context, ranked)
    for attempt in range(2):
        try:
            candidate = producer(canonical, bool(attempt)) if producer else canonical.model_dump()
            report = Report.model_validate(candidate)
            validate_report(report, context)
            if (
                report.ranked_hypotheses != ranked
                or report.recommendations != canonical.recommendations
            ):
                raise ReportValidationError("Report changed verified ranking or read-only checks")
            return report, attempt + 1
        except (ValidationError, ReportValidationError) as exc:
            if attempt:
                raise ReportValidationError("Report invalid after one repair") from exc
    raise AssertionError("Unreachable")
