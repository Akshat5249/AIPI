"""Incident metadata and immutable evidence snapshots, separate from telemetry reads."""

from typing import Any

from sqlalchemy import Column, DateTime, ForeignKey, Index, MetaData, String, Table, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

metadata = MetaData()
incidents = Table(
    "incidents",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("title", String(200), nullable=False),
    Column("service", String(200), nullable=False),
    Column("related_services", JSONB, nullable=False),
    Column("start_time", DateTime(timezone=True), nullable=False),
    Column("end_time", DateTime(timezone=True), nullable=False),
    Column("symptom", Text, nullable=False),
    Column("status", String(30), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


def reference() -> Column[Any]:
    return Column("incident_id", UUID(as_uuid=True), ForeignKey("incidents.id"), primary_key=True)


evidence = Table(
    "evidence",
    metadata,
    reference(),
    Column("id", String(19), primary_key=True),
    Column("type", String(20), nullable=False),
    Column("service", String(200), nullable=False),
    Column("timestamp", DateTime(timezone=True), nullable=False),
    Column("source_ref", Text, nullable=False),
    Column("summary", Text, nullable=False),
    Column("payload_json", JSONB, nullable=False),
    Column("redactions", JSONB, nullable=False),
)
bundles = Table(
    "evidence_bundles",
    metadata,
    reference(),
    Column("scope_key", String(64), primary_key=True),
    Column("bundle_json", JSONB, nullable=False),
)
denials = Table(
    "scope_denials",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("incident_id", UUID(as_uuid=True), ForeignKey("incidents.id"), nullable=False),
    Column("request_id", String(64), nullable=False),
    Column("actor", String(30), nullable=False),
    Column("requested_json", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
Index(
    "ix_incidents_service_window", incidents.c.service, incidents.c.start_time, incidents.c.end_time
)
Index("ix_evidence_service_timestamp", evidence.c.service, evidence.c.timestamp)
Index("ix_evidence_incident_type", evidence.c.incident_id, evidence.c.type)
