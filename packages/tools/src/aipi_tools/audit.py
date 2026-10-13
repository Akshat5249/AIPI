"""Audit ports: the supervisor persists records; telemetry tools never receive a writer."""

from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from aipi_telemetry.evidence import Evidence
from pydantic import BaseModel, ConfigDict, JsonValue


class ToolAudit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: UUID
    investigation_id: UUID
    actor: str
    tool: str
    args_json: dict[str, JsonValue]
    result_ref: tuple[str, ...]
    latency_ms: float
    status: str
    truncated: bool
    error: str | None
    attempts: int
    created_at: datetime


class AuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: UUID
    investigation_id: UUID
    seq: int
    ts: datetime
    kind: str
    node: str
    payload_json: dict[str, JsonValue]


class AuditSink(Protocol):
    def retain(self, items: tuple[Evidence, ...]) -> None: ...
    def record_tool(self, record: ToolAudit) -> None: ...
    def emit(self, kind: str, node: str, payload: dict[str, JsonValue]) -> UUID: ...


class MemoryAudit:
    def __init__(self, investigation_id: UUID) -> None:
        self.investigation_id = investigation_id
        self.calls: list[ToolAudit] = []
        self.events: list[AuditEvent] = []

    def retain(self, items: tuple[Evidence, ...]) -> None:
        pass

    def record_tool(self, record: ToolAudit) -> None:
        self.calls.append(ToolAudit.model_validate(record.model_dump()))

    def emit(self, kind: str, node: str, payload: dict[str, JsonValue]) -> UUID:
        identifier = uuid4()
        self.events.append(
            AuditEvent(
                id=identifier,
                investigation_id=self.investigation_id,
                seq=len(self.events) + 1,
                ts=datetime.now(UTC),
                kind=kind,
                node=node,
                payload_json=payload,
            )
        )
        return identifier
