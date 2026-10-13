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


## ADR-016 — Full-scope correlation and summarized evidence with type floors

The initial relevance-v1 sample ranking preserved decisive metrics but let repeated
samples consume all 50 slots and biased rule inputs. It is superseded by
series-floors-v2. Correlators run once over **all** telemetry in the authorized,
authoritative incident/service/time scope, before any summary or cap. Four
parameterized SELECTs use investigator_ro in one repeatable-read transaction.
There is no silent per-source limit; database timeouts fail explicitly. The
current local MVP materializes up to a six-hour scoped window in memory; larger
production workloads should replace this with equivalent SQL aggregates.

Full-scope signals are frozen with the first evidence snapshot. Selection never
changes `/signals`, including when selected-only correlation misses a rule or
creates a sampling false positive. `capped_rules` exposes that selected-only
diagnostic; it is not used for investigation signals. All full-scope cited raw
observations are also persisted immutably, independently of the 50 display items,
and can be resolved through the scoped evidence-by-ID endpoint. No citation may
escape the frozen incident/service/time boundary. Late telemetry cannot change
saved signals, summaries, or IDs.

Each (service, metric_name, canonical labels_json) series becomes one metric
summary: first/last/min/max values, sample count, first/last timestamps and source
references, plus chronological paused/healthy transitions. The normalizer stores
histogram sample data in labels_json.histogram; this reserved sample-data key is
excluded from series identity, while genuine route/resource labels remain. Summary source_ref
hashes the series identity and ordered scoped sample source references, so a
changed membership creates a new immutable version. IDs still follow exactly
`ev_ + sha256(type|source_ref)[:16]`; sample IDs are unchanged. Summaries preserve
conflicting health values (min/max), rather than suggesting a healthy primary
from the last recovered sample. Summary-aware pure rules retain those semantics.

Selection reserves up to ten ERROR/FATAL/WARN/WARNING logs and five error/slow
traces (slow >=250 ms), subject to available qualifying observations. Runtime
lifecycle events and summaries of the fixed rule-metric name list occupy the
remaining space first, then additional severe logs/error or slow traces, then
ordinary telemetry. Severity order is FATAL, ERROR, WARN/WARNING, ordinary;
traces inherit the strongest linked scoped log severity, error status, or slow
threshold. Ties use timestamp then source_ref. This extends the earlier feature
allowlist with trace status/duration to meet the explicit error/slow floor.
Metric values, free-text causal labels, scenario IDs and ground truth never rank.

If protected events/series plus floors exceed 50, keeping them all is impossible.
Reserve the floors and take protected items in deterministic priority order;
report omitted candidates by type. Fewer than ten severe logs or five qualifying
traces results in a floor up to availability, never fabricated observations.
`raw_counts` counts rows; `available_counts` counts summary candidates (metric
series instead of samples); `dropped_counts` counts candidates omitted by the cap.
Compression is not counted as dropped evidence. The v2 cache namespace leaves
previous immutable snapshots intact.

Live tests retain kill die(137)/start, gateway ERROR logs, replica lag/pause/health
summaries, stale-read WARN logs and ReplicaReadTimeout evidence. A stale read
already exhausts three bounded retries; its log/span now explicitly identifies
that application retry deadline, without implying a primary or network outage.
The ErrorSpikeRule adds matching-operation span-p95 latency versus early-window
baseline, completing its documented error-rate/latency behavior. Live windows
include 30 seconds of steady pre-fault telemetry for an honest baseline. The kill
verifier compares the /checkout 503 counter only, avoiding unrelated /orders
series at identical export timestamps. Offline crowded windows prove floors,
oldest decisive retention, series transitions, stable IDs, and full-scope rule
invariance even when a particular witness falls outside the displayed bundle.

## ADR-017 — Scoped investigation tools, supervisor audits and synthetic-first mock

M4a first authored `synthetic:true` observable fixture bundles. Hidden truth files
are read only by `aipi_evaluation.golden`; agents/tools do not import the scorer,
chaos code or truth readers. The deterministic mock derives falsifiable competing
hypotheses solely from full-scope correlator signals. Optional paid providers are
not implemented in this local release, as explicitly permitted by the M4 request.

Six typed tools expose fixed allowlisted SELECT operations under investigator_ro.
A runner binds its owning incident, independently reloads its authoritative scope,
rejects widening/cross-incident requests, validates source results and attempts
at most three reads (initial + two timeout retries). The API supervisor owns the
restricted writer and records immutable tool calls/events and evidence provenance;
query backends never receive a writer or administrator credential. Local Markdown
runbooks are service-tagged BM25 chunks with versioned content/source IDs.

Replication status uses historical scoped lag/paused/health metrics. A live WAL
receiver view observation is included only if its observation timestamp is inside
the requested incident window. Current recovered state is not evidence about a
completed historical outage. Both connections assert investigator_ro identity.

Confidence uses the exact section-8 weighted formula and capped contradiction
penalty. Components are deterministic: direct conjunction coverage/proximity/check
=1; nonspecific symptom coverage=.4, proximity=.2, check=0; retrieval quality=1
(or .8 for truncated retrieval, 0 without supporting evidence). Unique material
contradicting families each add .15, capped at .45. The model has no score input.
Report generation validates every structured citation and retries repair once;
recommendations are human-review checks, require approval and are never executed.
Full-scope rule witnesses remain usable even when absent from the 50-item display.

## ADR-018 — Validated LangGraph, background supervisor and scoped report provenance

M4b compiles a six-node StateGraph with Pydantic state: Triage → Retriever →
Hypothesis → Verifier → Ranker → Reporter. Each transition is revalidated and
emits durable events and nested OTel spans. Reporter has one explicit repair
edge; a second invalid output fails the job. Malformed hypothesis outputs get
one schema correction. Confidence remains the fixed deterministic formula.
The mock consumes correlator signals and never receives hidden labels or scores.

The supervisor freezes full-scope signals and resolves their immutable witnesses
before model reasoning; tools may add bounded telemetry and runbook observations.
Every fact cites the complete original rule witness set, including observations
outside the display cap. Competing hypotheses preserve FOR/AGAINST families;
primary outage retains nonspecific read symptoms FOR and healthy primary AGAINST.
Report timelines show verified causal/contradicting observations chronologically.
All structured citations and Markdown IDs are validated. Stored agent_evidence
provenance enables evidence-by-ID lookup for additional tool/runbook citations,
with the same authoritative incident/service/time bounds and immutable records.

FastAPI BackgroundTasks implements a single-process local job (no queue).
Status and artifacts persist in PostgreSQL; interrupted queued/running jobs fail
explicitly on startup. SSE streams ordered persisted events with seq IDs, a
Last-Event-ID/after cursor, heartbeat and terminal done event; format=json provides
an ordered snapshot. Tokens/cost are zero for mock; actual latency, source count,
confidence and tool failures are instrumented. Paid adapters remain optional and
unimplemented. The M5 scorer/replay and dashboard remain future phase gates.

LangGraph API usage was checked against its official Graph API documentation:
https://docs.langchain.com/oss/python/langgraph/graph-api. Locked version 1.2.15
runs on host Python 3.12 and native linux/arm64 Docker. Runtime build metadata uses
AIPI_CODE_COMMIT (working-tree builds state that explicitly); no agent runs git.

Reporter output must preserve the verified hypothesis ordering/confidence and
the factory's read-only recommendations, even if a candidate is otherwise
schema-valid. It cannot replace them with model confidence or mutating advice.
Recommendation citations include a retrieved scoped runbook where available.
Nonspecific error logs/failed traces count as request symptoms for competing
hypotheses, but lifecycle/pause counterevidence and missing direct causal checks
prevent those secondary symptoms from outranking the verified root cause.

## ADR-019 — Isolated scorer, bounded entailment and repeated recorded evaluation

Evaluation truth access belongs to a separate FastAPI scorer service, using
chaos_admin with default_transaction_read_only=on for fixed protected-run SELECTs.
The incident API receives only a scorer URL and public typed score contracts. It
has neither the truth credential nor golden truth fixture files. Golden agent
replay executes in a separate Python process with an allowlisted environment and
observable JSON on stdin; scorer/DB/model secrets are not inherited. Only the
scorer opens the separate truth file, after the observable report is produced.

POST /api/evaluations/replay supports golden replay and recorded-incident replay.
Recorded mode validates a completed, recovered protected run against the incident
window, then resolves report citations through scoped HTTP lookup. Fault injection
remains the host CLI's bounded chaos operation; the API/scorer never gains a Docker
socket or remediation tool. Evaluation jobs/experiment metadata persist in
public.evaluation_runs with FKs to scenarios, runs and investigations. Public score
responses omit expected causal labels. Restarted in-memory scorer jobs fail clearly.

The pure hallucination gate checks all cited IDs, claim-to-evidence support,
explicit numeric field/metric quotations, trace IDs, quoted log/deployment text,
timeline content/time and Markdown consistency. It fails closed outside the
implemented MVP claim vocabulary: deterministic correlator facts, fixed category
hypotheses and approval-required read-only next checks. Semantic precision counts
supported claim/evidence pairs, not merely existing IDs. This is an auditable
bounded semantic gate, not a general natural-language entailment model. A new
report vocabulary requires extending its predicates and adversarial tests.

Top-1/Top-3 compare the protected category. Coverage measures the fraction of
required witness families cited (kill: die137, recovery, 5xx, failed span, gateway
error; lag: seconds, backlog, paused replay, healthy primary, stale read, timeout).
Unsupported rate divides unsupported structured claims by material claim count;
critical violations on any report surface independently fail the gate. Contradiction
handling requires the known false lead ranked lower with correct AGAINST evidence.
Tool efficiency divides unique supported cited observations from the whole pipeline
by audited tool calls; per-token efficiency is null when mock uses zero tokens.
Latency includes the credential-free child process for offline replay, and actual
persisted investigation latency for live runs.

make record-golden runs three separate recovered faults per scenario, scores them
through the live API and records all per-run metrics, population variance/stddev,
median/range and misses. Latest real raw scoped telemetry replaces root golden
bundles (synthetic=false); the original hand-authored corpus remains under
fixtures/synthetic for unit tests. The poisoned golden adds an explicitly synthetic
untrusted log to the recorded kill window; expected labels stay in *.truth.json.
Scorecards and repeat summaries are JSON/Markdown under ignored eval_reports;
committed verification summaries and PROGRESS preserve real measured results.


Scorer API scorecards persist in a named evaluation-results volume initialized
for non-root UID 10001. Host make eval/record-golden write ./eval_reports themselves;
this avoids Docker-created root-owned bind directories failing on fresh Linux CI.

The Python Dockerfile has separate api/scorer targets sharing a runtime stage.
The scorer target alone copies truth fixtures. This removes the implicit dependency
on an already-built aipi-python:local image during parallel fresh-clone Compose
builds. API/demo/migration targets continue to contain no truth fixture files.

Host CLI experiment metadata marks an uncommitted checkout with +working-tree;
clean CI/committed runs record their actual HEAD. Build metadata uses the explicit
CODE_COMMIT argument (or working-tree) without passing git/credentials to agents.

The critical root-cause surface must satisfy its causal conjunction from linked
FOR witnesses (plus cited primary health for replica lag). Merely relevant timeout
symptoms cannot support a top-ranked primary outage. The pure gate checks this
without reading truth; Top-1 correctness is a separate oracle comparison.
