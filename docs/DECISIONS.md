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

## ADR-014 — Verified local chaos and bounded manual-kill recovery

SCN-001 uses the fixed aipi checkout target with its `unless-stopped` policy.
On Docker Desktop 29.8.1/aarch64, manual SIGKILL left the container stopped after
the bounded observation interval. The runner explicitly starts it and requires
stored die(exit 137) followed by start, plus failed gateway telemetry. This is
the restart-behavior adjustment permitted by the resolved scenario spec.

SCN-002 uses narrow PostgreSQL function grants to chaos_admin instead of
superuser credentials, waits for actual replay-paused state, and always attempts
resume before checking telemetry. A session advisory lock serializes scenarios.
All runtime causal labels and scenario snapshots remain solely in ground_truth;
operator JSON and normal workload telemetry contain observations only.

## ADR-015 — Frozen scoped snapshots and separate retrieval/persistence paths

Incidents declare their primary service and optional related_services at creation.
This explicit allowlist allows a checkout incident to include gateway failures
and a replica incident to include probe health gauges, without later widening.
Windows are positive, timezone-aware, and at most six hours. The retrieval adapter
reloads authoritative incident bounds and only runs parameterized telemetry SELECTs
with investigator_ro. The API writes immutable snapshots and denial audits.

The first bundle for each normalized scope is frozen to prevent late OTLP arrivals
from changing replay IDs. A transaction advisory lock serializes snapshot creation.
Evidence IDs are source-derived and shared across incidents; the storage primary
key is (incident_id, id), preserving incident ownership for future citations.
Database triggers block updates/deletes/truncation even by accidental admin SQL.
The original per-signal round-robin selection capped bundles at 50; ADR-016
replaces it with telemetry-only global relevance selection.

The existing restricted telemetry_writer receives explicit SELECT/INSERT grants
on M3 metadata/artifact tables. No new credential or .env change is needed; it
cannot read ground truth. Investigation retrieval itself remains read-only.
GET /api/scenarios uses static public descriptors instead of a privileged view or
ground-truth connection. Catalog/schema tests guard against causal-label exposure.
The six read-only tools and their investigation audit records remain M4 work.


## ADR-016 — Telemetry relevance before the evidence cap

Prioritize runtime lifecycle names, fixed rule-supporting metric names, and error
severity before ordinary telemetry. A span may inherit only the severity of a
linked log in the same incident/service/time scope; status and metric values do
not rank evidence. No scenario identifier or ground-truth dependency is involved.
Tie order is timestamp then source_ref, consistently in SQL and global selection.
Exact scoped COUNTs report omitted rows by type, even beyond candidate fetch limits.
The relevance-v1 cache namespace preserves all previous immutable snapshots.
Live tests explicitly require die(137)/start and lag/paused metrics to survive;
crowded synthetic tests cover decisive observations at the oldest timestamp.
