"""Durable supervisor audit sink; its writer is never used by a telemetry query backend."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from aipi_telemetry.evidence import Evidence
from aipi_tools.audit import AuditEvent, ToolAudit
from aipi_tools.scope import ScopePolicy, ScopeRequest
from pydantic import JsonValue
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert

from aipi_api.agent_storage import agent_evidence, investigation_events, tool_calls
from aipi_api.core_storage import evidence
from aipi_api.incidents import IncidentCore


class DatabaseAudit:
    def __init__(self, core: IncidentCore, investigation_id: UUID, incident_id: UUID) -> None:
        self.core = core
        self.investigation_id = investigation_id
        self.incident_id = incident_id

    def retain(self, items: tuple[Evidence, ...]) -> None:
        boundary = self.core.get(self.incident_id)
        scope = ScopePolicy().authorize(boundary, ScopeRequest(incident_id=boundary.id))
        checked = tuple(Evidence.model_validate(e.model_dump()) for e in items)
        if any(
            e.service not in scope.services
            or not scope.window.start_time <= e.timestamp <= scope.window.end_time
            for e in checked
        ):
            raise ValueError("Artifact outside incident scope")
        if not checked:
            return
        with self.core.writer.begin() as db:
            db.execute(
                insert(evidence).on_conflict_do_nothing(),
                [
                    dict(
                        incident_id=boundary.id,
                        id=e.evidence_id,
                        type=e.type,
                        service=e.service,
                        timestamp=e.timestamp,
                        source_ref=e.source_ref,
                        summary=e.summary,
                        payload_json=e.model_dump(mode="json")["payload"],
                        redactions=e.model_dump(mode="json")["redactions"],
                    )
                    for e in checked
                ],
            )
            db.execute(
                insert(agent_evidence).on_conflict_do_nothing(),
                [
                    dict(
                        investigation_id=self.investigation_id,
                        incident_id=boundary.id,
                        evidence_id=e.evidence_id,
                    )
                    for e in checked
                ],
            )

    def record_tool(self, record: ToolAudit) -> None:
        values = record.model_dump()
        values["result_ref"] = list(record.result_ref)
        values["truncated"] = int(record.truncated)
        with self.core.writer.begin() as db:
            db.execute(insert(tool_calls).values(**values))

    def emit(self, kind: str, node: str, payload: dict[str, JsonValue]) -> UUID:
        identifier = uuid4()
        with self.core.writer.begin() as db:
            db.execute(
                text("SELECT pg_advisory_xact_lock(:key)"),
                {"key": int(self.investigation_id.hex[:15], 16)},
            )
            seq = (
                db.scalar(
                    select(func.max(investigation_events.c.seq)).where(
                        investigation_events.c.investigation_id == self.investigation_id
                    )
                )
                or 0
            ) + 1
            record = AuditEvent(
                id=identifier,
                investigation_id=self.investigation_id,
                seq=seq,
                ts=datetime.now(UTC),
                kind=kind,
                node=node,
                payload_json=payload,
            )
            db.execute(insert(investigation_events).values(**record.model_dump()))
        return identifier
