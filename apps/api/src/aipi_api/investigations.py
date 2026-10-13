"""Background supervisor: readonly graph sources, immutable artifacts, durable status."""

import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from aipi_agents.adapters import adapter_for
from aipi_agents.offline import ModelOutputInvalid
from aipi_agents.reporting import ReportValidationError, validate_report
from aipi_agents.schemas import AgentInput, InvestigationState
from aipi_agents.workflow import Workflow
from aipi_tools.backend import SQLBackend
from aipi_tools.registry import ToolRunner
from aipi_tools.scope import ScopeRequest
from opentelemetry import metrics, trace
from sqlalchemy import update

from aipi_api.agent_audit import DatabaseAudit
from aipi_api.agent_storage import (
    investigations,
)
from aipi_api.config import Settings
from aipi_api.incidents import IncidentCore
from aipi_api.investigation_repository import InvestigationRepository


class Investigator(InvestigationRepository):
    def __init__(
        self,
        core: IncidentCore,
        config: Settings,
        tracer: trace.Tracer | None = None,
        meter: metrics.Meter | None = None,
    ) -> None:
        super().__init__(core, config)
        self.tracer = tracer or trace.get_tracer("aipi.supervisor")
        self.meter = meter or metrics.get_meter("aipi.supervisor")
        self.latency = self.meter.create_histogram("investigation.latency_ms", unit="ms")
        self.tokens = self.meter.create_counter("investigation.tokens")
        self.count = self.meter.create_histogram("investigation.evidence_count")
        self.confidence = self.meter.create_histogram("investigation.confidence")
        self.backend = SQLBackend(
            core.reader,
            Path(config.runbooks_path),
            config.replica_database_url.get_secret_value() if config.replica_database_url else None,
        )

    def close(self) -> None:
        if self.backend.replica:
            self.backend.replica.engine.dispose()

    def run(self, identifier: UUID) -> None:
        current = self.get(identifier)
        audit = DatabaseAudit(self.core, current.id, current.incident_id)
        started = time.monotonic()
        try:
            with self.core.writer.begin() as db:
                db.execute(
                    update(investigations)
                    .where(investigations.c.id == identifier)
                    .values(status="running", started_at=datetime.now(UTC))
                )
            audit.emit("investigation_running", "Supervisor", {})
            incident = self.core.get(current.incident_id)
            request = ScopeRequest(incident_id=incident.id)
            bundle = self.core.retrieve(request, "investigation-" + identifier.hex)
            ids = {e.evidence_id for e in bundle.items} | {
                eid for s in bundle.signals for eid in s.evidence_ids
            }
            known = {e.evidence_id: e for e in bundle.items}
            for eid in sorted(ids - known.keys()):
                known[eid] = self.core.evidence_item(request, "investigation", eid)
            context = AgentInput(
                incident=incident,
                items=tuple(known.values()),
                signals=bundle.signals,
                truncated=bundle.truncated,
            )
            runner = ToolRunner(
                self.backend, audit, identifier, incident.id, self.tracer, self.meter
            )
            result = Workflow(
                runner, audit, adapter_for(self.config.model_provider), self.tracer
            ).run(InvestigationState(investigation_id=identifier, input=context))
            if result.report is None:
                raise ReportValidationError("Report missing")
            audit.retain(result.input.items)
            validate_report(result.report, result.input)
            self.persist(current, result)
            elapsed = (time.monotonic() - started) * 1000
            self.latency.record(elapsed)
            self.tokens.add(
                result.input_tokens + result.output_tokens, {"provider": current.provider}
            )
            self.count.record(len(result.evidence_ids))
            self.confidence.record(result.report.root_cause.confidence)
            audit.emit(
                "investigation_completed",
                "Supervisor",
                {
                    "latency_ms": elapsed,
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                    "estimated_cost": 0,
                    "confidence": result.report.root_cause.confidence,
                },
            )
            with self.core.writer.begin() as db:
                db.execute(
                    update(investigations)
                    .where(investigations.c.id == identifier)
                    .values(
                        status="completed",
                        completed_at=datetime.now(UTC),
                        latency_ms=elapsed,
                        input_tokens=result.input_tokens,
                        output_tokens=result.output_tokens,
                        estimated_cost=0,
                    )
                )
        except Exception as exc:
            code = (
                "REPORT_VALIDATION_FAILED"
                if isinstance(exc, ReportValidationError)
                else "MODEL_OUTPUT_INVALID"
                if isinstance(exc, ModelOutputInvalid)
                else "INVESTIGATION_FAILED"
            )
            with self.core.writer.begin() as db:
                db.execute(
                    update(investigations)
                    .where(investigations.c.id == identifier)
                    .values(
                        status="failed",
                        completed_at=datetime.now(UTC),
                        latency_ms=(time.monotonic() - started) * 1000,
                        error=code,
                    )
                )
            audit.emit("investigation_failed", "Supervisor", {"error": code})
