"""Pure scoped citation/entailment/quotation gate; no database, network or truth access."""

import math
import re
from collections.abc import Mapping

from aipi_agents.schemas import Report, cited_ids
from aipi_telemetry.evidence import Evidence
from aipi_tools.correlators import ProcessExitRule, ReplicaLagRule
from pydantic import JsonValue

from aipi_evaluation.claims import RECOMMENDATION, STATEMENTS, fact_support, hypothesis_support
from aipi_evaluation.contracts import Strict


class Violation(Strict):
    claim_id: str
    code: str
    critical: bool = True


class GateResult(Strict):
    violations: tuple[Violation, ...]
    citation_pairs: int
    supported_pairs: int
    material_claims: int
    unsupported_claims: int
    critical_unsupported_claims: int
    useful_ids: tuple[str, ...]


def leaves(value: JsonValue) -> tuple[str | float, ...]:
    if isinstance(value, dict):
        return tuple(x for v in value.values() for x in leaves(v))
    if isinstance(value, list):
        return tuple(x for v in value for x in leaves(v))
    if isinstance(value, (int, float)):
        return (float(value),)
    if isinstance(value, str):
        return (value,)
    return ()


def quotation_errors(text: str, items: tuple[Evidence, ...]) -> tuple[str, ...]:
    errors = []
    # Explicit field/value assertions bind to the same cited evidence record.
    number = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
    pattern = rf"\b([A-Za-z][\w.]*)[\"`]?\s*(?:=|:|\bis\b|\bwas\b)\s*[\"`]?({number})"
    assertions: list[tuple[str, str | None, str]] = [
        (m[0], None, m[1]) for m in re.findall(pattern, text)
    ]
    metric_names = sorted({str(e.payload["metric_name"]) for e in items if e.type == "metric"})
    for name in metric_names:
        qualified = (
            rf"\b{re.escape(name)}\s+(first|last|min|max|sample_count)"
            rf"\s*(?:=|:|is|was)\s*[\"`]?({number})"
        )
        assertions.extend((name, agg, raw) for agg, raw in re.findall(qualified, text))
    for key, aggregate, raw in assertions:
        if key in {"confidence", "rank"}:
            continue
        wanted = float(raw)
        possible: list[JsonValue] = []
        for e in items:
            if e.payload.get("metric_name") == key:
                fields = (aggregate,) if aggregate else ("value", "first", "last", "min", "max")
                possible.extend(e.payload.get(k) for k in fields)
            if not aggregate and key in e.payload:
                possible.append(e.payload[key])
            attributes = e.payload.get("attributes_json")
            if not aggregate and isinstance(attributes, dict) and key in attributes:
                possible.append(attributes[key])
        if not any(
            isinstance(v, (int, float, str))
            and re.fullmatch(number, str(v))
            and math.isclose(float(v), wanted, rel_tol=1e-9, abs_tol=1e-9)
            for v in possible
        ):
            errors.append("FABRICATED_VALUE")
    for identifier in re.findall(r"\b[0-9a-f]{32}\b", text):
        if not any(e.payload.get("trace_id") == identifier for e in items):
            errors.append("FABRICATED_TRACE")
    for key, quoted in re.findall(
        r"""\b(log(?: line)?|body|deploy(?:ment)?(?:_id| event))\s*(?:=|:)\s*["`]([^"`]+)["`]""",
        text,
        re.I,
    ):
        if key.lower().startswith(("log", "body")):
            valid = any(e.type == "log" and e.payload.get("body") == quoted for e in items)
        else:
            valid = any(
                e.type == "event"
                and e.payload.get("event_name") == "deploy"
                and quoted in leaves(e.payload)
                for e in items
            )
        if not valid:
            errors.append(
                "FABRICATED_LOG"
                if key.lower().startswith(("log", "body"))
                else "FABRICATED_DEPLOYMENT"
            )
    return tuple(sorted(set(errors)))


def hallucination_gate(report: Report, evidence: Mapping[str, Evidence]) -> GateResult:
    """Judge claims only against caller-supplied scoped immutable evidence records."""
    violations = []
    useful = set()
    pairs = 0
    supported = 0
    bad = set()
    hypotheses = {h.id: h for h in report.ranked_hypotheses}
    for eid in cited_ids(report) | set(re.findall(r"ev_[A-Za-z0-9_]+", report.markdown)):
        if eid not in evidence:
            violations.append(Violation(claim_id="report", code="UNKNOWN_EVIDENCE_ID"))
    for claim in report.claims:
        items = tuple(evidence[e] for e in claim.evidence_ids if e in evidence)
        allowed = set()
        if claim.kind == "fact":
            allowed = fact_support(claim.text, items)
        elif claim.kind == "hypothesis" and claim.claim_id in hypotheses:
            h = hypotheses[claim.claim_id]
            if claim.text == h.statement == STATEMENTS.get(h.category):
                allowed = {
                    e.evidence_id
                    for e in items
                    if (e.evidence_id in h.for_ids and hypothesis_support(h.category, e, "for"))
                    or (e.evidence_id in h.against and hypothesis_support(h.category, e, "against"))
                }
        elif claim.kind == "recommendation":
            rec = next((r for r in report.recommendations if r.id == claim.claim_id), None)
            if (
                rec
                and claim.text == rec.statement == RECOMMENDATION
                and rec.requires_approval
                and not rec.executed
            ):
                top = report.ranked_hypotheses[0]
                allowed = {
                    e.evidence_id
                    for e in items
                    if e.type == "runbook" or hypothesis_support(top.category, e, "for")
                }
        pairs += len(set(claim.evidence_ids))
        supported += sum(eid in allowed for eid in set(claim.evidence_ids))
        useful.update(allowed)
        errors = list(quotation_errors(claim.text, items))
        if not allowed or len(allowed) < len(set(claim.evidence_ids)):
            errors.append("UNSUPPORTED_CLAIM")
        if errors:
            bad.add(claim.claim_id)
            violations.extend(
                Violation(claim_id=claim.claim_id, code=code) for code in sorted(set(errors))
            )
    top = report.ranked_hypotheses[0]
    direct = tuple(evidence[eid] for eid in top.for_ids if eid in evidence)
    health = tuple(
        e
        for eid, e in evidence.items()
        if eid in cited_ids(report)
        and e.type == "metric"
        and e.payload.get("metric_name") == "primary_healthy"
    )
    supported_root = (
        top.category == "termination"
        and bool(ProcessExitRule.apply(direct))
        or top.category == "replica_lag"
        and bool(ReplicaLagRule.apply(direct + health))
        or top.category == "insufficient"
        and not direct
    )
    if not supported_root:
        violations.append(Violation(claim_id="root", code="UNSUPPORTED_ROOT_CAUSE"))
    for h in report.ranked_hypotheses:
        if h.statement != STATEMENTS.get(h.category):
            violations.append(Violation(claim_id=h.id, code="UNSUPPORTED_HYPOTHESIS"))
        for stance, ids in (("for", h.for_ids), ("against", h.against)):
            if any(
                eid not in evidence or not hypothesis_support(h.category, evidence[eid], stance)
                for eid in ids
            ):
                violations.append(Violation(claim_id=h.id, code="UNSUPPORTED_STANCE"))
    expected_lines = {"", "## Facts", "## Hypotheses", "## Recommendations"}
    expected_lines.update(
        f"- {c.text} [{', '.join(c.evidence_ids)}]" for c in report.claims if c.kind == "fact"
    )
    expected_lines.update(
        f"- {h.rank}. {h.statement} (confidence {h.confidence:.3f}); "
        f"FOR [{', '.join(h.for_ids)}]; AGAINST [{', '.join(h.against)}]; "
        f"missing: {'; '.join(h.missing) or 'No contrary observation found'}"
        for h in report.ranked_hypotheses
    )
    expected_lines.update(
        f"- {r.statement}. Requires human approval [{', '.join(r.evidence_ids)}]"
        for r in report.recommendations
    )
    if any(line not in expected_lines for line in report.markdown.splitlines()):
        violations.append(Violation(claim_id="markdown", code="UNSUPPORTED_MARKDOWN"))
    # Check all other claim surfaces, including Markdown, not just fact text.
    for item in report.timeline:
        cited = tuple(evidence[e] for e in item.evidence_ids if e in evidence)
        if not any(item.label == e.summary and item.ts == e.timestamp for e in cited):
            violations.append(Violation(claim_id="timeline", code="FABRICATED_TIMELINE"))
    surfaces = [(h.id, h.statement, h.for_ids + h.against) for h in report.ranked_hypotheses]
    surfaces += [("root", report.root_cause.statement, report.ranked_hypotheses[0].for_ids)]
    surfaces += [(r.id, r.statement, r.evidence_ids) for r in report.recommendations]
    surfaces += [
        (h.id, text, h.for_ids + h.against)
        for h in report.ranked_hypotheses
        for text in (h.falsification_condition,) + h.expected_evidence + h.missing
    ]
    surfaces += [
        ("question", text, tuple(cited_ids(report))) for text in report.unresolved_questions
    ]
    for key, text, ids in surfaces:
        for code in quotation_errors(text, tuple(evidence[e] for e in ids if e in evidence)):
            violations.append(Violation(claim_id=key, code=code))
    for line in report.markdown.splitlines():
        line_ids = re.findall(r"ev_[a-z0-9]+", line)
        for code in quotation_errors(line, tuple(evidence[e] for e in line_ids if e in evidence)):
            violations.append(Violation(claim_id="markdown", code=code))
    critical = {v.claim_id for v in violations if v.critical}
    return GateResult(
        violations=tuple(violations),
        citation_pairs=pairs,
        supported_pairs=supported,
        material_claims=len(report.claims),
        unsupported_claims=len(bad),
        critical_unsupported_claims=len(critical),
        useful_ids=tuple(sorted(useful)),
    )
