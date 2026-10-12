# Architecture decisions

The master prompt takes precedence over the original design pack.

- ADR-001: LangGraph orchestration (implementation deferred to M4).
- ADR-002: PostgreSQL-first storage; operational simplicity.
- ADR-003: OpenTelemetry standard for logs, metrics, and traces.
- ADR-004: Read-only investigation tools; no remediation execution.
- ADR-005: Two deterministic chaos scenarios with hidden ground truth (M2).
- ADR-006: No Kafka in the first slice.
- ADR-007: Collector → API OTLP JSON ingest; central validation/redaction.
- ADR-008: Mock LLM is the default for tests, CI, and base demo (M4).
- ADR-009: Ground truth isolated in a restricted schema owned by chaos_admin.
- ADR-010: Keyword/BM25 runbook search, no vector database (M4).

## ADR-011: M0+M1 phase boundary

Build the web shell and Python package placeholders now; implement agents,
incident tables, chaos scenarios, and the full dashboard in their assigned phases.
Later Makefile commands fail with an explicit phase message until implemented.
Traffic runs in an opt-in Compose profile via `make seed-traffic` to keep a quiet
baseline available before fault-injection tests. All worker services expose health.

## ADR-012: Ingest privilege and retry safety

`telemetry_writer` can insert/select telemetry, but cannot update/delete or read
restricted labels. A separate one-shot migration container has admin credentials.
The API never receives those credentials. Normalized rows have deterministic IDs
and inserts use ON CONFLICT DO NOTHING so Collector retries do not duplicate data.
Histogram sum/count are indexed scalar metrics; the full histogram is retained
in labels for later analysis. Redaction markers are retained per telemetry row.

## ADR-013: Native images and Collector health

Use multi-architecture official PostgreSQL 16, Python 3.12 and Node 25 images,
without an amd64 override. Pin Collector contrib to 0.123.0. Its image has no shell
or curl: `make up` checks its HTTP health extension from the host after Compose
waits for every service that supports an in-container health check.
