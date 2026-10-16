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
