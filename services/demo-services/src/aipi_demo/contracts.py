"""Validated request, response, and external Docker event contracts."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class Checkout(BaseModel):
    product: str = Field(default="demo", min_length=1, max_length=100)
    quantity: int = Field(default=1, ge=1, le=100)


class Order(BaseModel):
    id: UUID
    product: str
    quantity: int
    status: str = "created"


class DockerActor(BaseModel):
    id: str = Field(alias="ID")
    attributes: dict[str, str] = Field(alias="Attributes", default_factory=dict)


class DockerEvent(BaseModel):
    type: Literal["container"] = Field(alias="Type")
    action: Literal["die", "start", "restart"] = Field(alias="Action")
    actor: DockerActor = Field(alias="Actor")
    timestamp_ns: int = Field(alias="timeNano", gt=0)
