"""Typed job metadata, scoped artifact reads and supervisor-only persistence."""

import os
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from aipi_agents.context import PROMPT_VERSION
from aipi_agents.schemas import Hypothesis, InvestigationState, Report
from aipi_tools.audit import AuditEvent
from aipi_tools.contracts import TOOL_VERSION
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Connection

from aipi_api.agent_audit import DatabaseAudit
from aipi_api.agent_storage import (
    hypotheses,
    hypothesis_evidence,
    investigation_events,
    investigations,
    recommendations,
    reports,
)
from aipi_api.config import Settings
from aipi_api.incidents import IncidentCore, MissingIncident

Status = Literal["queued", "running", "completed", "failed"]


class Investigation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: UUID
    incident_id: UUID
    model: str
    provider: str
    status: Status
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    prompt_version: str
    tool_version: str
    code_commit: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    estimated_cost: float = Field(ge=0)
    latency_ms: float | None = None
    error: str | None = None


class InvestigationUnavailable(Exception):
    def __init__(self, code: str) -> None:
        self.code = code


class EventsSnapshot(BaseModel):
    investigation_id: UUID
    status: Status
    events: tuple[AuditEvent, ...]
    last_seq: int


class InvestigationRepository:
    def __init__(self, core: IncidentCore, config: Settings) -> None:
        self.core = core
        self.config = config

    def recover_interrupted(self) -> None:
        # Single process MVP; a restart cannot resume in-memory jobs.
        with self.core.writer.begin() as db:
            rows = (
                db.execute(
                    select(investigations).where(investigations.c.status.in_(("queued", "running")))
                )
                .mappings()
                .all()
            )
            if rows:
                db.execute(
                    update(investigations)
                    .where(investigations.c.status.in_(("queued", "running")))
                    .values(
                        status="failed", completed_at=datetime.now(UTC), error="PROCESS_INTERRUPTED"
                    )
                )
        for row in rows:
            DatabaseAudit(self.core, row["id"], row["incident_id"]).emit(
                "investigation_failed", "Supervisor", {"error": "PROCESS_INTERRUPTED"}
            )

    def start(self, incident_id: UUID) -> Investigation:
        self.core.get(incident_id)
        value = Investigation(
            id=uuid4(),
            incident_id=incident_id,
            provider=self.config.model_provider,
            model=self.config.model_name,
            status="queued",
            created_at=datetime.now(UTC),
            prompt_version=PROMPT_VERSION,
            tool_version=TOOL_VERSION,
            code_commit=os.getenv("AIPI_CODE_COMMIT", "working-tree"),
            input_tokens=0,
            output_tokens=0,
            estimated_cost=0,
        )
        with self.core.writer.begin() as db:
            db.execute(insert(investigations).values(**value.model_dump()))
        DatabaseAudit(self.core, value.id, incident_id).emit(
            "investigation_queued", "Supervisor", {}
        )
        return value

    def get(self, identifier: UUID) -> Investigation:
        with self.core.reader.engine.connect() as db:
            row = (
                db.execute(select(investigations).where(investigations.c.id == identifier))
                .mappings()
                .first()
            )
        if row is None:
            raise MissingIncident("Investigation not found")
        return Investigation.model_validate(dict(row))

    def latest(self, incident_id: UUID) -> Investigation:
        self.core.get(incident_id)
        with self.core.reader.engine.connect() as db:
            row = (
                db.execute(
                    select(investigations)
                    .where(investigations.c.incident_id == incident_id)
                    .order_by(investigations.c.created_at.desc(), investigations.c.id.desc())
                    .limit(1)
                )
                .mappings()
                .first()
            )
        if row is None:
            raise MissingIncident("Investigation not found")
        return Investigation.model_validate(dict(row))

    def report(self, incident_id: UUID) -> Report:
        current = self.latest(incident_id)
        if current.status != "completed":
            raise InvestigationUnavailable(
                "INVESTIGATION_FAILED" if current.status == "failed" else "INVESTIGATION_NOT_READY"
            )
        with self.core.reader.engine.connect() as db:
            value = db.scalar(
                select(reports.c.report_json).where(reports.c.investigation_id == current.id)
            )
        if value is None:
            raise InvestigationUnavailable("INVESTIGATION_FAILED")
        return Report.model_validate(value)

    def events(self, identifier: UUID, after: int = 0) -> EventsSnapshot:
        current = self.get(identifier)
        with self.core.reader.engine.connect() as db:
            rows = db.execute(
                select(investigation_events)
                .where(
                    investigation_events.c.investigation_id == identifier,
                    investigation_events.c.seq > after,
                )
                .order_by(investigation_events.c.seq)
                .limit(1000)
            ).mappings()
            events = tuple(AuditEvent.model_validate(dict(row)) for row in rows)
        return EventsSnapshot(
            investigation_id=identifier,
            status=current.status,
            events=events,
            last_seq=events[-1].seq if events else after,
        )

    def persist(self, current: Investigation, result: InvestigationState) -> None:
        assert result.report is not None
        with self.core.writer.begin() as db:
            for h in result.ranked_causes:
                self.persist_hypothesis(db, current, h)
            report = result.report
            db.execute(
                insert(reports).values(
                    investigation_id=current.id,
                    root_cause=report.root_cause.model_dump(mode="json"),
                    markdown=report.markdown,
                    version=1,
                    report_json=report.model_dump(mode="json", by_alias=True),
                )
            )
            for rec in report.recommendations:
                db.execute(
                    insert(recommendations).values(
                        investigation_id=current.id,
                        id=rec.id,
                        requires_approval=1,
                        approval_status="pending",
                        recommendation_json=rec.model_dump(mode="json"),
                    )
                )

    def persist_hypothesis(self, db: "Connection", current: Investigation, h: Hypothesis) -> None:
        db.execute(
            insert(hypotheses).values(
                investigation_id=current.id,
                id=h.id,
                statement=h.statement,
                rank=h.rank,
                confidence=h.confidence,
                hypothesis_json=h.model_dump(mode="json", by_alias=True),
            )
        )
        for stance, ids in (("for", h.for_ids), ("against", h.against)):
            for eid in ids:
                db.execute(
                    insert(hypothesis_evidence).values(
                        investigation_id=current.id,
                        hypothesis_id=h.id,
                        incident_id=current.incident_id,
                        evidence_id=eid,
                        stance=stance,
                        weight=1,
                    )
                )
