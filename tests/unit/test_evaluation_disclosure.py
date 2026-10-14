"""Ground truth is a distinct scorer-only disclosure after a terminal scored evaluation."""

from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import uuid4

import pytest
from aipi_evaluation.contracts import EvaluationJob, Experiment, Scorecard, Scores
from aipi_evaluation.server import Scorer, ScorerSettings
from fastapi import HTTPException


def card():
    return Scorecard(
        scenario_id="SCN-001",
        passed=True,
        scores=Scores(
            top1=1,
            top3_recall=1,
            evidence_precision=1,
            evidence_coverage=1,
            unsupported_claim_rate=0,
            contradiction_handling=1,
            latency_ms=10,
            useful_evidence_per_tool_call=1,
            citation_pairs=1,
            supported_pairs=1,
            material_claims=1,
            unsupported_claims=0,
            critical_unsupported_claims=0,
            covered_features=("die_137",),
            required_feature_count=1,
            tool_calls=1,
            tokens=0,
        ),
        experiment=Experiment(
            prompt_version="test",
            tool_version="test",
            code_commit="test",
            seed=42,
            retrieval_params={"limit": 50},
        ),
        mode="golden",
        created_at=datetime.now(UTC),
    )


@pytest.mark.parametrize("status", ["queued", "running", "failed"])
def test_no_truth_read_before_a_scored_terminal_result(status, monkeypatch):
    scorer = Scorer.__new__(Scorer)
    scorer.get = Mock(
        return_value=EvaluationJob(
            id=uuid4(), scenario_id="SCN-001", status=status, created_at=datetime.now(UTC)
        )
    )
    reader = Mock()
    monkeypatch.setattr("aipi_evaluation.server.load_truth", reader)
    with pytest.raises(HTTPException) as denied:
        scorer.disclosure(uuid4())
    assert denied.value.status_code == 409
    reader.assert_not_called()
    # No writer or database is even attached: any premature read would have failed.


@pytest.mark.parametrize("status", ["completed", "failed"])
def test_terminal_disclosure_reads_separate_truth_and_preserves_score_only_job(status, tmp_path):
    scorer = Scorer.__new__(Scorer)
    identifier = uuid4()
    job = EvaluationJob(
        id=identifier,
        scenario_id="SCN-001",
        status=status,
        created_at=datetime.now(UTC),
        scorecard=card(),
    )
    scorer.get = Mock(return_value=job)
    scorer.config = ScorerSettings(
        truth_database_url="postgresql+psycopg://chaos_admin@localhost/aipi",
        writer_database_url="postgresql+psycopg://telemetry_writer@localhost/aipi",
        fixtures=str(tmp_path),
    )
    scorer.writer = Mock()
    scorer.writer.connect.return_value.__enter__ = Mock(
        return_value=Mock(scalar=Mock(return_value={"scenario_id": "SCN-001", "mode": "golden"}))
    )
    scorer.writer.connect.return_value.__exit__ = Mock(return_value=False)
    (tmp_path / "scn-001.truth.json").write_text('{"expected_category":"termination","seed":42}')
    result = scorer.disclosure(identifier)
    assert result.evaluation_id == identifier and "terminated" in result.expected_root_cause
    assert "die_137" in result.required_evidence and result.source == "golden"
    assert "expected_root_cause" not in job.model_dump_json()
