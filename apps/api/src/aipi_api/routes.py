"""Typed M3 public API; no routes import the restricted scenario registry."""

from typing import Annotated, Literal, cast
from uuid import UUID

from aipi_tools.correlators import Signal
from aipi_tools.retrieval import EvidenceBundle
from aipi_tools.scope import Incident, IncidentCreate, ScopeRequest, Service
from fastapi import APIRouter, Depends, Query, Request
from pydantic import AwareDatetime, BaseModel

from aipi_api.incidents import IncidentCore, TimelineResponse

router = APIRouter(prefix="/api")


class ScenarioPublic(BaseModel):
    id: Literal["SCN-001", "SCN-002"]
    name: str
    description: str


# Public descriptions have no dependency on restricted labels or chaos credentials.
CATALOG = (
    ScenarioPublic(
        id="SCN-001", name="Service Kill", description="Checkout availability lab scenario"
    ),
    ScenarioPublic(
        id="SCN-002", name="Replica Lag", description="Standby replication lab scenario"
    ),
)


def core(request: Request) -> IncidentCore:
    return cast(IncidentCore, request.app.state.core)


Core = Annotated[IncidentCore, Depends(core)]


def scope_request(
    incident_id: UUID,
    service: str | None = Query(None, min_length=1, max_length=200),
    start_time: AwareDatetime | None = None,
    end_time: AwareDatetime | None = None,
) -> ScopeRequest:
    return ScopeRequest(
        incident_id=incident_id, service=service, start_time=start_time, end_time=end_time
    )


ScopeInput = Annotated[ScopeRequest, Depends(scope_request)]


@router.post("/incidents", status_code=201)
def create_incident(body: IncidentCreate, store: Core) -> Incident:
    return store.create(body)


@router.get("/incidents")
def list_incidents(
    store: Core, service: Service | None = None, status: Literal["open"] | None = None
) -> tuple[Incident, ...]:
    return store.list(service, status)


@router.get("/incidents/{incident_id}")
def get_incident(incident_id: UUID, store: Core) -> Incident:
    return store.get(incident_id)


@router.get("/incidents/{incident_id}/evidence")
def get_evidence(request: Request, scope: ScopeInput, store: Core) -> EvidenceBundle:
    return store.retrieve(scope, request.state.request_id)


@router.get("/incidents/{incident_id}/timeline")
def get_timeline(request: Request, scope: ScopeInput, store: Core) -> TimelineResponse:
    return store.timeline(scope, request.state.request_id)


@router.get("/incidents/{incident_id}/signals")
def get_signals(request: Request, scope: ScopeInput, store: Core) -> tuple[Signal, ...]:
    return store.signals(scope, request.state.request_id)


@router.get("/scenarios")
def scenarios() -> tuple[ScenarioPublic, ...]:
    return CATALOG
