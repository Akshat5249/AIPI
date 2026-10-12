"""Immutable incident bounds; requested services and windows may only narrow."""

import logging
from datetime import UTC, timedelta
from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

Service = Literal[
    "gateway",
    "checkout-api",
    "orders-api",
    "pg-lag-probe",
    "event-watcher",
    "traffic",
    "postgres-primary",
    "postgres-replica",
    "api",
]
logger = logging.getLogger(__name__)


class IncidentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    title: str = Field(min_length=1, max_length=200)
    service: Service
    related_services: tuple[Service, ...] = Field(default=(), max_length=8)
    start_time: AwareDatetime
    end_time: AwareDatetime
    symptom: str = Field(min_length=1, max_length=2000)

    @field_validator("title", "symptom")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Text must not be blank")
        return value.strip()

    @model_validator(mode="after")
    def valid_window(self) -> Self:
        if self.end_time <= self.start_time or self.end_time - self.start_time > timedelta(hours=6):
            raise ValueError("Incident window must be positive and at most 6 hours")
        if len(set(self.related_services)) != len(self.related_services):
            raise ValueError("Related services must be unique")
        return self


class Incident(IncidentCreate):
    id: UUID
    status: Literal["open"] = "open"
    created_at: AwareDatetime

    @property
    def services(self) -> tuple[str, ...]:
        return tuple(sorted({self.service, *self.related_services}))


class ScopeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    incident_id: UUID
    service: str | None = Field(default=None, min_length=1, max_length=200)
    start_time: AwareDatetime | None = None
    end_time: AwareDatetime | None = None


class Window(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    start_time: AwareDatetime
    end_time: AwareDatetime


class Scope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    incident_id: UUID
    services: tuple[str, ...]
    window: Window


class ScopeDenied(Exception):
    """A retrieval tried to escape its persisted incident boundary."""


class ScopePolicy:
    def authorize(self, incident: Incident, request: ScopeRequest) -> Scope:
        services = (request.service,) if request.service else incident.services
        start = request.start_time or incident.start_time
        end = request.end_time or incident.end_time
        if (
            request.incident_id != incident.id
            or not set(services).issubset(incident.services)
            or start < incident.start_time
            or end > incident.end_time
            or start >= end
        ):
            logger.warning("Scope widening denied", extra={"incident_id": str(incident.id)})
            raise ScopeDenied("Requested scope exceeds the incident boundary")
        return Scope(
            incident_id=incident.id,
            services=tuple(sorted(services)),
            window=Window(start_time=start.astimezone(UTC), end_time=end.astimezone(UTC)),
        )
