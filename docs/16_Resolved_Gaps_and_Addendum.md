# Resolved Gaps & Addendum

Decisions that close open points in documents 00–15 and take precedence where they differ

**AI Production Incident Investigator**  
*AIPI-16 · Project documentation pack · v1.0*

|                      |                                                     |
|----------------------|-----------------------------------------------------|
| **Document ID**      | AIPI-16                                             |
| **Version**          | 1.0                                                 |
| **Status**           | Implementation baseline                             |
| **Amends**           | AIPI-02, 03, 04, 05, 06, 07, 08, 10, 11, 12, 14, 15 |
| **Primary audience** | Developer / reviewer / interviewer                  |

## 1. Purpose and Precedence

A completeness review of documents 00–15 found that the pack defines what to build but leaves several implementation-critical points undefined or inconsistent. This addendum records the decision taken for each. It does not replace the original documents; it amends them.

- **Precedence:** where this addendum and an earlier document differ, this addendum is authoritative.
- **Scope discipline is unchanged:** two scenarios, read-only tools, PostgreSQL first, no Kafka, no Kubernetes, no vector database (AIPI-08 section 3, AIPI-14 ADR-006).
- **Companion files:** CODEX_MASTER_PROMPT.md (build instructions), AIPI_CONTEXT.md (paste-anywhere project context), PROGRESS.md (build log).

## 2. Gap Resolution Summary

| **Gap or inconsistency**                                              | **Affects**     | **Resolution**                                                                                                               |
|-----------------------------------------------------------------------|-----------------|------------------------------------------------------------------------------------------------------------------------------|
| **No path from the OTel Collector into PostgreSQL**                   | AIPI-02, 04     | Collector otlphttp exporter (JSON) posts to internal API endpoints; the API normalizes, redacts and stores (section 4).      |
| **Raw telemetry tables undefined**                                    | AIPI-06         | Added telemetry_logs, telemetry_metrics, telemetry_spans, telemetry_events (section 4).                                      |
| **Chaos events listed as observable, ground truth said to be hidden** | AIPI-04, 06, 15 | Runtime events are observable telemetry; scenario and injection records are ground truth in a restricted schema (section 5). |
| **Demo services not defined**                                         | AIPI-02, 08     | gateway, checkout-api, orders-api, pg-lag-probe, event-watcher, traffic (section 3).                                         |
| **Fault-injection mechanisms unspecified**                            | AIPI-09         | Service kill via docker kill; replica lag via pg_wal_replay_pause (section 6).                                               |
| **LLM provider open question**                                        | AIPI-14         | Provider adapter interface with a deterministic mock default (section 8).                                                    |
| **Confidence score had no formula**                                   | AIPI-03         | Explicit weighted formula with contradiction penalty (section 8).                                                            |
| **Report, hypothesis and timeline schemas undefined**                 | AIPI-03, 05     | Report schema defined (section 9).                                                                                           |
| **Runbook source content missing**                                    | AIPI-03, 08     | runbooks/ directory; keyword/BM25 search, no pgvector (sections 8, 15).                                                      |
| **Dashboard screens undefined**                                       | AIPI-02         | Three pages defined (section 13).                                                                                            |
| **Golden test fixtures undefined**                                    | AIPI-07, 09     | Synthetic fixtures first, then recorded from live runs (section 12).                                                         |
| **Tooling versions unspecified**                                      | AIPI-11, 12     | Python 3.12, uv, ruff, mypy strict, Vite, Vitest (section 14).                                                               |
| **Env example file naming mismatch**                                  | AIPI-11, 12     | Repository file is .env.example (section 14).                                                                                |

## 3. Demo System Topology

```
traffic -> gateway -> checkout-api  --writes--> postgres-primary
                  \-> orders-api    --reads---> postgres-replica   (streaming replication)

all services, pg-lag-probe, event-watcher --OTLP--> otel-collector
otel-collector --otlphttp (JSON)--> api:/internal/otlp/v1/{traces,logs,metrics}
```

| **Service**       | **Role**                                                                                                                                                                    |
|-------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **gateway**       | POST /checkout routes to checkout-api; GET /orders/{id} routes to orders-api.                                                                                               |
| **checkout-api**  | Inserts order rows into the PostgreSQL primary. Target of Scenario A (SCN-001).                                                                                             |
| **orders-api**    | Reads order status from the replica. Replica lag shows up here as stale or missing reads and elevated latency. Affected service for Scenario B (SCN-002).                   |
| **pg-lag-probe**  | Every 2 seconds emits replica_lag_seconds, replica_lag_bytes and replica_replay_paused, and a WARN log above a threshold.                                                   |
| **event-watcher** | Lab-only. Converts Docker die, start and restart events into OTel log records (event.domain=runtime). Mounts the Docker socket read-only; documented in the security notes. |
| **traffic**       | Deterministic seeded request generator with configurable RPS (make seed-traffic).                                                                                           |

All demo services are FastAPI applications instrumented with OpenTelemetry (traces, metrics, structured JSON logs carrying trace_id and span_id), expose /healthz and /readyz, and set service.name, deployment.environment, service.version and container identity as resource attributes.

## 4. Telemetry Ingestion and Storage

The OpenTelemetry Collector has no native PostgreSQL exporter. The ingestion path is therefore: Collector otlphttp exporter (JSON encoding) to the API internal endpoints POST /internal/otlp/v1/traces, /logs and /metrics. The ingest handler parses, normalizes, redacts and bulk-inserts. These endpoints are internal and not part of the public API contract.

### 4.1 Telemetry tables (TELEMETRY_DATABASE_URL)

| **Table**             | **Columns**                                                                                             |
|-----------------------|---------------------------------------------------------------------------------------------------------|
| **telemetry_logs**    | id, ts, service, severity, body, trace_id, span_id, attributes_json, container, ingested_at             |
| **telemetry_metrics** | id, ts, service, metric_name, value, labels_json, ingested_at                                           |
| **telemetry_spans**   | trace_id, span_id, parent_span_id, service, operation, status, start_ts, duration_ms, attributes_json   |
| **telemetry_events**  | id, ts, service, event_domain, event_name, attributes_json (die, start, restart, deploy, config change) |

Indexes: (service, ts) on logs, metrics and events; (trace_id) on spans and logs; (service, start_ts) on spans.

### 4.2 Evidence identifiers

evidence_id = "ev_" + first 16 hex characters of sha256(type + "|" + source_ref). Identifiers are deterministic, so replays of the same incident window produce the same IDs. Evidence rows are immutable; a correction creates a new row referencing the prior source_ref version.

### 4.3 Redaction

Redaction runs before persistence and again before any content enters model context. Rules cover bearer tokens, keys named api_key, secret, password or token, connection-string credentials, AWS-style keys and (configurable) email addresses. The evidence redactions[] list records the field and rule name, never the redacted value. The rules are covered by unit tests with adversarial samples.

## 5. Observable Telemetry vs Ground Truth

AIPI-04 lists chaos events as a signal, while AIPI-06 and AIPI-15 require ground truth to stay hidden from the agent. Resolution:

- **Observable (visible to the agent):** logs, metrics, traces, and runtime or deployment events such as die, start, restart, deploy and config change.
- **Ground truth (hidden):** scenario id, injection record, target and expected root cause. Stored only in the ground_truth schema (tables scenarios and chaos_runs).

### 5.1 Database roles

| **Role**            | **Access**                                                                                                                                                                                |
|---------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **app_rw**          | Used by checkout-api against the primary.                                                                                                                                                 |
| **app_ro**          | Used by orders-api against the replica.                                                                                                                                                   |
| **investigator_ro** | SELECT-only on telemetry and incident tables and replication status views. Used by every investigation tool and API route. No access to the ground_truth schema. Cannot INSERT or UPDATE. |
| **chaos_admin**     | Owns ground_truth. Used only by chaos scripts and the evaluation package.                                                                                                                 |

The AIPI-06 scenarios table is the ground_truth.scenarios table. GET /api/scenarios returns id, name and description only. A test must prove that no investigation route, tool or agent process can read ground-truth fields.

## 6. Fault-Injection Mechanisms

### 6.1 SCN-001 Service Kill

- Demo services run with restart: unless-stopped.
- Injection: docker kill --signal=KILL on the checkout-api container, recorded with timestamp, target and expected root cause in ground_truth.chaos_runs. Restart-policy behavior must be verified in the build environment; the lab must show a die event followed by a start or restart event.
- Expected observable evidence: die event with exit code 137, availability drop, 5xx spike, failed spans, restart event. False lead: downstream timeouts that resemble a network or database fault.

### 6.2 SCN-002 Replica Lag

- Injection: SELECT pg_wal_replay_pause() on the replica while a short write burst runs on the primary so lag grows. Recovery: SELECT pg_wal_replay_resume().
- Expected observable evidence: replica_lag_seconds and replica_lag_bytes rising, replica_replay_paused = 1, stale reads and latency in orders-api, healthy primary. False lead: application latency or a primary outage.
- PostgreSQL uses the official postgres:16 image. Primary: wal_level=replica, replicator role, pg_hba entry. Replica: pg_basebackup -R with hot standby.
- Both scenarios must run precondition checks (steady traffic and healthy DB; primary and replica healthy) and verify recovery.

## 7. Telemetry Contract Amendments

The signal table in AIPI-04 section 2 is amended: the Deployment events row becomes Deployment and runtime events (die, start, restart, deploy, config change) and is observable. The Chaos events row is ground truth and is not part of the observable telemetry model.

## 8. Agent Design Amendments

### 8.1 Deterministic correlators

Pure functions that run before any LLM call. They seed hypotheses and provide the deterministic check score.

| **Correlator**            | **Logic**                                                                                                            |
|---------------------------|----------------------------------------------------------------------------------------------------------------------|
| **ProcessExitRule**       | Runtime die event for a service plus availability drop or 5xx spike plus failed spans indicates service termination. |
| **ErrorSpikeRule**        | Error rate or latency versus baseline inside the incident window.                                                    |
| **ReplicaLagRule**        | Lag metrics above threshold with replica_replay_paused = 1 while primary health is normal.                           |
| **DownstreamTimeoutRule** | Timeout spans and logs. Registered as the known false lead for both scenarios.                                       |
| **PrimaryHealthRule**     | Healthy primary database; contradicts a primary-outage hypothesis.                                                   |

### 8.2 Confidence model

```
score = 0.35 * evidence_coverage
      + 0.25 * causal_proximity
      + 0.20 * retrieval_quality
      + 0.20 * deterministic_check_score
      - contradiction_penalty
contradiction_penalty = min(0.45, 0.15 * material_contradicting_evidence_count)
final = clamp(score, 0, 1)
```

Weights live in a configuration module and are unit-tested with fixed inputs. The LLM may explain the score but does not determine it. Conflicting evidence is preserved on both sides and lowers confidence. These weights are a starting point; calibration across scenarios remains an open question (section 16).

### 8.3 Tool scope policy

- Every tool takes typed Pydantic input and returns {source_id, window, query_params, truncated, items}.
- A ScopePolicy bounds every query by incident, service and time window. Widening requests are denied, returned as a policy-denied result and logged.
- Default result cap is 50 items with a truncated flag. Timeouts retry at most twice with bounded backoff, then the evidence is marked unavailable.
- MVP tool set: logs_query, metric_query, trace_lookup, runtime_events_query, db_replication_status, runbook_search. A test asserts that no mutating tool is registered.

### 8.4 Prompt-injection hardening

Evidence placed in model context is wrapped in delimited data blocks, control and delimiter sequences are stripped or escaped, and system rules state that embedded instructions are never followed. Unit tests include poisoned log lines.

### 8.5 LLM provider adapters

A single interface, generate_structured(prompt, schema), returns a validated Pydantic object plus token usage and latency. Implementations: mock (default; deterministic, rule-based, works offline), anthropic and openai. CI and golden tests always use mock. Prompts are versioned files; the prompt version is recorded on every investigation. This resolves the AIPI-14 open question on provider choice for the MVP; model quality comparisons remain future work.

## 9. Report Schema

```
{
  "root_cause": {"statement": "...", "hypothesis_id": "...", "confidence": 0.0},
  "claims": [{"claim_id": "c1", "kind": "fact|hypothesis|recommendation",
              "text": "...", "evidence_ids": ["ev_..."]}],
  "timeline": [{"ts": "ISO-8601", "label": "...", "evidence_ids": ["ev_..."]}],
  "ranked_hypotheses": [{"id": "...", "statement": "...", "rank": 1, "confidence": 0.0,
                         "for": ["ev_.."], "against": ["ev_.."], "missing": ["..."]}],
  "unresolved_questions": ["..."],
  "recommendations": [{"id": "r1", "statement": "...", "evidence_ids": ["ev_.."],
                       "requires_approval": true, "executed": false}],
  "markdown": "rendered report"
}
```

- Every claim of kind fact carries at least one evidence ID, and every ID must exist in the evidence table for that incident.
- Reports that reference unknown evidence IDs are rejected: the Reporter repairs once, then the investigation fails with a clear error.
- Facts, hypotheses and recommendations are visibly separated in the rendered markdown. Recommendations are non-mutating next checks only.
- Hypotheses must be falsifiable: statement, falsification condition, expected evidence and category.

## 10. API Amendments

Added to the AIPI-05 endpoint catalog:

| **Method** | **Endpoint**                            | **Purpose**                                                          |
|------------|-----------------------------------------|----------------------------------------------------------------------|
| **GET**    | /api/incidents                          | List incidents; filter by service and status.                        |
| **GET**    | /api/incidents/{id}/recommendations     | Recommendations (recommend-only, requires approval, never executed). |
| **GET**    | /api/investigations/{id}                | Investigation status, token usage, estimated cost and latency.       |
| **GET**    | /api/scenarios                          | Scenario id, name and description only. Never ground-truth fields.   |
| **GET**    | /healthz, /readyz                       | Liveness and readiness.                                              |
| **POST**   | /internal/otlp/v1/{traces,logs,metrics} | Internal OTLP ingest from the Collector. Not a public contract.      |

- **Events endpoint:** GET /api/investigations/{id}/events streams server-sent events and supports ?format=json for a snapshot.
- **Validation:** create-incident requires end_time greater than start_time and a maximum window of about six hours.
- **Stable error codes:** VALIDATION_ERROR, NOT_FOUND, EVIDENCE_QUERY_TIMEOUT, SCOPE_POLICY_DENIED, INVESTIGATION_FAILED, MODEL_OUTPUT_INVALID. A request-id middleware populates request_id in every error.
- **Execution model:** investigations run as background tasks in the API process with statuses queued, running, completed, failed. No queue in the MVP.
- **Authentication:** none in the MVP; RBAC and tenant isolation remain production-evolution items (AIPI-11 section 5).

## 11. Database Amendments

Additions to AIPI-06 (all with foreign keys and Alembic migrations):

| **Table**                                           | **Additions**                                                                                                                                |
|-----------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------|
| **investigations**                                  | prompt_version, tool_version, code_commit, input_tokens, output_tokens, est_cost_usd, latency_ms                                             |
| **tool_calls**                                      | actor, status, truncated, error                                                                                                              |
| **reports**                                         | claims_json, unsupported_claims_count                                                                                                        |
| **recommendations (new)**                           | id, investigation_id, statement, evidence_ids, requires_approval (default true), executed (default false), approval_status (default pending) |
| **investigation_events (new)**                      | id, investigation_id, seq, ts, kind, node, payload_json                                                                                      |
| **ground_truth.scenarios, ground_truth.chaos_runs** | Restricted schema. scenarios: id, name, injected_fault, expected_root_cause. chaos_runs: scenario_id, injection_ts, target, recovery_status. |

FR-09 (token and cost metadata) is now backed by the investigations columns. FR-10 (recommend, then approve) is implemented as stored recommendations with requires_approval = true and executed = false; no execution endpoint exists.

## 12. Evaluation Amendments

- **Hallucination gate** is a pure function usable in CI. It checks that every cited evidence ID exists, quoted values match stored payloads, and no trace IDs, log lines or deployment events are invented. Any critical failure fails the run.
- **Golden fixtures:** stored in tests/fixtures as evidence bundles per scenario. Ground-truth labels live in a separate *.truth.json read only by the scorer.
- **Fixture order:** first hand-author schema-valid synthetic bundles (marked synthetic: true) and build the agent and evaluation against them with the mock LLM; then add make record-golden to capture real bundles from live runs and replace the synthetic ones.
- **Golden assertions:** Top-1 correct for both scenarios; all cited IDs exist; no critical unsupported claims; Scenario B contradicts a primary-outage hypothesis; a poisoned-log fixture does not change conclusions.
- **Experiment tracking:** each evaluation_runs.metrics_json records provider, model and version, prompt version, tool version, retrieval parameters, code commit and scenario seed. Scorecards are written as JSON and Markdown to eval_reports/.
- **Exit behavior:** make eval exits non-zero on any critical hallucination or Top-1 miss in the golden set.

## 13. Dashboard Pages

| **Page**            | **Content**                                                                                                                                                                                                                                                                                                                                                         |
|---------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Incidents**       | List with status badges and a create-incident form.                                                                                                                                                                                                                                                                                                                 |
| **Incident detail** | Tabs: Timeline (chronological, evidence-linked); Evidence (filter by type and service, payload and redactions); Hypotheses (ranked, confidence, FOR/AGAINST evidence chips that open the evidence); Report (facts, hypotheses and recommendations separated, Markdown export); Agent Trace (live SSE of node and tool steps with latency, token and cost metadata). |
| **Evaluation**      | Run a replay and view the scorecard. Ground truth is revealed only here, after a run completes.                                                                                                                                                                                                                                                                     |

A persistent banner states that the investigation is read-only and no remediation is executed. Recommendations are labelled "Requires human approval". The frontend uses Vite, React and TypeScript with Vitest component tests.

## 14. Tooling, Commands and Environment

| **Area**                   | **Decision**                                                                                                                                                                                                                                          |
|----------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Backend**                | Python 3.12, FastAPI, Pydantic v2, pydantic-settings, SQLAlchemy 2, Alembic, psycopg 3, httpx                                                                                                                                                         |
| **Python tooling**         | uv workspace (pip and venv as fallback), ruff, mypy --strict on packages and apps/api, pytest, pytest-asyncio                                                                                                                                         |
| **Frontend tooling**       | Vite, React 18, TypeScript, Vitest, React Testing Library, eslint, tsc --noEmit                                                                                                                                                                       |
| **Infrastructure**         | Docker Compose v2, official postgres:16 image (not bitnami), OpenTelemetry Collector contrib, GitHub Actions                                                                                                                                          |
| **Docker-dependent tests** | Marked @pytest.mark.docker and skipped automatically when Docker is unavailable                                                                                                                                                                       |
| **Environment file**       | Committed as .env.example (the original upload name ENVIRONMENT_VARIABLES.example.txt is superseded). Variables: APP_ENV, DATABASE_URL, TELEMETRY_DATABASE_URL, OTEL_EXPORTER_OTLP_ENDPOINT, MODEL_PROVIDER (default mock), MODEL_NAME, MODEL_API_KEY |

Command amendments to AIPI-12: make down, make lint, make record-golden and make demo are added. make demo runs: up, seed traffic, chaos-kill, create incident, investigate, eval. CI additionally runs a secret scanner (gitleaks) and enforces the hallucination gate.

## 15. New Architecture Decision Records

| **ADR**     | **Decision**                                                    | **Reason**                                                                                                            |
|-------------|-----------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------|
| **ADR-007** | Collector sends OTLP JSON to an API ingest endpoint             | The Collector has no PostgreSQL exporter; ingestion in the API keeps normalization and redaction in one tested place. |
| **ADR-008** | Mock LLM adapter is the default for tests, CI and the base demo | Deterministic, offline, free; makes golden tests and CI reproducible without API keys.                                |
| **ADR-009** | Ground truth isolated by separate schema and database role      | Makes it provable that the agent and investigation APIs cannot see labels.                                            |
| **ADR-010** | Keyword/BM25 runbook search; no pgvector in the MVP             | A small runbook set does not justify an embedding pipeline; revisit only if measured retrieval quality demands it.    |

## 16. Open Questions: Status

| **AIPI-14 open question**                                                                | **Status**       | **Note**                                                                                                   |
|------------------------------------------------------------------------------------------|------------------|------------------------------------------------------------------------------------------------------------|
| **Which LLM provider and model gives the best structured reasoning at acceptable cost?** | Partly resolved  | Adapter interface and mock default decided; real model comparison remains future work.                     |
| **Is pgvector needed for runbook retrieval?**                                            | Resolved for MVP | No. Keyword/BM25 (ADR-010).                                                                                |
| **Should logs stay in PostgreSQL or move after profiling?**                              | Open             | PostgreSQL for MVP (ADR-002); revisit after measuring volume.                                              |
| **How to calibrate confidence across heterogeneous scenarios?**                          | Open             | Starting weights defined in section 8.2; calibrate with more scenarios after the evaluation harness works. |

## 17. Amendment Index by Document

| **Document**                   | **Amended by this addendum**                                                                                   |
|--------------------------------|----------------------------------------------------------------------------------------------------------------|
| **AIPI-02 Architecture**       | Ingestion path (4), topology (3), roles (5), dashboard pages (13).                                             |
| **AIPI-03 Agentic AI**         | Correlators, confidence formula, tool scope policy, injection hardening, adapters (8), report schema (9).      |
| **AIPI-04 Telemetry**          | Tables (4), evidence ID and redaction (4), observable vs ground truth (5, 7).                                  |
| **AIPI-05 API**                | New endpoints, events, validation, error codes (10).                                                           |
| **AIPI-06 Database**           | New tables and columns, ground_truth schema, roles (5, 11).                                                    |
| **AIPI-07 Evaluation**         | Hallucination gate, golden fixtures, tracking, exit behavior (12).                                             |
| **AIPI-08 Roadmap**            | Demo services in M0/M1, runbooks, scope unchanged (3, 15).                                                     |
| **AIPI-10 Security**           | Roles, read-only enforcement tests, redaction timing, event-watcher note (5, 8).                               |
| **AIPI-11 Deployment**         | Tooling, environment file, CI additions (14).                                                                  |
| **AIPI-12 README**             | New make targets (14).                                                                                         |
| **AIPI-14 Decision Log**       | ADR-007 to ADR-010, open question status (15, 16).                                                             |
| **AIPI-15 Codex Instructions** | Superseded for execution by CODEX_MASTER_PROMPT.md, which merges documents 00–16 into one phased build prompt. |
