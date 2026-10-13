"""Supervisor-owned artifacts: tools receive only a SELECT-only backend and audit port."""

from typing import Any

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from aipi_api.core_storage import metadata


def inv() -> Column[Any]:
    return Column(
        "investigation_id", UUID(as_uuid=True), ForeignKey("investigations.id"), nullable=False
    )


investigations = Table(
    "investigations",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("incident_id", UUID(as_uuid=True), ForeignKey("incidents.id"), nullable=False),
    Column("model", String(100), nullable=False),
    Column("provider", String(30), nullable=False),
    Column("status", String(20), nullable=False),
    Column("started_at", DateTime(timezone=True)),
    Column("completed_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("prompt_version", String(30), nullable=False),
    Column("tool_version", String(30), nullable=False),
    Column("code_commit", String(64), nullable=False),
    Column("input_tokens", Integer, nullable=False),
    Column("output_tokens", Integer, nullable=False),
    Column("estimated_cost", Float, nullable=False),
    Column("latency_ms", Float),
    Column("error", String(100)),
    UniqueConstraint("id", "incident_id"),
)
tool_calls = Table(
    "tool_calls",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    inv(),
    Column("actor", String(40), nullable=False),
    Column("tool", String(40), nullable=False),
    Column("args_json", JSONB, nullable=False),
    Column("result_ref", JSONB, nullable=False),
    Column("latency_ms", Float, nullable=False),
    Column("status", String(30), nullable=False),
    Column("truncated", Integer, nullable=False),
    Column("attempts", Integer, nullable=False),
    Column("error", String(100)),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
investigation_events = Table(
    "investigation_events",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    inv(),
    Column("seq", Integer, nullable=False),
    Column("ts", DateTime(timezone=True), nullable=False),
    Column("kind", String(40), nullable=False),
    Column("node", String(40), nullable=False),
    Column("payload_json", JSONB, nullable=False),
    UniqueConstraint("investigation_id", "seq"),
)
hypotheses = Table(
    "hypotheses",
    metadata,
    inv(),
    Column("id", String(100), nullable=False),
    Column("statement", Text, nullable=False),
    Column("rank", Integer, nullable=False),
    Column("confidence", Float, nullable=False),
    Column("hypothesis_json", JSONB, nullable=False),
    UniqueConstraint("investigation_id", "id"),
)
hypothesis_evidence = Table(
    "hypothesis_evidence",
    metadata,
    inv(),
    Column("hypothesis_id", String(100), nullable=False),
    Column("incident_id", UUID(as_uuid=True), nullable=False),
    Column("evidence_id", String(19), nullable=False),
    Column("stance", String(10), nullable=False),
    Column("weight", Float, nullable=False),
    ForeignKeyConstraint(
        ["investigation_id", "hypothesis_id"], ["hypotheses.investigation_id", "hypotheses.id"]
    ),
    ForeignKeyConstraint(["incident_id", "evidence_id"], ["evidence.incident_id", "evidence.id"]),
)
reports = Table(
    "reports",
    metadata,
    inv(),
    Column("root_cause", JSONB, nullable=False),
    Column("markdown", Text, nullable=False),
    Column("version", Integer, nullable=False),
    Column("report_json", JSONB, nullable=False),
    UniqueConstraint("investigation_id"),
)
recommendations = Table(
    "recommendations",
    metadata,
    inv(),
    Column("id", String(100), nullable=False),
    Column("requires_approval", Integer, nullable=False),
    Column("approval_status", String(20), nullable=False),
    Column("recommendation_json", JSONB, nullable=False),
    UniqueConstraint("investigation_id", "id"),
)
# Explicit provenance permits scoped lookup of tool/runbook evidence outside the display cap.
agent_evidence = Table(
    "agent_evidence",
    metadata,
    inv(),
    Column("incident_id", UUID(as_uuid=True), nullable=False),
    Column("evidence_id", String(19), nullable=False),
    ForeignKeyConstraint(
        ["investigation_id", "incident_id"], ["investigations.id", "investigations.incident_id"]
    ),
    ForeignKeyConstraint(["incident_id", "evidence_id"], ["evidence.incident_id", "evidence.id"]),
    UniqueConstraint("investigation_id", "evidence_id"),
)
Index("ix_hypotheses_investigation_rank", hypotheses.c.investigation_id, hypotheses.c.rank)
Index("ix_tool_calls_investigation_created", tool_calls.c.investigation_id, tool_calls.c.created_at)
Index(
    "ix_events_investigation_seq",
    investigation_events.c.investigation_id,
    investigation_events.c.seq,
)
TABLES = (
    investigations,
    tool_calls,
    investigation_events,
    hypotheses,
    hypothesis_evidence,
    reports,
    recommendations,
    agent_evidence,
)
