# Architecture

The README diagram describes the running Compose topology. Traffic reaches gateway;
checkout-api writes orders to PostgreSQL primary, orders-api reads the streaming
standby. The lag probe samples the primary LSN and replica replay state every two
seconds. The lab watcher reads Docker lifecycle events for its explicit project.

All demo processes use OTel SDK traces, metrics and correlated logs. Collector
contrib 0.123.0 exports OTLP HTTP **JSON** to internal API ingestion. The API parses,
normalizes, redacts and inserts idempotent source rows. PostgreSQL 16 contains
public telemetry, incidents and artifacts, plus restricted ground_truth tables.
Services use app_rw/app_ro; ingestion and artifact persistence use telemetry_writer;
retrieval uses investigator_ro. See SECURITY for the actual privilege boundaries.

A created incident freezes one service, explicitly related services and a positive
time window of at most six hours. Four telemetry SELECTs form a repeatable-read
snapshot. Pure correlators run over full scoped source data before display
selection. Metric series summaries and per-type floors keep the display bundle
at 50. Raw rule witnesses remain frozen and resolvable by incident/evidence ID.
Evidence/bundle mutation is blocked by database triggers. A new scope or source
version creates another immutable snapshot instead of altering old observations.

FastAPI schedules an in-process investigation background task. A Pydantic-validated
LangGraph runs Triage → Retriever → Hypothesis → Verifier → Ranker → Reporter.
Six typed read-only tools collect bounded observations and BM25 runbook chunks;
the supervisor writes tool audit and investigation event rows. Initial read plus
two timeout retries are allowed. The mock proposes competing falsifiable causes
from correlator signals. Fixed scoring weights and material contradictions set
confidence. Reporter validates citations/order/claims, repairs once, then fails.
No investigation tool executes shell, SQL supplied by a model or remediation.

The React 18/TypeScript dashboard uses Vite's same-origin /api proxy. Incident
detail tabs show timeline, evidence, hypotheses, report and persisted SSE events.
Fetch SSE resumes with a sequence cursor, suppresses duplicates and retries dropped
connections. A citation beyond the displayed bundle resolves through the scoped
by-ID API. Facts, hypotheses and approval-required recommendations stay separate.

The separate scorer service alone has the protected truth connection. The API
proxies typed replay requests/results; it has no truth credential or truth fixture
files. Golden replay runs the graph in a credential-free child process given
observable JSON; the scorer separately reads *.truth.json. Recorded replay checks
the recovered chaos run and resolves every report citation through the incident
API. Terminal scored jobs have a separate evaluation-only truth disclosure route.
The agent never consumes scores or protected labels.

API and scorer jobs are single-process local tasks, not durable distributed
queues. Persisted interrupted jobs fail on restart. There is no app authentication
or RBAC. Host publications bind to loopback; scorer has no public host port.
See DEPLOYMENT for isolation and operating constraints; DECISIONS records ADRs.

## Storage and ownership

All schemas are created by [Alembic migrations](../infra/docker/migrations/versions).
The public database separates source telemetry, frozen evidence and investigation
artifacts; role grants enforce which component can read or write each family.

| Data | Owner and purpose |
|---|---|
| `telemetry_logs`, `telemetry_metrics`, `telemetry_spans`, `telemetry_events` | Normalized, redacted observable sources, inserted idempotently by ingestion |
| `incidents`, `evidence`, `evidence_bundles`, `scope_denials` | Incident scope, immutable snapshots and sanitized policy-denial audit |
| `investigations`, `hypotheses`, `hypothesis_evidence`, `reports`, `recommendations` | Run status, ranked FOR/AGAINST relations and stored report |
| `tool_calls`, `investigation_events`, `agent_evidence` | Tool/node audit, SSE sequence and scoped evidence provenance |
| `evaluation_runs` | Scorer job status, experiment metadata and scorecards |
| `ground_truth.scenarios`, `ground_truth.chaos_runs` | Protected expected labels and actual injection/recovery records; scorer/host chaos only |

Typed service/time columns and indexes support bounded queries; JSONB stores
heterogeneous payloads. Artifact foreign keys preserve incident/investigation
ownership. `evidence` is keyed by incident plus evidence ID, so a source-derived
ID cannot grant cross-incident access. There is no automatic retention or
partition management in this local implementation.

## Confidence scoring

The [scoring module](../packages/agents/src/aipi_agents/scoring_config.py) computes:

```text
score = 0.35 * evidence_coverage
      + 0.25 * causal_proximity
      + 0.20 * retrieval_quality
      + 0.20 * deterministic_check_score
      - min(0.45, 0.15 * material_contradicting_evidence_count)
confidence = clamp(score, 0, 1)
```

The four positive features are validated in [0, 1]; contradiction count is a
nonnegative integer. Pure verification derives features from observable evidence,
then ranking applies this formula. No model self-confidence is accepted. Fixed
input/contradiction tests cover the weights and clamping. These heuristic weights
are not calibrated probabilities of correctness across arbitrary incidents.
