"""Repeated-run distributions use population variance; never hide individual misses."""

import statistics

from aipi_evaluation.contracts import Scorecard


def summarize(cards: list[Scorecard]) -> dict[str, object]:
    result: dict[str, object] = {
        "runs": len(cards),
        "passed": sum(c.passed for c in cards),
        "misses": [c.model_dump(mode="json") for c in cards if not c.passed],
    }
    metrics = {}
    for key in (
        "top1",
        "top3_recall",
        "evidence_precision",
        "evidence_coverage",
        "unsupported_claim_rate",
        "contradiction_handling",
        "latency_ms",
        "useful_evidence_per_tool_call",
    ):
        samples = [float(getattr(c.scores, key)) for c in cards]
        if samples:
            metrics[key] = {
                "samples": samples,
                "mean": statistics.mean(samples),
                "median": statistics.median(samples),
                "min": min(samples),
                "max": max(samples),
                "variance": statistics.pvariance(samples),
                "stddev": statistics.pstdev(samples),
            }
    result["metrics"] = metrics
    return result
