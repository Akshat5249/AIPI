"""Typed scorer proxy; truth is disclosed only by a separate terminal-evaluation route."""

from uuid import UUID

import httpx
from aipi_evaluation.contracts import EvaluationJob, EvaluationTruth, ReplayRequest
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ValidationError

router = APIRouter(prefix="/api/evaluations", tags=["evaluations"])


def forward[ResponseModel: BaseModel](
    request: Request,
    path: str,
    schema: type[ResponseModel],
    body: ReplayRequest | None = None,
) -> ResponseModel:
    try:
        with httpx.Client(base_url=request.app.state.scorer_url, timeout=15) as client:
            response = (
                client.post(path, json=body.model_dump(mode="json")) if body else client.get(path)
            )
            if response.status_code == 404:
                raise HTTPException(404, "Evaluation not found")
            if response.status_code == 409:
                raise HTTPException(409, "Evaluation not ready")
            response.raise_for_status()
            return schema.model_validate(response.json())
    except (httpx.HTTPError, ValidationError) as exc:
        raise HTTPException(503, "Scorer unavailable") from exc


@router.post("/replay", response_model=EvaluationJob, status_code=202)
def replay(body: ReplayRequest, request: Request) -> EvaluationJob:
    return forward(request, "/replay", EvaluationJob, body)


@router.get("/{identifier}", response_model=EvaluationJob)
def get(identifier: UUID, request: Request) -> EvaluationJob:
    return forward(request, f"/evaluations/{identifier}", EvaluationJob)


@router.get("/{identifier}/ground-truth", response_model=EvaluationTruth)
def disclosure(identifier: UUID, request: Request) -> EvaluationTruth:
    return forward(request, f"/evaluations/{identifier}/ground-truth", EvaluationTruth)
