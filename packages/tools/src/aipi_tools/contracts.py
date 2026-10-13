"""Six allowlisted read-only tool contracts and structured scoped outcomes."""

from typing import Literal
from uuid import UUID

from aipi_telemetry.evidence import Evidence
from pydantic import BaseModel, ConfigDict, Field

from aipi_tools.scope import Scope, ScopeRequest, Window

ToolName = Literal[
    "logs_query",
    "metric_query",
    "trace_lookup",
    "runtime_events_query",
    "db_replication_status",
    "runbook_search",
]
TOOL_VERSION = "v1"


class ToolInput(ScopeRequest):
    limit: int = Field(default=50, ge=1, le=50)


class LogsInput(ToolInput):
    severity: Literal["INFO", "WARN", "WARNING", "ERROR", "FATAL"] | None = None
    text: str | None = Field(default=None, max_length=200)


class MetricInput(ToolInput):
    metric_name: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_.]+$")
    aggregation: Literal["series_summary", "first", "last", "min", "max", "count"] = (
        "series_summary"
    )


class TraceInput(ToolInput):
    trace_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    errors_only: bool = False
    slow_ms: float | None = Field(default=None, ge=0, le=60000)


class RuntimeInput(ToolInput):
    names: tuple[Literal["die", "start", "restart", "deploy"], ...] = (
        "die",
        "start",
        "restart",
        "deploy",
    )


class ReplicationInput(ToolInput):
    pass


class RunbookInput(ToolInput):
    query: str = Field(min_length=1, max_length=200)


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    call_id: UUID
    source_id: UUID
    window: Window
    query_params: Scope
    status: Literal["ok", "unavailable", "denied"]
    truncated: bool = False
    items: tuple[Evidence, ...] = Field(default=(), max_length=50)
    attempts: int = Field(ge=1, le=3)
    error: str | None = None
    diagnostics: tuple[str, ...] = ()
