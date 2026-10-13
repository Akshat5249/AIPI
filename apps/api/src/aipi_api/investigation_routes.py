"""Background investigations, typed artifacts and resumable ordered SSE events."""

import asyncio
from collections.abc import AsyncIterator
from typing import Literal
from uuid import UUID

from aipi_agents.schemas import Hypothesis, Recommendation, Report
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict
from starlette.concurrency import run_in_threadpool
from starlette.responses import StreamingResponse

from aipi_api.investigation_repository import EventsSnapshot, Investigation
from aipi_api.investigations import Investigator

router = APIRouter(prefix="/api", tags=["investigations"])


class InvestigateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


def manager(request: Request) -> Investigator:
    return request.app.state.investigator  # type: ignore[no-any-return]


@router.post("/incidents/{incident_id}/investigate", response_model=Investigation, status_code=202)
def start(
    incident_id: UUID,
    request: Request,
    background: BackgroundTasks,
    body: InvestigateRequest | None = None,
) -> Investigation:
    supervisor = manager(request)
    investigation = supervisor.start(incident_id)
    background.add_task(supervisor.run, investigation.id)
    return investigation


@router.get("/investigations/{investigation_id}", response_model=Investigation)
def status(investigation_id: UUID, request: Request) -> Investigation:
    return manager(request).get(investigation_id)


@router.get("/incidents/{incident_id}/hypotheses", response_model=tuple[Hypothesis, ...])
def hypotheses(incident_id: UUID, request: Request) -> tuple[Hypothesis, ...]:
    return manager(request).report(incident_id).ranked_hypotheses


@router.get("/incidents/{incident_id}/report", response_model=Report)
def report(incident_id: UUID, request: Request) -> Report:
    return manager(request).report(incident_id)


@router.get("/incidents/{incident_id}/recommendations", response_model=tuple[Recommendation, ...])
def recommendations(incident_id: UUID, request: Request) -> tuple[Recommendation, ...]:
    return manager(request).report(incident_id).recommendations


@router.get(
    "/investigations/{investigation_id}/events",
    response_model=EventsSnapshot,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def events(
    investigation_id: UUID,
    request: Request,
    format: Literal["sse", "json"] = "sse",
    after: int = Query(default=0, ge=0),
    last_event_id: str | None = Header(default=None),
) -> EventsSnapshot | StreamingResponse:
    supervisor = manager(request)
    if last_event_id is not None:
        try:
            parsed = int(last_event_id)
            if parsed < 0:
                raise ValueError()
            after = max(after, parsed)
        except ValueError as exc:
            raise HTTPException(422, "Invalid event cursor") from exc
    initial = await run_in_threadpool(supervisor.events, investigation_id, after)
    if format == "json":
        return initial

    async def stream() -> AsyncIterator[str]:
        snapshot = initial
        cursor = after
        while not await request.is_disconnected():
            for event in snapshot.events:
                yield f"id: {event.seq}\nevent: {event.kind}\ndata: {event.model_dump_json()}\n\n"
                cursor = event.seq
            if snapshot.status in {"completed", "failed"} and len(snapshot.events) < 1000:
                yield f'event: done\ndata: {{"status":"{snapshot.status}"}}\n\n'
                return
            yield ": heartbeat\n\n"
            await asyncio.sleep(0.2)
            snapshot = await run_in_threadpool(supervisor.events, investigation_id, cursor)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/incidents/{incident_id}/investigation", response_model=Investigation)
def latest(incident_id: UUID, request: Request) -> Investigation:
    return manager(request).latest(incident_id)
