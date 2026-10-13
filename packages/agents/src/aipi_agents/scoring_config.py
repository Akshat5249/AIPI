"""Exact AIPI_CONTEXT section 8 confidence formula; no model confidence input."""

from pydantic import BaseModel, ConfigDict, Field

EVIDENCE_COVERAGE = 0.35
CAUSAL_PROXIMITY = 0.25
RETRIEVAL_QUALITY = 0.20
DETERMINISTIC_CHECK = 0.20
CONTRADICTION_WEIGHT = 0.15
MAX_CONTRADICTION_PENALTY = 0.45


class ScoreFeatures(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    evidence_coverage: float = Field(ge=0, le=1)
    causal_proximity: float = Field(ge=0, le=1)
    retrieval_quality: float = Field(ge=0, le=1)
    deterministic_check_score: float = Field(ge=0, le=1)
    n_material_contradicting_evidence: int = Field(ge=0)


def confidence(features: ScoreFeatures) -> float:
    score = (
        EVIDENCE_COVERAGE * features.evidence_coverage
        + CAUSAL_PROXIMITY * features.causal_proximity
        + RETRIEVAL_QUALITY * features.retrieval_quality
        + DETERMINISTIC_CHECK * features.deterministic_check_score
        - min(
            MAX_CONTRADICTION_PENALTY,
            CONTRADICTION_WEIGHT * features.n_material_contradicting_evidence,
        )
    )
    return min(1.0, max(0.0, score))
