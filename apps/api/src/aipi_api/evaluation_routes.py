"""Typed proxy to isolated scorer; this API has no truth credential or reader."""

from uuid import UUID

import httpx
from aipi_evaluation.contracts import EvaluationJob, ReplayRequest
from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

router = APIRouter(prefix="/api/evaluations", tags=["evaluations"])


def forward(request: Request, path: str, body: ReplayRequest | None = None) -> EvaluationJob:
    try:
        with httpx.Client(base_url=request.app.state.scorer_url, timeout=15) as client:
            response = (
                client.post(path, json=body.model_dump(mode="json")) if body else client.get(path)
            )
            if response.status_code == 404:
                raise HTTPException(404, "Evaluation not found")
            response.raise_for_status()
            return EvaluationJob.model_validate(response.json())
    except (httpx.HTTPError, ValidationError) as exc:
        raise HTTPException(503, "Scorer unavailable") from exc


@router.post("/replay", response_model=EvaluationJob, status_code=202)
def replay(body: ReplayRequest, request: Request) -> EvaluationJob:
    return forward(request, "/replay", body)


@router.get("/{identifier}", response_model=EvaluationJob)
def get(identifier: UUID, request: Request) -> EvaluationJob:
    return forward(request, f"/evaluations/{identifier}")
