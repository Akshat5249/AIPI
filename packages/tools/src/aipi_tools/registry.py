"""Immutable six-tool registry; supervisor audit and two bounded timeout retries."""

import time
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Literal, cast
from uuid import UUID, uuid4

from aipi_telemetry.evidence import Evidence
from aipi_telemetry.redaction import redact
from opentelemetry import trace
from pydantic import BaseModel, ConfigDict, JsonValue, ValidationError
from sqlalchemy.exc import SQLAlchemyError

from aipi_tools.audit import AuditSink, ToolAudit
from aipi_tools.backend import ToolBackend, ToolTimeout
from aipi_tools.contracts import (
    LogsInput,
    MetricInput,
    ReplicationInput,
    RunbookInput,
    RuntimeInput,
    ToolInput,
    ToolName,
    ToolResult,
    TraceInput,
)
from aipi_tools.ranking import rank_candidates, select_ranked
from aipi_tools.scope import Scope, ScopeDenied, ScopePolicy, Window

REGISTRY: MappingProxyType[str, type[ToolInput]] = MappingProxyType(
    {
        "logs_query": LogsInput,
        "metric_query": MetricInput,
        "trace_lookup": TraceInput,
        "runtime_events_query": RuntimeInput,
        "db_replication_status": ReplicationInput,
        "runbook_search": RunbookInput,
    }
)


class ReadOnlyDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: ToolName
    mutating: Literal[False] = False


DESCRIPTORS = tuple(ReadOnlyDescriptor(name=cast(ToolName, name)) for name in REGISTRY)


class ToolRunner:
    def __init__(
        self,
        backend: ToolBackend,
        audit: AuditSink,
        investigation_id: UUID,
        incident_id: UUID,
        tracer: trace.Tracer | None = None,
    ) -> None:
        self.backend = backend
        self.audit = audit
        self.investigation_id = investigation_id
        self.incident_id = incident_id
        self.tracer = tracer or trace.get_tracer("aipi.tools")

    def call(self, name: ToolName, args: ToolInput, actor: str) -> ToolResult:
        # Revalidate at boundary: callers cannot bypass typed inputs via model_copy.
        started = time.monotonic()
        identifier = uuid4()
        incident = self.backend.incident(self.incident_id)
        safe_scope = Scope(
            incident_id=incident.id,
            services=incident.services,
            window=Window(start_time=incident.start_time, end_time=incident.end_time),
        )
        attempts = 1
        with self.tracer.start_as_current_span("tool." + name) as span:
            span.set_attribute("incident.id", str(incident.id))
            try:
                args = REGISTRY[name].model_validate(args.model_dump())
                scope = ScopePolicy().authorize(incident, args)
                for attempt in range(3):
                    attempts = attempt + 1
                    try:
                        found = tuple(
                            Evidence.model_validate(e.model_dump())
                            for e in self.backend.fetch(name, args, scope)
                        )
                        # Validate outputs and reject out-of-scope adapter bugs.
                        if any(
                            e.service not in scope.services
                            or not scope.window.start_time <= e.timestamp <= scope.window.end_time
                            for e in found
                        ):
                            raise ScopeDenied("Tool source returned out-of-scope evidence")
                        if name == "runbook_search":
                            chosen = found[: args.limit]  # retain BM25 score order
                        else:
                            chosen = select_ranked(rank_candidates(found), args.limit)
                        result = ToolResult(
                            call_id=identifier,
                            source_id=incident.id,
                            window=scope.window,
                            query_params=scope,
                            status="ok",
                            items=chosen,
                            truncated=len(found) > len(chosen),
                            attempts=attempts,
                        )
                        break
                    except ToolTimeout:
                        if attempt == 2:
                            result = ToolResult(
                                call_id=identifier,
                                source_id=incident.id,
                                window=scope.window,
                                query_params=scope,
                                status="unavailable",
                                attempts=attempts,
                                error="EVIDENCE_QUERY_TIMEOUT",
                            )
                        else:
                            time.sleep(0.05 * (2**attempt))
            except ScopeDenied:
                result = ToolResult(
                    call_id=identifier,
                    source_id=incident.id,
                    window=safe_scope.window,
                    query_params=safe_scope,
                    status="denied",
                    attempts=attempts,
                    error="SCOPE_POLICY_DENIED",
                )
            except (ValueError, ValidationError, SQLAlchemyError):
                result = ToolResult(
                    call_id=identifier,
                    source_id=incident.id,
                    window=safe_scope.window,
                    query_params=safe_scope,
                    status="unavailable",
                    attempts=attempts,
                    error="TOOL_OUTPUT_INVALID",
                )
            self.audit.retain(result.items)
            clean, _ = redact(args.model_dump(mode="json"))
            self.audit.record_tool(
                ToolAudit(
                    id=identifier,
                    investigation_id=self.investigation_id,
                    actor=actor,
                    tool=name,
                    args_json=cast(dict[str, JsonValue], clean),
                    result_ref=tuple(e.evidence_id for e in result.items),
                    latency_ms=(time.monotonic() - started) * 1000,
                    status=result.status,
                    truncated=result.truncated,
                    error=result.error,
                    attempts=result.attempts,
                    created_at=datetime.now(UTC),
                )
            )
            self.audit.emit(
                "tool_completed",
                actor,
                {
                    "tool": name,
                    "call_id": str(identifier),
                    "status": result.status,
                    "truncated": result.truncated,
                    "attempts": attempts,
                    "evidence_ids": list(e.evidence_id for e in result.items),
                },
            )
            return ToolResult.model_validate(result.model_dump())
