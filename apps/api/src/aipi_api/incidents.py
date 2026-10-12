"""Application writes stay outside the read-only evidence retrieval adapter."""

from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID, uuid4

from aipi_telemetry.evidence import TimelineItem, build_timeline
from aipi_telemetry.redaction import redact
from aipi_tools.correlators import Signal, correlate
from aipi_tools.retrieval import EvidenceBundle, EvidenceReader
from aipi_tools.scope import Incident, IncidentCreate, ScopeDenied, ScopePolicy, ScopeRequest
from pydantic import BaseModel
from sqlalchemy import create_engine, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import make_url

from aipi_api.core_storage import bundles, denials, evidence, incidents


class MissingIncident(Exception):
    """An incident identifier has no persisted record."""


class TimelineResponse(BaseModel):
    incident_id: UUID
    truncated: bool
    items: tuple["TimelineItem", ...]


class IncidentCore:
    def __init__(self, reader_url: str, writer_url: str) -> None:
        self.reader = EvidenceReader(reader_url)
        if make_url(writer_url).username != "telemetry_writer":
            raise ValueError("Incident persistence requires the restricted API writer")
        self.writer = create_engine(
            writer_url,
            pool_pre_ping=True,
            hide_parameters=True,
            connect_args={"connect_timeout": 5, "options": "-c statement_timeout=5000"},
        )

    def close(self) -> None:
        self.reader.engine.dispose()
        self.writer.dispose()

    def create(self, request: IncidentCreate) -> Incident:
        incident = Incident(**request.model_dump(), id=uuid4(), created_at=datetime.now(UTC))
        values = incident.model_dump()
        values["related_services"] = list(incident.related_services)
        with self.writer.begin() as db:
            db.execute(insert(incidents).values(**values))
        return incident

    def get(self, incident_id: UUID) -> Incident:
        with self.reader.engine.connect() as db:
            row = (
                db.execute(select(incidents).where(incidents.c.id == incident_id))
                .mappings()
                .first()
            )
        if row is None:
            raise MissingIncident("Incident not found")
        return Incident.model_validate(dict(row))

    def list(self, service: str | None = None, status: str | None = None) -> tuple[Incident, ...]:
        query = select(incidents)
        if service:
            query = query.where(incidents.c.service == service)
        if status:
            query = query.where(incidents.c.status == status)
        with self.reader.engine.connect() as db:
            rows = db.execute(
                query.order_by(incidents.c.created_at.desc(), incidents.c.id.desc()).limit(100)
            ).mappings()
            return tuple(Incident.model_validate(dict(row)) for row in rows)

    def retrieve(self, request: ScopeRequest, request_id: str) -> EvidenceBundle:
        incident = self.get(request.incident_id)
        try:
            scope = ScopePolicy().authorize(incident, request)
        except ScopeDenied:
            clean, _ = redact(request.model_dump(mode="json"))
            with self.writer.begin() as db:
                db.execute(
                    insert(denials).values(
                        id=uuid4(),
                        incident_id=incident.id,
                        request_id=request_id,
                        actor="api",
                        requested_json=clean,
                        created_at=datetime.now(UTC),
                    )
                )
            raise
        key = sha256(scope.model_dump_json().encode()).hexdigest()
        # One immutable first-read snapshot per incident/scope, even under concurrent requests.
        with self.writer.begin() as db:
            lock = int(key[:15], 16)
            db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})
            cached = db.scalar(
                select(bundles.c.bundle_json).where(
                    bundles.c.incident_id == incident.id, bundles.c.scope_key == key
                )
            )
            if cached is not None:
                return EvidenceBundle.model_validate(cached)
            result = self.reader.retrieve(incident, request)
            for item in result.items:
                db.execute(
                    insert(evidence)
                    .values(
                        incident_id=incident.id,
                        id=item.evidence_id,
                        type=item.type,
                        service=item.service,
                        timestamp=item.timestamp,
                        source_ref=item.source_ref,
                        summary=item.summary,
                        payload_json=item.model_dump(mode="json")["payload"],
                        redactions=item.model_dump(mode="json")["redactions"],
                    )
                    .on_conflict_do_nothing()
                )
            db.execute(
                insert(bundles).values(
                    incident_id=incident.id,
                    scope_key=key,
                    bundle_json=result.model_dump(mode="json"),
                )
            )
        return result

    def timeline(self, request: ScopeRequest, request_id: str) -> TimelineResponse:
        bundle = self.retrieve(request, request_id)
        return TimelineResponse(
            incident_id=request.incident_id,
            truncated=bundle.truncated,
            items=build_timeline(bundle.items),
        )

    def signals(self, request: ScopeRequest, request_id: str) -> tuple[Signal, ...]:
        return correlate(self.retrieve(request, request_id).items)
