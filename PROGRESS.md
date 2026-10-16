# PROGRESS.md — AIPI build log

> Source of truth for "where are we and where is it broken".
> Codex: update this file at the END of every phase and every time a command fails. Follow this format exactly. Never mark anything done unless you ran the verification command and saw it pass. Paste real command output (trimmed), not summaries.

**Last updated:** 2026-10-17 03:43 IST
**Current phase:** M7 Polish DONE (isolated fresh-clone gate passed)
**Next action:** No further build phase. Preserve the original main replica; any F052 reseed requires separate authorization. Do not push.
**Overall:** 7 / 7 phases complete
**Docker available:** yes — Docker Desktop aarch64; daemon access requires sandbox escalation
**LLM provider:** mock

---

## 1. PHASE STATUS (one-glance table)

Status values: `NOT STARTED` · `IN PROGRESS` · `BLOCKED` · `PARTIAL` · `DONE (gate passed)`

| Phase | Name | Status | Gate command(s) | Gate result | Commit |
|---|---|---|---|---|---|
| M0+M1 | Foundation + Observability | DONE (gate passed) | `make up`, `make test`, `make lint` | Healthy native arm64 lab; follow-up audit: 21 Python + 1 web tests passed | `ea3aee2`; audit `e01c082` |
| M2 | Chaos Lab | DONE (gate passed) | `make chaos-kill`, `make chaos-lag`, `make test`, `make lint` | Both live scenarios recovered; 33 Python + 1 web tests passed | `4b73c8c` |
| M3 | Incident Core | DONE (gate passed) | `make test`, `make lint`; live incident replay/isolation tests | 71 Python + 1 web passed; full-scope rules invariant to cap; metric summaries, type floors and stable IDs | `60790a4`; prioritization `b98c640`; refinement `37c8acc` |
| M4 | Agents + Tools + Report | DONE (gate passed) | `make test`, `make lint`; synthetic goldens and live reports | 102 Python + 1 web; 18 live tests, none skipped; both scoped mock reports valid | M4a `afba25f`; M4b `5de61e4` |
| M5 | Evaluation | DONE (gate passed) | `make eval`, `make record-golden`, `make test`, `make lint` | 123 Python + 1 web; 22 live tests; six repeated live reports passed final gate, variance recorded | `4a95ed9` |
| M6 | Dashboard | DONE (gate passed) | `make test`, `make lint`, `make up`; live UI gate | 128 Python + 26 web verified; 22 live tests; real browser incident-to-recorded-evaluation passed | `9e9a840` |
| M7 | Polish | DONE (gate passed) | fresh-clone README; two consecutive `make test`; lint/actionlint/full-history scan | 140 Python + 26 UI twice; 24 live tests each; original replica preserved (F052) | `feat(M7)` phase commit |

---

## 2. PHASE CHECKLISTS

Tick a box only after verifying it. Add a one-line note (file/test name) next to each ticked item.

### M0+M1 Foundation + Observability
- [x] Monorepo skeleton matches layout; uv workspace installs — `make setup`: frozen sync checked 64 packages; npm ci completed
- [x] Typed config + `.env.example` — `test_settings_hide_credentials_and_validate_provider`; generated ignored .env
- [x] Compose: PG primary + replica healthy — `make up`; streaming standby + live replica read verified
- [x] Compose: otel-collector, api, gateway, checkout-api, orders-api, pg-lag-probe, event-watcher, traffic — `make up`, Collector HTTP health, `make seed-traffic`; all enabled services healthy
- [x] `/healthz` + `/readyz` on all services — API + all six demo services verified; web /healthz; Collector health extension /
- [x] OTel traces/metrics/logs from demo services — SDK instrumentation; checkout correlation, probe metrics, real watcher events; seeded traffic healthy
- [x] Collector → API `/internal/otlp/v1/*` ingest works — live integration through Collector HTTP JSON exporters
- [x] Telemetry tables + normalization + redaction (with tests) — Alembic revision 0001; parser/redaction/component + live storage tests
- [x] One request → correlated trace + log (same trace_id) + metric in DB — `test_request_has_correlated_trace_log_metric_and_replica_read`
- [x] Makefile targets, CI workflow, lint/type/test commands — `make lint`, `make build-web`; Compose config validation; actionlint 1.7.7 passed
- [x] **GATE:** `make up` healthy + `make test` green — 20 Python tests passed (4 live Docker integration, none skipped), 1 Vitest test passed


Verification evidence (2026-10-13, native Apple Silicon):

```text
make up: exit 0
Healthy: http://localhost:8000/readyz
Healthy: http://localhost:8080/readyz
Healthy: http://localhost:5173/healthz
Healthy: http://localhost:13133/
make seed-traffic: Container aipi-traffic-1 Healthy
Demo endpoint checks: gateway, checkout-api, orders-api, pg-lag-probe,
  event-watcher, traffic: [200, 200] for /healthz and /readyz
make test (Node v25.9.0 explicitly selected in approved shell):
  20 passed, 1 warning in 5.83s (Python; 4 live integration tests, none skipped)
  Test Files 1 passed (1); Tests 1 passed (1) (Vitest 4.1.11)
make lint: All checks passed!; 55 files already formatted;
  Success: no issues found in 15 source files; eslint and tsc exit 0
make build-web: vite v7.3.7; 27 modules transformed; built in 342ms
make setup: Checked 64 packages; npm ci completed; found 0 vulnerabilities
Compose base + test overlay config --quiet: exit 0
rhysd/actionlint:1.7.7: exit 0
Gitleaks v8.24.2 source snapshot: no leaks found
Image inspect: postgres:16, aipi-python:local, aipi-web:latest,
  otel/opentelemetry-collector-contrib:0.123.0 all linux/arm64
```

The sandbox's approved shell initially selected system Node 20; all final npm
setup/tests explicitly selected `/Users/akshat/.nvm/versions/node/v25.9.0/bin`.
Normal workspace commands and the web container use Node 25. Disposable lab
credentials exposed in an early test traceback were rotated; failure output now
suppresses driver connection locals. The lab and seeded traffic remain running.

M0+M1 follow-up audit (2026-10-13): missing web readiness endpoint, gateway upstream
readiness checks, complete probe/watcher work traces and metrics, and successful
gateway application logs. All repaired before M2 implementation.

```text
make up: exit 0; Healthy: API / gateway / web / Collector
make seed-traffic: Container aipi-traffic-1 Healthy
make lint: All checks passed!; 55 files already formatted;
  Success: no issues found in 15 source files; ESLint / tsc exit 0
make test: 21 passed, 1 warning in 6.32s; Vitest: 1 passed
```

The live audit test verifies logs, traces, and metrics for gateway, checkout,
orders, lag probe, and event watcher. Seeded traffic is active. Gateway readiness
now checks both upstream readiness endpoints; web exposes /readyz. Future
incident/agent/evaluation/dashboard deliverables remain assigned to M3–M6.

### M2 Chaos Lab
- [x] Scenario schema + SCN-001 + SCN-002 scripts — schema contract tests passed
- [x] Ground truth written to `ground_truth.chaos_runs` — migration 0002; live run metadata checks; non-chaos roles denied
- [x] Precondition checks + recovery verification — unit failure paths, overlap refusal, live HTTP/DB/Docker checks
- [x] A: die→start events + 5xx spike visible — live make chaos-kill passed
- [x] B: lag rises, `replica_replay_paused=1`, primary healthy — live make chaos-lag passed
- [x] `make chaos-kill`, `make chaos-lag` — both exit 0 on this machine
- [x] **GATE:** both scenarios run and recover — live integration runs repeated successfully in full suite

Live SCN-001 command output (2026-10-13, Apple Silicon):

```text
make chaos-kill: exit 0
"run_id": "716ffec7-76b3-4c4c-bb10-99a137d5e331",
"scenario_id": "SCN-001", "passed": true, "recovery_status": "verified",
"gateway_5xx_requests": 69, "explicit_start_required": true,
"event": "die", "ts": "2026-10-12T19:57:09.408357+00:00", "exit_code": "137"
"event": "start", "ts": "2026-10-12T19:57:17.840432+00:00"
"gateway_failed_spans": 258, "gateway_error_logs": 86,
"gateway_503_counter_increase": 75.0
Restricted-role integration: 1 passed in 1.11s
```

Live SCN-002 command output:

```text
make chaos-lag: exit 0
"run_id": "4e42bc15-cf04-4042-9eb2-976b5e7e645c",
"scenario_id": "SCN-002", "passed": true, "recovery_status": "verified",
"healthy_primary_writes": 10,
"direct_primary_health_samples": [true,true,true,true,true,true,true,true,true,true],
"replica_read_recovered": true, "replay_resumed": true,
"lag_samples": [
  {"ts": "2026-10-12T19:57:39.556698+00:00", "seconds": 0.69015},
  {"ts": "2026-10-12T19:57:41.565357+00:00", "seconds": 2.749074},
  {"ts": "2026-10-12T19:57:43.570420+00:00", "seconds": 4.762386},
  {"ts": "2026-10-12T19:57:45.574960+00:00", "seconds": 6.792152},
  {"ts": "2026-10-12T19:57:47.581467+00:00", "seconds": 8.821291}
],
"max_lag_bytes": 1349776.0, "replay_paused_samples": 5,
"primary_healthy_samples": 5, "stale_read_logs": 13
```

Final M2 verification output:

```text
make up: exit 0; API / gateway / web / Collector healthy
make seed-traffic: Container aipi-traffic-1 Healthy
make lint: All checks passed!; 67 files already formatted;
  Success: no issues found in 23 source files; ESLint and tsc exit 0
make test (host Python 3.12.0 and explicit Node v25.9.0):
  33 passed, 1 warning in 38.09s
  8 live Docker tests, including both scenarios; none skipped
  Test Files 1 passed (1); Tests 1 passed (1); Duration 548ms
Post-gate lab: all six demo containers healthy; primary healthy;
  standby unpaused; new order visible
Final integration run: SCN-002 completed verified
Final integration run: SCN-001 completed verified
rhysd/actionlint:1.7.7: exit 0
Gitleaks v8.24.2 final source: scanned ~412708 bytes (412.71 KB); no leaks found
```

Both scripts and live tests use the actual Docker Desktop lab. Runtime labels,
scenario snapshots and injection records are confined to the restricted schema;
API/demo identities have no schema access or replay-control grant. No live LLM
or investigation accuracy claims are made at this phase. Static templates remain
in source; stdout reports observed signals rather than expected causal labels.

### M3 Incident Core

Dedicated live M3 gate output:

```text
uv run pytest tests/integration/test_incidents.py -v -s --tb=short
SCN-001: incident_id=d9856c8b-563b-46af-bc6e-b739f6febab4
  items=50; truncated=true; identical_ids=true;
  rules=[ProcessExitRule]; chaos_recovery=verified
SCN-002: incident_id=7a3c46e2-fbe7-442a-bb71-724f07970de1
  items=50; truncated=true; identical_ids=true;
  rules=[ErrorSpikeRule, ReplicaLagRule, DownstreamTimeoutRule, PrimaryHealthRule];
  chaos_recovery=verified
5 passed in 32.94s
```

Both real scenarios recovered. Each window came from host clock bounds around
scenario execution, not hidden injection metadata. The dedicated suite also
verified all four telemetry types, cap/truncation, late-arrival snapshot stability,
SQL mutation/truncate guards, denial audits, forged-scope denial, API validation,
and ground-truth privilege failures. ErrorSpikeRule subsequently gained a guard
against comparing different services or label series, covered by a new unit test.


Baseline required before implementation (existing .env preserved):

```text
make test: 33 passed, 1 warning in 34.98s
Vitest: Test Files 1 passed (1); Tests 1 passed (1); Duration 602ms
```
- [x] Incident POST/list/by-id + validation — live HTTP 201/422/404, positive max 6h and timezone checks
- [x] Bounded evidence retrieval + stable evidence IDs — both real windows return identical IDs; cap 50 and truncation tested
- [x] Immutable evidence, timeline builder, ScopePolicy — deep-frozen payloads; SQL guards; narrowing/denials audited
- [x] Correlators (5 rules) + unit tests — 9 pure-rule tests; live ProcessExit/ReplicaLag/PrimaryHealth assertions
- [x] Error contract + request-id middleware — stable codes and response/header request IDs; sanitized validation
- [x] Ground truth unreachable from API/investigator/retrieval — real privilege failures, source allowlist, forged-boundary denial; public catalog fields only
- [x] **GATE:** same evidence IDs on re-run — both real scenarios, 13 live Docker tests; final full suite green

Final M3 gate (native host Python 3.12.0, explicit Node v25.9.0):

```text
Baseline make test: 33 passed, 1 warning in 34.98s; Vitest 1 passed
Docker Compose build/up --wait: exit 0; migration and API healthy
make seed-traffic: Container aipi-traffic-1 Healthy
Offline suite: 46 passed, 12 deselected, 1 warning in 1.88s
Final make lint: All checks passed!; 80 files already formatted;
  Success: no issues found in 31 source files; ESLint/tsc exit 0
OpenAPI/incident/ingest component checks: 27 passed, 1 warning in 1.89s
Final make test: 60 passed, 1 warning in 69.00s (0:01:09)
  13 live Docker tests, none skipped; both scenarios run/recover again
  Test Files 1 passed (1); Tests 1 passed (1); Duration 727ms
rhysd/actionlint:1.7.7: exit 0
Gitleaks v8.24.2 final source: scanned ~486528 bytes (486.53 KB); no leaks found
.env content unchanged from start of M3
```

Final live snapshot checks (real output, trimmed):

```text
Post-gate lab: healthy primary, unpaused standby, six healthy demo containers,
  fresh order visible
incident_id=54aba96a-629a-4dbe-86e7-a5f1b9f9fd5e; service=orders-api
  items=50; identical_ids=true; truncated=true
  ids_sha256=cc19caf276a206987867692756d4daff6b7d219399c54c9842be5b23b7db8213
  rules=[ReplicaLagRule, DownstreamTimeoutRule, PrimaryHealthRule]
  contradicts=[primary outage]
incident_id=e47a1305-30d2-4e81-bdb2-20c81754e65c; service=checkout-api
  items=50; identical_ids=true; truncated=true
  ids_sha256=c45d37e1cad097971e7cf8227d13b2b2a65282858bcad1d712092d6ec8fbbb07
  rules=[ProcessExitRule]; contradicts=[]
```

The only warning is the existing FastAPI/httpx TestClient deprecation. CI was
validated locally; GitHub-hosted CI was not run. Runtime API responses and
OpenAPI now agree on ErrorEnvelope. Existing credentials were reused throughout;
no setup-env or .env regeneration command was executed. Retrieval uses only
investigator_ro; application writes are explicit SELECT/INSERT grants to the
existing writer. No agents, LLM adapters, LangGraph, or mutating tools were added.

M3 prioritization follow-up (historical relevance-v1; superseded by the refinement below):

- Global relevance tiers use lifecycle names, a fixed metric-name list, and severity;
  traces inherit only linked scoped log severity. No metric values, span status,
  scenario IDs or ground-truth queries rank evidence.
- SQL and Python break ties by timestamp then source_ref; IDs retain the original
  type/source hash. relevance-v1 has a separate immutable snapshot cache namespace.
- Exact available_counts/dropped_counts cover all scoped rows, including beyond
  the per-source 50-candidate limit.
- M3 commit reference corrected to 60790a4; Decisions rows are contiguous again.
  Unit tests confirm definitions ADR-007 through ADR-015 in docs/DECISIONS.md.
- Complete real inventory (all 50 items per live scenario, grouped by type/service):
  [docs/verification/evidence-priority-live.txt](docs/verification/evidence-priority-live.txt).

```text
uv run pytest tests/integration/test_incidents.py -v -s --tb=short
SCN-001: selected=50
  available={event:2, metric:468, log:114, trace:572}
  dropped={event:0, metric:438, log:111, trace:557}
  selected by type={event:2, metric:30, log:3, trace:15}
  die exit_code=137: ev_bd70a98706ab4d09
  start: ev_5300ce76444ceabf
  identical_ids=true; ProcessExitRule; recovery=verified
SCN-002: selected=50
  available={event:0, metric:212, log:71, trace:268}
  dropped={event:0, metric:162, log:71, trace:268}
  selected by service={checkout-api:8, orders-api:16, pg-lag-probe:26} (all metrics)
  replica_lag_seconds=0.468535, 2.489531, 4.502678, 6.523544, 8.542551, 9.675256, 0
  replica_replay_paused=1 retained; primary_healthy=1 retained
  identical_ids=true; ReplicaLagRule + PrimaryHealthRule; recovery=verified
Live crowded synthetic window: 146 available; 50 selected;
  oldest die/start + four lag/health metrics retained
  dropped={event:38, metric:0, log:58, trace:0}
6 passed in 34.65s
Offline suite before live gate: 51 passed, 13 deselected, 1 warning in 2.14s
```

Final prioritization gate output:

```text
make test: 65 passed, 1 warning in 67.33s (0:01:07)
  14 live Docker tests, none skipped
  Vitest: Test Files 1 passed (1); Tests 1 passed (1); Duration 709ms
make lint: All checks passed!; 82 files already formatted;
  Success: no issues found in 32 source files; ESLint/tsc exit 0
Gitleaks v8.24.2: scanned ~526761 bytes (526.76 KB); no leaks found
.env unchanged
```

ADR-007 through ADR-015 were confirmed by definition entries, not merely mention
matches. PROGRESS Decisions table rows 1–6 are contiguous and well formed. M4a,
agents, LLM adapters and LangGraph remain not started.

M3 selection/correlation refinement (before M4a):

- [x] Confirmed old `/signals` correlated capped evidence; replaced it with frozen full-scope correlation under investigator_ro, before summary/cap. All cited raw sources are persisted immutably and resolvable through scoped evidence-by-ID.
- [x] One summary per metric series with first/last/min/max/count, sample timestamps/references and paused/healthy transitions. Histogram sample data is excluded from series labels; genuine labels remain. Raw evidence IDs retain the hash formula; summary IDs version ordered source membership.
- [x] Floors reserve up to 10 severe logs and 5 actual error/slow traces within 50. Protected lifecycle events and rule-metric summaries take remaining slots first. Insufficient observations/overflow are explicit; no evidence is fabricated.
- [x] Offline crowded tests cover oldest decisive observations, 100-sample series compression, severity/time/source determinism, transitions/conflicting health, protected overflow and a rule witness excluded from presentation.
- [x] Live rule equality is checked between independent full-scope retrieval before selection and API signals after selection. Selected-only `capped_rules` is diagnostic and never drives investigation signals.
- [x] Existing stale-read retry exhaustion now emits explicit ReplicaReadTimeout log/span telemetry; ErrorSpikeRule completes matching-operation span-latency p95 baseline detection. Kill metric verification compares the same /checkout series.
- ADR-016 and API contract document the refinement. `.env` is unchanged; no agents, models, LangGraph or M4a implementation.

Final real output (complete 100-item inventory and gate stdout in
[docs/verification/evidence-selection-live.txt](docs/verification/evidence-selection-live.txt)):

```text
PATH=<Node 25>/bin:$PATH PYTEST_ADDOPTS='-v -s --tb=short' make test
SCN-001 incident c2afb9c3-b398-4626-9542-ca1028420663:
  raw={event:2, metric:1662, log:294, trace:1429}
  summary candidates={event:2, metric:67, log:294, trace:1429}
  selected={event:2, metric:12, log:10, trace:26} total=50
  dropped candidates={event:0, metric:55, log:284, trace:1403}
  die(137) ev_1ac10a5e77a28cc1; start ev_422156b45c2c49c4
  10 gateway ERROR logs retained; >=5 actual error/slow traces
  before_cap=[ErrorSpikeRule, ProcessExitRule]
  after_cap=[ErrorSpikeRule, ProcessExitRule]
  selected_only=[ProcessExitRule] (diagnostic; never drives API signals)
  identical_ids=true; chaos_recovery=verified
SCN-002 incident dfa53bdb-c2aa-40b3-b913-73188e7f37a5:
  raw={event:0, metric:621, log:180, trace:711}
  summary candidates={event:0, metric:27, log:180, trace:711}
  selected={event:0, metric:11, log:10, trace:29} total=50
  dropped candidates={event:0, metric:16, log:170, trace:682}
  lag_seconds summary: first=0 last=0 min=0 max=10.259077 samples=23
  paused summary: first=0 last=0 min=0 max=1 samples=23
  primary health summary: first=1 last=1 min=1 max=1 samples=23
  stale-read WARN + ReplicaReadTimeout log/span retained; >=5 error/slow traces
  before_cap=after_cap=[DownstreamTimeoutRule, ErrorSpikeRule,
    PrimaryHealthRule, ReplicaLagRule]
  primary outage contradicted; identical_ids=true; chaos_recovery=verified
71 passed, 1 warning in 162.28s (0:02:42); 14 Docker tests, none skipped
Vitest: Test Files 1 passed (1); Tests 1 passed (1); Duration 1.11s
make lint: All checks passed!; 84 files already formatted;
  Success: no issues found in 33 source files; ESLint/tsc exit 0
.env unchanged: True
Gitleaks v8.24.2: scanned ~586816 bytes (586.82 KB); no leaks found
Scanner image: linux/arm64
```

The independent reader's full-scope rule names match published signals before/after
selection for both scenarios, and cached IDs/signals match exactly on repeated calls.
All signal citations exist in immutable evidence storage; evidence-by-ID lookup is
verified for an omitted witness and rejects unknown IDs/out-of-scope services.
The offline adverse-window test intentionally omits a timeout witness from the 50
items while preserving the full-scope DownstreamTimeoutRule and its saved citation.
Severe-log and trace floors are availability-bounded, with deterministic overflow
and candidate drop counts documented in ADR-016. M4a remains not started.

### M4 Agents + Tools + Report
- [x] 6 read-only tools + registry test (no mutating tool) — synthetic scope/timeout tests and live audit/privilege gate
- [x] LLM adapter interface + deterministic default mock — synthetic goldens; optional paid providers deferred per request
- [x] LangGraph nodes: Triage, Retriever, Hypothesis, Verifier, Ranker, Reporter — eight goldens and explicit node events/spans/repair-edge tests
- [x] Confidence scoring + unit tests — exact fixed-input section-8 formula; no model score accepted
- [x] Report schema validation + unknown-ID rejection — rejects/repairs once, then fails in unit tests
- [x] Investigation endpoints + SSE events — both real mock jobs, JSON snapshots, streamed ordered events, terminal state and validation/failure tests
- [x] Recommendations (recommend-only) — approval=true, executed=false in golden tests
- [x] Prompt-injection tests — poisoned golden conclusion unchanged; escaped delimiters and redaction
- [x] Golden tests on synthetic bundles, then live — authored fixtures first, offline/graph goldens, then real SCN-001/SCN-002; all cited IDs resolved
- [x] **GATE:** both scenarios → valid evidence-linked report, golden green — 102 Python + 1 web; all 18 Docker tests executed

M4a verification (actual output; gate passed):

```text
Baseline make test before new code: 71 passed, 1 warning in 143.87s; web 1 passed (893ms)
Synthetic goldens + scoring/safety/tools: 17 passed in 2.16s (including live audit)
Offline regression suite: 74 passed, 15 deselected, 1 warning in 2.73s
make lint: All checks passed!; 108 files already formatted;
  Success: no issues found in 48 source files; ESLint / tsc exit 0
M4a live: 3 calls + 3 events; denied widening logged;
  WAL receiver SELECT observed; investigator INSERT/UPDATE/truth denied
Docker image native rebuild + API readiness: exit 0 (migration 0004)
Gitleaks final source: scanned ~699468 bytes; no leaks found
make test final: 89 passed, 1 warning in 139.04s; 15 live Docker tests, none skipped
  Vitest: Test Files 1 passed; Tests 1 passed; Duration 824ms
Image inspection: aipi-python:local linux/arm64
.env checksum matches the pre-M3 preserved checksum: True
```

M4b verification (real output, native Apple Silicon):

```text
LangGraph dependency: Resolved 90 packages; installed langgraph==1.2.15
Synthetic + graph/repair/scoring checks: 26 passed in 2.40s
Initial live end-to-end reports: 2 passed in 109.42s (both scenarios recovered)
Failure/restart API gate: 1 passed in 2.47s
  report rejection persisted; request IDs preserved; interrupted jobs failed;
  invalid SSE cursors rejected
make test before final Reporter hardening: 100 passed in 253.02s; web 1 passed
make test final (final image + confidence/recommendation tampering tests):
  102 passed in 240.98s (0:04:00); 18 live Docker tests, none skipped
  Test Files 1 passed (1); Tests 1 passed (1); Duration 763ms
make lint final: All checks passed!; 116 files already formatted;
  Success: no issues found in 52 source files; ESLint / tsc exit 0
Docker build + API readiness: exit 0; image linux/arm64
Compose config --quiet: exit 0; actionlint 1.7.7: exit 0
make investigate ID=d1ac8743-02bf-46cd-9c8f-c3c689419e89: exit 0
  completed 408dea37-6b72-486e-a338-3deee7d60100; mock; 1044.954959 ms
  replica_lag rank 1 confidence .96; primary_outage rank 3 with AGAINST
Gitleaks final source (including real reports and completed log):
  scanned ~1939814 bytes (1.94 MB); no leaks found
.env checksum equals the preserved pre-M3 checksum: True
```

Final live report captures (all claims/structured citations/Markdown IDs validated,
all cited IDs resolved by scoped API lookup; same bundle IDs on repeat retrieval):

| Scenario | Incident ID | Investigation ID | Latency | Cited IDs | Outside bundle | Outside rule witnesses |
|---|---|---|---|---|---|---|
| SCN-001 | 36d8db4c-81d5-4f76-af55-4fbf58ec8f23 | c87fd71c-70bc-40e1-b862-c04f99e4e3de | 1655.6955 ms | 372 | 353 | 352 |
| SCN-002 | d1ac8743-02bf-46cd-9c8f-c3c689419e89 | 8c17d69d-29cb-495f-b572-9b08755ea3ab | 547.0889 ms | 140 | 117 | 116 |

SCN-001 top termination confidence .96 cites die `ev_d293a27f2daf3a3b`
(exit_code=137), start `ev_7541c306b52fca1d` and gateway ERROR log
`ev_6ee34843fc311ca1`. Dependency rank 2 has FOR request symptoms and AGAINST die.
SCN-002 top replica lag confidence .96 cites lag summary
`ev_923bf36c67395587` (max 10.24426 seconds), paused summary
`ev_ad3b4e8d57cb9c62` (0→1→0), WAL backlog, stale-read WARN log
`ev_7fad9c514caf08ce` and timeout DB trace `ev_cb673269f520f6fe`.
Primary outage ranks 3, confidence .20, with healthy-primary AGAINST
`ev_7a3f9f21676de2a9`. All recommendations require approval and executed=false.

Complete outside-ID arrays, their raw rule witness subsets, reports and resolved
observations are recorded in [SCN-001](docs/verification/m4/scn_001_service_kill.json)
and [SCN-002](docs/verification/m4/scn_002_replica_lag.json).
The outside counts include one scoped runbook in each report. Example outside
rule IDs: SCN-001 `ev_008d3d196fa57259`, `ev_01e20ca7b2c52b70`;
SCN-002 `ev_08ebfe80b74fcdf3`, `ev_0958286d97a06473`.
Both tests verify cross-incident denial, scope-widening rejection, no hidden
labels in API/report/events, six completed nodes and at least eight tool audits,
ordered JSON/SSE events and terminal done. All tools use investigator_ro;
live INSERT/UPDATE/ground-truth privilege refusals passed.

### M5 Evaluation
- [x] Metrics + hallucination gate — pure citation/entailment/quoted-value predicates with adversarial tests
- [x] Scorecards in `eval_reports/` — JSON + Markdown for goldens and all six live repeats; experiment metadata and population variance
- [x] Replay API + CLI, experiment metadata — isolated scorer, typed public proxy, persisted golden/recorded jobs, protected window checks
- [x] `make eval`, `make record-golden` — real make commands passed; root fixtures recorded (synthetic=false), separate truth and retained synthetic unit corpus
- [x] **GATE:** `make eval` exits non-zero on critical hallucination / Top-1 miss — actual make CLI negatives passed; real recorded goldens and six live repeats passed

M5 baseline (before new code):
```text
make test: 102 passed in 244.84s (0:04:04); 18 live Docker tests, none skipped
Vitest: Test Files 1 passed (1); Tests 1 passed (1); Duration 781ms
.env not regenerated
```

M5 interim real verification:
```text
Pure/negative gates: 12 passed in 12.41s
NEGATIVE make eval unknown: exit=2 detected=UNKNOWN_EVIDENCE_ID
NEGATIVE make eval value: exit=2 detected=FABRICATED_VALUE
NEGATIVE make eval cause: exit=2 detected=TOP1_MISS
Offline tests: 96 passed, 21 deselected in 13.79s
Replay API/isolation: 3 passed in 12.09s
  SCN-001/SCN-002 completed Top-1=1 precision=1, scorecard persisted, no truth fields
  API has no truth credentials or fixture files
make lint: All checks passed!; 132 files formatted;
  Success: no issues found in 65 source files; ESLint / tsc exit 0
Synthetic make eval: all three Top-1/Top-3/precision/coverage 100%, unsupported 0%
```

M5 repeated live recording (real command output; `make record-golden`, exit 0):

```text
LIVE SCN-001 repeat=1 Top-1=1.0 precision=1.0000 coverage=1.0000 unsupported=0.0000 latency=2633.48ms passed=True failures=()
LIVE SCN-001 repeat=2 Top-1=1.0 precision=1.0000 coverage=1.0000 unsupported=0.0000 latency=2074.76ms passed=True failures=()
LIVE SCN-001 repeat=3 Top-1=1.0 precision=1.0000 coverage=1.0000 unsupported=0.0000 latency=2184.33ms passed=True failures=()
LIVE SCN-002 repeat=1 Top-1=1.0 precision=1.0000 coverage=1.0000 unsupported=0.0000 latency=2623.26ms passed=True failures=()
LIVE SCN-002 repeat=2 Top-1=1.0 precision=1.0000 coverage=1.0000 unsupported=0.0000 latency=877.35ms passed=True failures=()
LIVE SCN-002 repeat=3 Top-1=1.0 precision=1.0000 coverage=1.0000 unsupported=0.0000 latency=800.14ms passed=True failures=()
Both scenarios: runs=3, passed=3, misses=[]
```

All six completed/recovered faults were evaluated through the isolated server-side
scorer; the host read protected truth only through the scorer oracle to write
separate truth files. Root recorded fixture sizes: SCN-001 3426 observable items,
SCN-002 1587; poisoned kill 3427 (one added synthetic untrusted log). Original
hand-authored bundles remain under tests/fixtures/synthetic for isolated unit tests.
Every scorecard includes provider/model/prompt/tool/commit/seed and retrieval params.
Live summaries with individual scores and variance are preserved in
[JSON](docs/verification/m5/live-summary.json) and [Markdown](docs/verification/m5/live-summary.md),
with generated per-run JSON/Markdown cards under eval_reports/.

Final replay/API checks after healthy restart: `4 passed in 29.03s`:
both real-fixture golden API jobs passed, metadata persisted, no truth returned;
recorded replay passed protected window validation; wrong run/scenario failed;
API has no scorer credential or truth files; evaluation.top1.count exported.
Pure/adversarial suite including numeric strings/exponents: `16 passed in 49.13s`.
Full gate before final critical-root hardening:
```text
make test: 122 passed in 380.06s (0:06:20); 22 live Docker tests, none skipped
Vitest: Test Files 1 passed (1); Tests 1 passed (1); Duration 1.56s
make lint final: All checks passed!; 136 files formatted;
  Success: no issues found in 65 source files; ESLint / tsc exit 0
make eval (recorded real fixtures):
  scn-001 Top-1=100% Top-3=100% precision=100.00% coverage=100.00%
    unsupported=0.00% latency=5108.18ms passed=True failures=none
  scn-002 Top-1=100% Top-3=100% precision=100.00% coverage=100.00%
    unsupported=0.00% latency=2162.35ms passed=True failures=none
  poisoned-log Top-1=100% Top-3=100% precision=100.00% coverage=100.00%
    unsupported=0.00% latency=3447.22ms passed=True failures=none
Gitleaks source including real fixtures: scanned ~19848910 bytes; no leaks found
API and scorer image inspection: both linux/arm64
Actionlint 1.7.7: exit 0
```

Final infrastructure refinement: named scorer output volume is initialized for
UID 10001, avoiding root-owned bind output directories in fresh Linux CI. Separate
Dockerfile targets share a runtime stage so scorer does not require an existing
local API image. Docker build/restart/replay checks passed for this refinement; scorer uid=10001,
volume uid=10001, writable=True. Final replay/isolation gate after this refinement: `4 passed in 20.59s`.
The final scorer additionally requires causal conjunction support for the critical
root (timeouts alone cannot support primary outage); host metadata marks dirty
checkouts explicitly. New pure-root negative test passed after JSON tuple fix.
Scorer volume contains 3 JSON + 3 Markdown cards after real API replay.


Final M5 gate after critical-root and Docker-volume refinements (real output):
```text
make test: 123 passed in 345.38s (0:05:45)
  22 live Docker tests, none skipped
Vitest: Test Files 1 passed (1); Tests 1 passed (1); Duration 1.68s
make lint: All checks passed!; 136 files already formatted
  Success: no issues found in 65 source files; ESLint / tsc exit 0
make eval (final critical-root gate, recorded real fixtures):
  scn-001 Top-1=100% Top-3=100% precision=100.00% coverage=100.00%
    unsupported=0.00% latency=4272.77ms passed=True failures=none
  scn-002 Top-1=100% Top-3=100% precision=100.00% coverage=100.00%
    unsupported=0.00% latency=2234.37ms passed=True failures=none
  poisoned-log Top-1=100% Top-3=100% precision=100.00% coverage=100.00%
    unsupported=0.00% latency=5211.33ms passed=True failures=none
Gitleaks v8.24.2: scanned ~19856818 bytes (19.86 MB) in 3.27s; no leaks found
.env checksum unchanged from start of M3
```

All six persisted live reports were re-scored through the final critical-root gate;
each retained Top-1=1, evidence precision=1 and critical unsupported count=0.
Experiment metadata identifies the measured uncommitted code as the M4b commit
plus `+working-tree`; no result is relabeled as if it ran on a later commit.
M6 has not started. GitHub-hosted CI and fresh-clone verification remain explicitly
unverified below.

### M6 Dashboard

Baseline before implementation (existing .env preserved):
```text
make test: 123 passed in 303.39s (0:05:03); 22 live Docker tests, none skipped
Vitest: Test Files 1 passed (1); Tests 1 passed (1); Duration 667ms
```
- [x] Incidents list + create — explicit scope, time validation and status badges; frontend tests passed
- [x] Detail tabs: Timeline, Evidence, Hypotheses, Report, Agent Trace — all visited with real data; live SSE then terminal completion, scoped outside-ID drawer verified
- [x] Evaluation page — scorecards and terminal-only scorer truth; unit disclosure gates passed
- [x] Vitest tests + Dockerfile/Compose service — 25 frontend tests; native arm64 web healthy; loopback host/proxy verified
- [x] **GATE:** full demo path without manual DB edits — real kill, UI creation/investigation/evidence/report/export/recorded evaluation passed; final suite green

Interim M6 verification:
```text
Frontend: 25 passed (4 files); TypeScript and ESLint exit 0
Scorer disclosure guards: 5 passed in 2.20s
Live replay/disclosure/API isolation: 4 passed in 26.95s
make lint: All checks passed!; 137 files already formatted;
  Success: no issues found in 65 source files; ESLint / tsc exit 0
make build-web: 34 modules transformed; built in 474ms
make up: Preserving existing .env; API/gateway/web/Collector healthy
make seed-traffic: Container aipi-traffic-1 Healthy
```

Browser validation caught and repaired a native-date submission issue before
the real chaos gate; test incident 4b8442fe-19ff-4461-a3a8-f40a13868ed0 is not a
gate result. The corrected UI rejected both reversed and >6-hour windows.
No manual DB edits or .env regeneration were performed.

Live UI gate (2026-10-14, Apple Silicon, after fresh make up + seed-traffic):
```text
make chaos-kill: exit 0
run_id=fffb2290-6bb3-4a6c-a3cf-86bde8019dd4
passed=true; recovery_status=verified
runtime die 2026-10-14T16:03:57.562460+00:00 exit_code=137
runtime start 2026-10-14T16:04:05.956130+00:00
gateway_5xx_requests=68; gateway_failed_spans=246; gateway_error_logs=79
UI incident=57bccb03-2f6b-4997-b7dc-f2e8a381d716
stored window=2026-10-14T16:03:25Z–2026-10-14T16:04:14Z
service scope=checkout-api + gateway
investigation=6bf83863-05aa-4f74-9721-f2d41b98cbf3 completed
root=Checkout service process terminated; confidence=0.96
bundle=50; cited=333; outside_bundle_count=313
SSE: Live then Complete; event_count=24; last_seq=24; node_completed=6; tool_completed=8
latency_ms=1719.520501000261; input/output_tokens=0/0; estimated_cost=0.0
UI outside lookup ev_193db7bbd0a520e9: gateway requests_total=7, HTTP status=503
UI evidence filters: type=log + service=gateway -> filteredLogRows=10
Markdown export matches stored report: True
export_sha256=ae43f82f235302e2abe86e2febed22eb2f713a50cadfca123c7be431100187d2
UI EVALUATION 177f9e21-e2fc-4d86-ae37-e159011765be completed, passed=true
Top-1=1; Top-3=1; precision=1; coverage=1; unsupported_rate=0
contradiction_handling=1; critical_unsupported_claims=0
useful_evidence_per_tool_call=41.625; citation_pairs=supported_pairs=424
Job remains score-only: True
make lint: All checks passed!; 139 files already formatted;
  Success: no issues found in 65 source files; ESLint / tsc exit 0
make build-web: 35 modules transformed; built in 454ms
API / scorer / web images: linux/arm64; Compose config --quiet: exit 0
```

The incident was created and investigated in the browser; its recorded replay was
submitted in the Evaluation page using the actual recovered host run ID. Ground
truth appeared only after scoring through the separate scorer-backed disclosure.
The report preserves FOR/AGAINST evidence; the dependency false lead ranks lower
at 20%, contradicted by the die event. Recommendations display Requires human
approval and Not executed. Escape closes the drawer and restores focus to its
citation. No mutating investigation/remediation control exists.

Real screenshots (workspace paths):
- docs/verification/m6/01-incidents.jpg (desktop incidents)
- docs/verification/m6/02-timeline.jpg (real scoped window)
- docs/verification/m6/03-agent-trace-full.jpg (all execution events and usage)
- docs/verification/m6/04-hypotheses.jpg (ranked FOR/AGAINST)
- docs/verification/m6/05-outside-bundle.jpg (resolved scoped payload + redactions)
- docs/verification/m6/06-evidence-logs.jpg (ten filtered gateway logs)
- docs/verification/m6/07-report.jpg (Facts / Hypotheses / Recommendations)
- docs/verification/m6/08-evaluation.jpg (passed recorded scorecard + post-score truth)

The actual downloaded Markdown, scorecard JSON, incident/usage metadata and all
outside-ID references are preserved in docs/verification/m6/. Final full test gate:
```text
make test: 128 passed in 392.29s (0:06:32); 22 live Docker tests, none skipped
Vitest: Test Files 4 passed (4); Tests 25 passed (25); Duration 1.77s
.env checksum unchanged from start of M6
```
Follow-up trace accessibility/readability verification after the full suite:
```text
Frontend: Test Files 4 passed (4); Tests 26 passed (26); Duration 2.67s
TypeScript / ESLint: exit 0
Production build: 35 modules transformed; built in 442ms
Docker web rebuild --no-deps --wait: Container aipi-web-1 Healthy
Native UI trace labels include runtime_events_query, logs_query, trace_lookup,
  metric_query, db_replication_status and runbook_search
Gitleaks v8.24.2: scanned ~19995886 bytes (20 MB) in 3.82s; no leaks found
```

Trace event summaries now have accessible names and show tool identities directly.
Per-event duration renders only when the event payload provides it; the existing
live events do not include that field, so no per-event durations are invented.
Actual overall latency, tokens and cost are shown from investigation metadata.
The full backend suite was not repeated for this frontend-only presentation change;
the complete updated frontend suite, build, healthy container and real trace UI
were verified. The M6 source scan included that refinement; M7 had not started at that checkpoint.

### M7 Polish
- [x] README — actual topology, generated private .env setup, isolated-port variant, warm demo, safety, qualified M5 results and limitations
- [x] docs/ — current implementation references completed; threat table and ADR-001…023; original numbered specs explicitly labeled historical requirements
- [x] `make demo` and CI — fresh clone real incident/investigation/recorded score + 3 golden gates passed; local actionlint and full-history scanner passed; GitHub CI not run
- [x] **GATE:** README clone/setup/demo passed with new credentials/project/ports; current source matched tested clone (173 non-document files)

- [x] Test hygiene — exact source IDs + unique markers in finally; controlled failure/sentinel proof; legacy future-row before/after recorded
- [x] Replay timeout — 90 seconds with job ID/status/elapsed diagnostics
- [x] Push readiness — ignored secrets/dependencies/caches, MIT, two 7.524 MB fixtures retained with rationale; maximum historical blob 7,524,096 bytes; no 100 MB blobs
- [x] Two consecutive final `make test` runs and final lint — 140 Python + 26 UI each; 355.71s / 383.50s Python; 24 live Docker tests each, none skipped

Initial README fresh-clone output (2026-10-17 IST):

```text
clone: /tmp/aipi-m7-clone.59TjeJ/aipi (HEAD 9e9a840 + non-ignored candidate overlay)
Python 3.12.0; uv 0.11.21; node v25.9.0
make setup-env: Created private .env with generated lab credentials
make setup: frozen workspace installed; npm added 254 packages; 0 vulnerabilities
make demo: project aipi-fresh-check, ports 15432/15433/18000/18080/15173/14318/23133
all Compose services healthy; all images inspected linux/arm64
run d09b059c-1278-436a-abf3-0d759cb05a6d passed=true recovery_status=verified
die 2026-10-16T20:53:58.008488Z exit_code=137 -> start 20:54:06.411873Z
67 foreground gateway 5xx; 266 failed spans; 86 error logs; 503 counter +86
Incident ID: be582099-c886-409f-a4fc-bb62ad7dae80
UI URL: http://127.0.0.1:15173/#/incidents/be582099-c886-409f-a4fc-bb62ad7dae80
investigation d5785365-f04f-4db7-b14f-8d047dd05d17 completed, persisted latency 7714.169086 ms
evaluation de7253e5-2900-4d63-948a-ddc19c43304d passed=true
Top-1/Top-3/precision/coverage/contradiction=1; unsupported=0; 446/446 pairs supported
scn-001 Top-1=100% Top-3=100% precision=100.00% unsupported=0.00% latency=8486.23ms passed=True
scn-002 Top-1=100% Top-3=100% precision=100.00% unsupported=0.00% latency=1428.13ms passed=True
poisoned-log Top-1=100% Top-3=100% precision=100.00% unsupported=0.00% latency=3998.41ms passed=True
```

This is a separate smoke measurement, not a replacement for section 6's n=3
experiment. No existing .env or volume was copied into the clone. Main volumes
were retained when stopping its project; fresh clone resources use another project.
The final candidate additionally validates every demo API response with the
existing Pydantic contracts and prints an incident URL without an unused tab query.
Its second demo also passed: incident f9d05374-ad06-4b08-8958-d7fb90762474,
investigation 31dc11d3-a4a8-4858-a9bf-babdae8a7752, evaluation
5871e18a-dddb-4000-9b00-de758554f9a9; 402/402 supported citation pairs, zero
unsupported claims, persisted investigation latency 4987.098961 ms. The final
golden replay latencies were 4363.94 / 2858.13 / 4131.30 ms, all passed.

First consecutive isolated final run: `133 passed in 395.35s (0:06:35)`;
Vitest `4 passed (4)` files, `26 passed (26)`, duration 1.07s. All 23 Docker
integration tests passed, none skipped. Second consecutive run failed (F050); this does not count as a two-pass gate.

```text
Targeted test hygiene + golden replay: 5 passed, 6 deselected in 17.35s
Controlled failure cleanup: 4 owned rows removed; unrelated sentinel retained
make lint: All checks passed!; 148 files already formatted;
  Success: no issues found in 66 source files; ESLint + tsc exit 0
offline mock suite: 110 passed, 23 deselected in 210.35s
actionlint 1.7.7: exit 0 (GitHub CI has NOT run)
gitleaks 8.24.2 full history --log-opts=--all: 12 commits, 20.20 MB, no leaks found
candidate non-ignored source scan: 20.05 MB, no leaks found
largest tracked/historical blob: 7,524,096 bytes (poisoned-log.json); 0 >=100 MB
tracked environment files: .env.example only; original .env checksum: OK
```

Final M7 gate (current source; prior candidate failures above are retained honestly):

```text
clone /tmp/aipi-m7-release-clone.OfjsPE/aipi
project aipi-fresh-check-1792187061; new .env generated; original .env checksum OK
make setup-env / make setup / make demo: exit 0
live demo incident 9eab8cfe-f38f-4b97-aa64-c74712bd0757
investigation 0d1e3e90-4eb5-4575-841c-d6f7a8196aef, persisted latency 4842.606586 ms
evaluation b8aa2f3f-b18d-4869-8909-2fba6689a92b: passed; 342/342 supported pairs
Top-1/Top-3/precision/coverage/contradiction=1; unsupported=0; failures=[]
golden SCN-001 / SCN-002 / poison: all passed (5816.52 / 1747.64 / 5317.31 ms)
focused live evidence: 2 passed in 105.37s; requests 1.21s / 0.31s; IDs/rules stable
make test #1: 140 passed in 355.71s; Vitest 4 files / 26 tests passed in 2.68s
make test #2: 140 passed in 383.50s; Vitest 4 files / 26 tests passed in 1.68s
  24 Docker tests each, none skipped; consecutive, no source/cache changes between
make lint: All checks passed!; 151 files already formatted;
  Success: no issues found in 66 source files; ESLint and tsc exit 0
actionlint 1.7.7: exit 0; GitHub CI has NOT run
full-history gitleaks --log-opts=--all: 12 pre-phase commits / 20.20 MB / no leaks
final non-ignored candidate scan: 20.24 MB / no leaks
native project api/scorer/web images: linux/arm64
both PG containers init=true; wal_keep_size=512MB; crash-recovery events=0 / 0
current code/data/config versus tested clone: 173 files, differences=[]
current documentation local links: PASS; git diff --check: exit 0
```

Exact logs are under docs/verification/m7. These are local mock software gates;
section 6's historical n=3-per-scenario experiment is unchanged. F052 is outside
this isolated gate: the original standby requests an evicted WAL segment. No
original volume was reset/removed and no .env was regenerated. Its separate plan
is in docs/verification/m7/replica-recovery-plan.md and requires new permission
before a replica-only reseed. This does not claim the old lab is healthy.

---

## 3. FAILURE LOG (newest first)

### F053 — Ingest throughput and second-run live timeouts
- **Status:** RESOLVED — final 140 Python + 26 UI suites passed twice consecutively
- **Command:** second final-clone `make test`
- **Error:** SCN-001 `/evidence` HTTP read timeout at 20s; SCN-002 recovery failed; Collector logged OTLP metrics/traces HTTP timeouts and retries. Interrupted already-failed run: 2 failed, 22 passed in 370.43s. No new PostgreSQL orphan-crash events in the diagnostic interval.
- **Fix:** bounded true bulk INSERTs (500 rows), preserve shape/order/idempotency and transaction atomicity; nominal default background workload 1 cycle/s; foreground fault probes and all evidence/rule assertions unchanged. The live evidence HTTP budget matches the UI (60s), printing actual elapsed time even on failure; SQL statement limits unchanged. Recovery errors now retain safe ChaosError details.
- **Verification:** 14 targeted storage/chaos unit tests passed, including real SQL batching/first-value/rollback tests. Final reruns use fail-fast diagnostics without reducing passing-suite coverage. The focused post-batching regression passed both real scenarios in 105.37s: evidence HTTP 1.21s / 0.31s, full-scope rules invariant, 50 IDs identical on repeat. Host memory diagnostics measured 8 GiB RAM and ~7.5 GiB swap use; one-time clean VM page-cache release reduced Cached from ~4.3 GiB to ~0.7 GiB without deleting files or changing persistent settings. Host recovery client budget is 15s, SQL limits unchanged.
- **Files:** TelemetryStore, default traffic configuration/example, recovery diagnostics, bulk SQL tests, ADR-023.


### F052 — Retained replica requires an authorized reseed
- **Status:** OPEN — existing-volume constraint; no reset performed
- **Command:** restored main `make test`; read-only LSN/receiver diagnostics
- **Error:** `requested WAL segment 0000000100000004000000F5 has already been removed`; receiver empty, replay backlog 89,969,640 bytes, replay age ~1942s. Tools could not observe a WAL receiver and new orders could not become visible within 30 seconds.
- **Cause:** retained standby missed WAL during earlier interruptions; restarting/resuming cannot recover a removed segment. Both PG containers now have init=true and the live orphan test passed (1 passed in 4.52s), with no new orphan crashes observed.
- **Fix prepared:** primary now retains 512 MB WAL for bounded interruptions; existing stale replica needs a new base backup. Do not reset/reseed its retained volume without explicit authorization. Preserve the main project stopped and perform final software gates in a new isolated clone/project.
- **Files:** Compose retention, infra contract, DEPLOYMENT / ADR-022. No existing .env or volume reset.


### F051 — PostgreSQL PID-1 adoption causes spurious crash recovery
- **Status:** RESOLVED — init enabled; both final suites had zero crash-recovery events
- **Command:** full suite after F050; targeted Docker logs; disposable tmpfs reproduction
- **Error:** replica `server process ... terminated by signal 13: Broken pipe`; primary previously `server process ... exited with exit code 2`. PostgreSQL was PID 1; OOMKilled=false and only ~20 database connections.
- **Cause / fix:** a failing orphan health client is adopted by PostgreSQL PID 1 and treated as a crashed database child. Add Docker init:true to both PG containers and 60s graceful shutdown; no data reset. A separate tmpfs container reproduced orphan exit 2 causing crash recovery. Strengthen regression to keep one SQL backend connection alive across the orphan exit (postmaster start time is insufficient).
- **Files:** Compose, infra contracts, live session survival test, ADR-022 / DEPLOYMENT.
- **Reproduction:** two network-none/tmpfs containers, no persistent volume: init=false → new_crash_recoveries=1; init=true → 0. PostgreSQL postmaster start time was identical in both, confirming why the regression must hold a real backend session. Current retry interrupted after already-failed cases (`2 failed, 21 passed in 282.84s`); the restored main attempt exposed F052; final gates passed in the isolated project.


### F050 — M7 second isolated run: connection handshake and sparse lag symptoms
- **Status:** RESOLVED — both focused cases and final repeated full suites passed
- **Command:** second consecutive `make test` in aipi-fresh-check
- **Error:** SCN-001 `Lab database unavailable`; SCN-002 `ErrorSpikeRule` absent. Interrupted after recovered faults to inspect failures: `2 failed, 22 passed in 236.23s`.
- **Cause / fix:** no PostgreSQL crash reported in that interval. Add exception type/SQLSTATE without driver text and a bounded 10-second host handshake (SQL remains 5s). SCN-002 formerly probed only one stale order, so its error/latency spike depended on background scheduling. Probe all ten fresh orders and require actual 404s, then retain ten seconds of primary health samples. No correlator threshold or scope change.
- **Files:** Lab connector, SCN-002 runner, host connection redaction and foreground symptom tests; ADR-021 / CHAOS docs.
- **Verification:** 17 targeted unit tests passed after correcting the new test stub's required Order fields; both real evidence regressions then passed in 103.65s. SCN-001 rules ProcessExitRule/ErrorSpikeRule; SCN-002 ErrorSpikeRule/ReplicaLagRule/DownstreamTimeoutRule/PrimaryHealthRule. All 50 IDs identical on repeat; recovery verified for both. That candidate had 137 Python cases; the final 140-case gate is recorded above.


### F049 — M7 restart before the new web image was built
- **Status:** RESOLVED (make up rebuilt images; targeted tests passed)
- **Command:** `docker compose ... up -d --no-build --wait`
- **Error:** `No such image: aipi-web:local` after naming the image explicitly for project isolation.
- **Cause / fix:** old image used the Compose-generated tag; build the candidate images with `make up` before restarting or verifying tests.
- **Files:** `infra/docker/compose.yml`
- **Verification:** early targeted retry ran during the rebuild (4 HTTP failures, 1 cleanup proof passed); after health, the same target passed all 5 tests in 17.35s.


### F048 — M7 baseline database outage / audit invocation
- **Status:** RESOLVED for source defect via F051; retained missing-WAL state remains separately OPEN in F052
- **Command:** `make test`; `uv run python scripts/cleanup_legacy_synthetic.py`
- **Error:** `13 failed, 115 passed in 435.56s`; PostgreSQL `server process exited with exit code 2`, then `database system is not yet accepting connections`. Direct script invocation could not import `chaos`.
- **Cause:** PostgreSQL server interruption during baseline; underlying exit cause unconfirmed. Automatic WAL recovery completed without a reset. Audit initially used a full-table count; now constrained by indexed service/time predicates.
- **Tried / fix:** paused producers/reconnecting applications during recovery; resumed existing volumes. Run host scripts with `python -m scripts...`. No audit deletion succeeded during outage. Exact one-time cleanup then removed 3523 logs, 1392 events, 116 metrics and 28 spans; after counts all zero.
- **Files:** synthetic test teardown and `scripts/cleanup_legacy_synthetic.py`; no credential or volume reset.
- **Follow-up:** full retry interrupted after 6 failed / 11 passed in 212.13s when retained PostgreSQL again entered recovery (backend exit code 2); no second success claimed. Offline mock suite independently passed 110 tests (23 Docker tests deselected) in 210.35s. Main project stopped with volumes retained to run the isolated fresh-clone gate alone; host Data volume had 7.7–7.8 GiB free. The later controlled diagnosis is in F051 (PID-1 orphan adoption).

Add an entry whenever a command, test, or build fails and is not fixed immediately. Keep it until resolved, then mark `RESOLVED` (don't delete).

```
### F-047 — RESOLVED — M6 native date values versus submitted scope
- Action: browser fill of datetime-local fields followed by Create incident during validation checks.
- Real output: locator.fill deadline for Window start (21:00:00 normalized to 21:00); test incident 4b8442fe-19ff-4461-a3a8-f40a13868ed0 stored defaults 15:25:48Z–15:40:48Z despite visible date changes.
- Cause: native browser input updates did not reliably reach React onChange state through the automation path.
- Fix: read and validate native date values via FormData at submit and keep native date inputs uncontrolled; add a native-input regression test and repeat the UI checks. This test incident is not a chaos/evaluation gate result.
- Files: IncidentsPage.tsx, components.test.tsx.

### F-046 — RESOLVED — M6 report section accessible names
- Command: cd apps/web && npm test.
- Real output: 1 failed, 22 passed; unable to find region named Facts (actual name: 01 Facts).
- Fix: mark decorative section numbers aria-hidden, leaving meaningful region names Facts/Hypotheses/Recommendations.
- Files: components.tsx.

### F-045 — RESOLVED — M6 Python generic syntax lint
- Command: ruff check packages/evaluation apps/api --fix.
- Real output: Found 2 errors (1 fixed, 1 remaining); UP047 generic function forward should use type parameters.
- Fix: use Python 3.12 type-parameter syntax for the typed scorer proxy; checks follow.
- Files: evaluation_routes.py, server.py.

### F-044 — RESOLVED — M6 initial TypeScript check
- Command: cd apps/web && npm run typecheck.
- Real output: TS2322 string is not assignable to UUID template type; TS2580 Cannot find name process in vite.config.ts.
- Fix: annotate stream request ID as string and use Vite loadEnv for the proxy setting; npm run typecheck and npm run lint both exit 0.
- Files: stream.ts, vite.config.ts.

### F-043 — RESOLVED — Added pure root-cause negative test serialization
- Command: evaluation/golden targeted pytest after critical-root support hardening.
- Real output: 1 failed, 24 passed in 53.57s; tuple has no attribute remove.
- Cause: Pydantic Python-mode dump preserves tuples; the test attempted mutable re-ranking.
- Fix: JSON-mode dump supplies arrays for the deliberately tampered test report. Runtime implementation unchanged; make eval passed all recorded goldens with the new root check. Final full gate: 123 passed in 345.38s plus 1 web test.
- Files: test_evaluation.py.

### F-042 — RESOLVED — M5 replay check raced container restart
- Command: final live evaluation API test launched while Compose up was still running.
- Real output: 3 failed, 1 passed in 12.57s; server disconnected and transient 503 Scorer unavailable.
- Cause: dependent test started before the yielded Compose operation completed.
- Fix: await completed healthy restart, inspect services and rerun the replay/API gate sequentially.
- Files: PROGRESS.md; no implementation change required.

### F-041 — RESOLVED — Evaluation histogram metric name assertion
- Inspection: live evaluation test metric assertion versus otlp.py (corrected before the metric assertion executed).
- Cause/fix: histogram normalizer uses .sum/.count, not underscores; changed the exported metric assertion from evaluation.top1_count to evaluation.top1.count, matching the actual ingestion contract. Final gate rerun below.
- Files: test_evaluation_api.py.

### F-040 — RESOLVED — M5 topology test expected only M4 services
- Command: offline pytest.
- Real output: 1 failed, 93 passed, 18 deselected in 5.43s; extra service scorer.
- Fix: update topology contract and assert the truth URL exists only in scorer environment.
- Files: test_infra.py.

### F-039 — RESOLVED — M5 scorer Compose insertion
- Command: `docker compose ... build api`.
- Real output: yaml construct errors, cycle detected at x-demo.depends_on.
- Cause: text insertion matched the demo dependency instead of the services block.
- Fix: anchored scorer insertion under services; preserved x-demo's collector dependency. Validate Compose before rebuilding.
- Files: infra/docker/compose.yml.

### F-038 — RESOLVED — M5 initial formatting, typing and session inspection
- Commands: Ruff/mypy initial evaluation check; write_stdin with stale session 28139.
- Real output: Ruff 58 errors (7 fixed), then seven remaining long literals and final numeric/test literals; new recorded API test needed its json import after Ruff had removed the previously unused import; mypy two JSON/local-variable types, then two raw-capture types; Unknown process id 28139.
- Fix: formatter/import cleanup, explicit JSON list type and distinct Markdown cursor; resume actual sync session 70358 (resolved 90 packages). First synthetic eval: all three fixtures Top-1/Top-3/precision/coverage 100%, unsupported 0%.
- Files: evaluation modules, PROGRESS.md.

### F-037 — RESOLVED — M5 dependency resolution network restriction
- Command: `UV_CACHE_DIR=/tmp/aipi-uv-cache uv run ruff format packages/evaluation` after manifest update.
- Real output: failed to fetch https://pypi.org/simple/pydantic after 3 retries; DNS lookup not known.
- Cause: uv needed to resolve changed dependencies in a network-restricted shell.
- Fix: approved sync resolved 90 packages and installed updated evaluation; use --no-sync during edits.
- Files: packages/evaluation/pyproject.toml, uv.lock, PROGRESS.md.

### F-036 — RESOLVED — Temporary automatic approval-review usage limit
- Command: final Docker Gitleaks scan of /tmp/aipi-m4b-secret-scan.
- Real result: action was not executed because automatic approval review hit its usage limit; this was explicitly a review failure, not an unsafe-action determination.
- Fix: user requested continue; retried the same scan through approval review. It ran successfully: scanned ~1933645 bytes, no leaks found. No approval bypass used.
- Files: PROGRESS.md.

### F-035 — RESOLVED — M4b offline API lifespan dependency
- Command: `uv run pytest -m 'not docker' -q`.
- Real output: `2 failed, 76 passed, 15 deselected in 3.52s`; connection to mocked 127.0.0.1:1 during new interrupted-job startup recovery.
- Fix: existing isolated HTTP tests mock the new recovery port, as they already mock persistence/core reads; live recovery remains real and tested separately.
- Files: test_incident_core.py, test_telemetry.py.

### F-034 — RESOLVED — M4b graph SDK typing
- Command: `uv run mypy --strict packages apps/api`.
- Real output: two overload errors for StateGraph.add_node and graph.invoke (typed Pydantic state versus a dumped dictionary).
- Fix: explicit RunnableLambda typed node/input schema; pass validated state and RunnableConfig. Golden graph tests and strict checks passed after correction.
- Files: workflow.py. Formatting/import issues fixed with Ruff before subsequent checks.

### F-033 — RESOLVED — M3 matching-operation error-rate regression found in M4a gate
- Command: `make test` after FK-test repair.
- Real output: `1 failed, 87 passed, 1 warning in 141.52s`; SCN-002 missing ErrorSpikeRule.
- Diagnosis: scoped SQL showed orders-api postgres.select_order failed-span rate 0 → .3611; GET request rate remained 0 (fallback is HTTP 200), while p95 was 224.73 → 352.76 ms, below the 2× latency threshold. Service-wide mixing diluted errors below .25.
- Fix: compare failed-span rates for matching service/operation, as already required for latency; add offline mixed-operation regression. No lowered threshold or scenario/truth-aware behavior.
- Files: correlators.py, test_correlators.py; rebuild live API before gate re-run.

### F-032 — RESOLVED — M4a foreign-key-aware immutability test
- Command: `make test`.
- Real output: `1 failed, 85 passed, 1 warning in 143.55s`; `psycopg.errors.FeatureNotSupported: cannot truncate a table referenced in a foreign key constraint`; agent_evidence now references evidence.
- Fix: test TRUNCATE CASCADE to reach the immutable trigger while including referenced artifact tables; the trigger rejects the entire transaction. The original foreign-key refusal already prevented mutation.
- Files: tests/integration/test_incidents.py. Final gate output below supersedes this failed run.

### F-031 — RESOLVED — M4a typing and formatting
- Commands: `uv run ruff check packages --fix`, `uv run mypy --strict packages apps/api`.
- Real output: Ruff initially reported 41 errors (6 fixed); after formatting 11 remained. Mypy reported 16 errors across 6 files (JSON union narrowing, aliases, generic types).
- Fix: Python 3.12 type parameters, explicit validated JSON/model types, wrapped long literals. Re-run results are recorded in the M4 session gate below.

### F-030 — Initial M4 inspection paths    Status: RESOLVED
- Phase/step: M4 baseline inspection
- Commands: `cat CODEX_MASTER_PROMPT.md AIPI_CONTEXT.md`; `cat apps/api/src/aipi_api/app.py`; glob/reads using guessed migration/docs paths (0003 under infra/postgres, 05_API_Contract, 10_Security_and_Safety, ARCHITECTURE.md); `.gitleaks.toml` inspection.
- Error (real): `AIPI_CONTEXT.md: No such file or directory`; `app.py: No such file or directory`
- Suspected cause: context lives in docs/ and API factory in main.py.
- Tried / fix: discover with rg; read actual context, API/security specs and main.py; migrations are under infra/docker; use existing numbered architecture docs and default Gitleaks configuration.
- Files touched: PROGRESS.md

### F-029 — Secret scan referenced nonexistent configuration    Status: RESOLVED
- Phase/step: M3 refinement pre-commit scan
- Command: `docker run --rm -v /tmp/aipi-selection-secret-scan:/repo zricethezav/gitleaks:v8.24.2 dir /repo --config /repo/.gitleaks.toml --redact`
- Error (real): `unable to load gitleaks config ... no such file or directory`
- Suspected cause: this repository uses the default scanner configuration.
- Tried / fix: reran the previously verified ghcr.io scanner invocation with defaults; scanned ~586816 bytes (586.82 KB), no leaks found.
- Files touched: PROGRESS.md

### F-028 — Unused diagnostic correlator import    Status: RESOLVED
- Phase/step: M3 refinement lint
- Command: `make lint`
- Error (real): `F401 aipi_tools.correlators.correlate imported but unused`
- Suspected cause: live test switched to checking persisted full-scope signals.
- Tried / fix: remove the unused import.
- Files touched: test_incidents.py, PROGRESS.md

### F-026 — Live correlation and counter-series mismatches    Status: RESOLVED
- Phase/step: M3 refinement first live gate
- Command: `uv run pytest tests/integration/test_incidents.py -v -s --tb=short`
- Error (real): `2 failed, 4 passed in 70.88s`; kill recovered but `Timed out: exported 5xx metric increase`; replica selected-only rules had extra ErrorSpikeRule versus full scope.
- Suspected cause: gateway counter query mixed /orders and /checkout series with identical timestamps; capped error-biased samples distorted correlation.
- Tried / fix: narrow kill verifier to /checkout; freeze full-scope signals and compare before selection against API after selection. Add missing span-latency baseline check and include 30 seconds of steady telemetry in live windows.
- Files touched: signals.py, correlators.py, test_correlators.py, test_incidents.py, PROGRESS.md

### F-027 — Inspection used nonexistent normalization path    Status: RESOLVED
- Phase/step: M3 refinement inspection
- Command: `rg -n 'counter|value|metric' packages/telemetry/src/aipi_telemetry/normalize.py`
- Error (real): `No such file or directory`
- Suspected cause: storage/ingestion modules have different filenames.
- Tried / fix: inspect actual metric labels with an allowlisted read-only query instead.
- Files touched: PROGRESS.md

### F-025 — JSON union numeric typing    Status: RESOLVED
- Phase/step: M3 refinement mypy
- Command: `uv run mypy --strict packages apps/api services/demo-services/src chaos`
- Error (trimmed, real): `Found 3 errors in 2 files`; JSON union incompatible with float/int and inferred payload dict.
- Suspected cause: strict typing needs numeric narrowing and explicit JsonValue annotations.
- Tried / fix: validate numeric sample/count types and annotate summary payload/transitions.
- Files touched: metric_summaries.py, correlators.py, PROGRESS.md

### F-024 — Long live inventory diagnostic line    Status: RESOLVED
- Phase/step: M3 selection refinement lint
- Command: `make lint`
- Error (real): `E501 Line too long (154 > 100)` at test_incidents.py:159
- Suspected cause: expanded raw/full-rule diagnostic string.
- Tried / fix: split the diagnostic into adjacent strings; rerun lint.
- Files touched: tests/integration/test_incidents.py, PROGRESS.md

### F-023 — Inspection used nonexistent demo module paths    Status: RESOLVED
- Phase/step: M3 refinement inspection
- Command: `cat services/demo-services/src/aipi_demo/orders.py services/demo-services/src/aipi_demo/gateway.py`
- Error (real): `No such file or directory`
- Suspected cause: demo endpoints share app.py.
- Tried / fix: `rg --files services/demo-services/src`; read app.py instead.
- Files touched: PROGRESS.md

### F-001 — <short title>            Status: OPEN | RESOLVED
- Phase/step:
- Command:
- Error (trimmed, real output):
- Suspected cause:
- Tried:
- Fix / workaround (if resolved):
- Files touched:
```

### F-022 — Decision-definition test import sorting    Status: RESOLVED
- Phase/step: M3 prioritization final lint
- Command: `make lint`
- Error (real output): `I001 Import block is un-sorted or un-formatted`; `make: *** [lint] Error 1`.
- Fix: Ruff organized the added re import; reran the complete lint gate.
- Files touched: tests/unit/test_evidence_ranking.py

### F-021 — Evidence inventory line formatting    Status: RESOLVED
- Phase/step: M3 prioritization follow-up
- Command: `uv run ruff check . --fix`
- Error (real output): `E501 Line too long (125 > 100)` and `(111 > 100)` in inventory print statements.
- Fix: split the diagnostic print strings before the live gate.
- Files touched: tests/integration/test_incidents.py

### F-020 — Authoritative scope query formatting    Status: RESOLVED
- Phase/step: M3 security review
- Command: `uv run ruff check .`
- Error (real output): `E501 Line too long (113 > 100)` in the new persisted-incident SELECT.
- Fix: split the static SQL string; retrieval reloads authoritative incident bounds before telemetry SELECTs.
- Files touched: packages/tools/src/aipi_tools/retrieval.py

### F-019 — Isolation test asserted overly broad exception    Status: RESOLVED
- Phase/step: M3 integration test lint
- Command: `uv run ruff check . --fix`
- Error (real output): `B017 Do not assert blind exception: Exception`.
- Fix: assert SQLAlchemy ProgrammingError with permission-denied message, proving the intended security boundary.
- Files touched: tests/integration/test_incidents.py

### F-018 — Existing ingest test used obsolete database identities    Status: RESOLVED
- Phase/step: M3 offline suite
- Command: `uv run pytest -m 'not docker' --tb=short`
- Error (real output): `1 failed, 45 passed, 8 deselected`; `Incident persistence requires the restricted API writer`.
- Cause: replacing the old SQLite dummy URL also changed the writer dummy to investigator_ro.
- Fix: use the correct investigator_ro and telemetry_writer identities at an unreachable test port; no live credentials or .env changes.
- Files touched: tests/unit/test_telemetry.py

### F-017 — Workspace rebuild needed sandbox network    Status: RESOLVED
- Phase/step: M3 local package dependencies
- Command: `uv run ruff format ...`; `uv run mypy ...` after changing local dependencies
- Error (real output): `Failed to build aipi-api`; `Failed to fetch https://pypi.org/simple/hatchling/`; `failed to lookup address information`.
- Fix: approved `uv sync --all-packages --frozen` rebuilt aipi-api and aipi-tools; subsequent Ruff and strict mypy passed. Existing .env preserved.
- Files touched: package manifests, uv.lock

### F-016 — Audit test-file lookup    Status: RESOLVED
- Phase/step: M2 infrastructure review
- Command: `cat tests/unit/test_structure.py`
- Error (real output): `No such file or directory`.
- Fix: inspected the actual tests/unit/test_infra.py contract tests; no implementation impact.
- Files touched: none

### F-015 — Recovery preceded Docker health status    Status: RESOLVED
- Phase/step: M2 sequential integration gate
- Command: `make test`
- Error (real output): `1 failed, 32 passed, 1 warning in 18.50s`; second scenario refused injection: `Precondition failed: checkout-api not healthy`.
- Cause: HTTP readiness recovered before Docker completed its next healthcheck after start.
- Fix: SCN-001 recovery now also waits for Docker checkout/gateway health, making sequential scenarios safe. Limit 503 baselines to fresh samples to handle process counter resets.
- Files touched: chaos/scenarios/scn_001_service_kill.py, signals.py

### F-014 — Pytest module-name collision    Status: RESOLVED
- Phase/step: M2 full gate
- Command: `make test`
- Error (real output): `import file mismatch: imported module 'test_chaos' ... tests/integration/test_chaos.py ... not the same ... tests/unit/test_chaos.py`.
- Fix: renamed unit file to test_chaos_contracts.py; independent test basenames avoid pytest import collision.
- Files touched: tests/unit/test_chaos_contracts.py

### F-013 — Live kill probe timed out    Status: RESOLVED
- Phase/step: M2 first live SCN-001
- Command: `make seed-traffic && make chaos-kill`
- Error (real output): `"passed": false, "recovery_status": "verified", "error": "ReadTimeout"`; `make: *** [chaos-kill] Error 1`.
- Cause: host request timeout (3s) was shorter than gateway upstream timeout (5s).
- Fix: host timeout 8s and bounded 8s observation; tolerate transport errors but require actual HTTP 5xx. Recovery succeeded on the failed run.
- Files touched: chaos/scenarios/lab.py, scn_001_service_kill.py

### F-012 — Initial chaos static checks    Status: RESOLVED
- Phase/step: M2 implementation
- Command: Ruff and strict mypy on chaos modules
- Error (real output): `Found 10 errors (1 fixed, 9 remaining)`; `runtime_events ... list[dict[str, Any]] ... expected JsonValue`.
- Fix: split long strings, use Python 3.12 type parameters, validate observation JSON.
- Files touched: chaos/scenarios/*, migration 0002

### F-011 — Audit repair formatting    Status: RESOLVED
- Phase/step: M0+M1 follow-up audit
- Command: `uv run ruff check . --fix`
- Error (trimmed, real output): `Found 3 errors` (E501 in gateway logging and watcher attributes); `B023 Function definition does not bind loop variable` in the new integration polling test.
- Suspected cause: new lines exceeded the formatter limit.
- Tried: `uv run ruff format .`; bind test loop variables in lambda defaults.
- Fix / workaround: subsequent `make lint` passed Ruff checks.
- Files touched: services/demo-services/src/aipi_demo/*


### F-010 — Older Git lacks branch --show-current    Status: RESOLVED
- Phase/step: M0+M1 repository inspection
- Command: `git branch --show-current`
- Error (trimmed, real output): `error: unknown option show-current`.
- Suspected cause: older machine Git version.
- Tried / fix: use portable `git symbolic-ref --short HEAD` instead.
- Files touched: none

### F-009 — Secret scanner flagged synthetic redaction sample    Status: RESOLVED
- Phase/step: M0+M1 candidate-file secret scan
- Command: `docker run --rm -v /tmp/aipi-secret-scan:/repo:ro ghcr.io/gitleaks/gitleaks:v8.24.2 dir /repo --redact=100 --no-banner --verbose`
- Error (trimmed, real output): `leaks found: 1`; `RuleID: aws-access-token`; `File: /repo/tests/unit/test_telemetry.py`.
- Suspected cause: deliberately synthetic AWS-format adversarial input.
- Tried: construct the benign test string at runtime, preserving the redaction assertion without committing a credential-shaped literal.
- Fix / workaround: repeated source scan: `no leaks found`; no scanner exclusion or broad allowlist added.
- Files touched: tests/unit/test_telemetry.py

### F-008 — Hardening test expectation and event typing    Status: RESOLVED
- Phase/step: M0+M1 final parser review
- Command: `make lint`; `uv run pytest -m 'not docker'`
- Error (trimmed, real output): `Argument 1 to int has incompatible type ... JsonValue`; `assert len(markers) == 2; AssertionError: assert 1 == 2`.
- Suspected cause: mypy cannot narrow repeated dictionary lookups; markers intentionally aggregate multiple matches by field/rule.
- Tried: narrow a local event timestamp variable; assert the documented marker contract.
- Fix / workaround: use a typed local; test one marker for two replacements in the same field.
- Files touched: packages/telemetry/src/aipi_telemetry/otlp.py, tests/unit/test_telemetry.py

### F-007 — Integration tests overlapped stack rebuild    Status: RESOLVED
- Phase/step: M0+M1 live integration
- Command: `make test`
- Error (trimmed, real output): `3 failed, 13 passed`; `Checkout dependency unavailable`; `connection to server at 127.0.0.1, port 5432 failed: Connection refused`.
- Suspected cause: tests were started while Compose recreated the database and demo containers.
- Tried: wait for completed make up before rerunning; prevent driver connection locals in future failure output.
- Fix / workaround: sequential `make test`: `16 passed` Python and `1 passed` frontend; all generated lab passwords rotated in PostgreSQL and ignored .env, including replica connection configuration; no replacement values emitted.
- Files touched: tests/integration/test_lab.py, ignored .env

### F-006 — Web dev server ownership    Status: RESOLVED
- Phase/step: M0+M1 first Compose gate
- Command: `make up`; `docker compose --env-file .env -f infra/docker/compose.yml logs --tail=30 web`
- Error (trimmed, real output): `container aipi-web-1 exited (1)`; `EACCES: permission denied, open '/app/node_modules/.vite-temp/vite.config.ts.timestamp-...mjs'`
- Suspected cause: non-root Node process cannot write Vite config cache owned by root.
- Tried: grant ownership of /app to node after image build.
- Fix / workaround: rebuilt `make up` passed; web and all service health checks passed.
- Files touched: infra/docker/Dockerfile.web

### F-005 — Frontend dependency advisories    Status: RESOLVED
- Phase/step: M0+M1 dependency audit
- Command: `npm audit --json`
- Error (trimmed, real output): `3 vulnerabilities (1 moderate, 2 critical)`; Vitest <4.1.11 and tinypool <2.1.2.
- Suspected cause: old Vitest major selected initially.
- Tried: upgrade to patched Vitest 4.1.11 and current compatible Vite/plugin.
- Fix / workaround: patched dependencies installed with Node 25; `found 0 vulnerabilities`; final Vitest 4.1.11 test passed.
- Files touched: apps/web/package.json, apps/web/package-lock.json

### F-004 — Missing unit directory on initial test write    Status: RESOLVED
- Phase/step: M0+M1 test scaffolding
- Command: `cat > tests/unit/test_telemetry.py`; `uv run pytest -m 'not docker'`
- Error (trimmed, real output): `no such file or directory: tests/unit/test_telemetry.py`; first run had no selected unit tests.
- Suspected cause: unit directory omitted from skeleton.
- Tried: create tests/unit and write tests again.
- Fix / workaround: `13 passed, 3 deselected` on the corrected run.
- Files touched: tests/unit/*

### F-003 — Initial lint and SDK typing    Status: RESOLVED
- Phase/step: M0+M1 static checks
- Command: `uv run ruff check . --fix`; `uv run mypy --strict packages apps/api services/demo-services/src`
- Error (trimmed, real output): `Found 44 errors (9 fixed, 35 remaining)` (line formatting); `Call to untyped function "shutdown" in typed context [no-untyped-call]`
- Suspected cause: initial formatting and missing upstream log-provider annotation.
- Tried: ruff format; narrow SDK-only typing exception.
- Fix / workaround: automatic formatting; targeted ignore for third-party shutdown method.
- Files touched: Python modules, PROGRESS.md

### F-002 — uv sandbox cache and network    Status: RESOLVED
- Phase/step: M0+M1 dependency installation
- Command: `uv sync --all-packages`; `UV_CACHE_DIR=/tmp/aipi-uv-cache uv sync --all-packages`
- Error (trimmed, real output): `failed to open file /Users/akshat/.cache/uv/sdists-v9/.git: Operation not permitted`; `failed to lookup address information: nodename nor servname provided, or not known`
- Suspected cause: restricted cache writes and sandbox DNS.
- Tried: workspace-safe /tmp cache; approved network access.
- Fix / workaround: approved sync succeeded: `Resolved 67 packages`, `Installed 64 packages`.
- Files touched: Makefile, uv.lock

### F-001 — Docker socket sandbox access    Status: RESOLVED
- Phase/step: M0+M1 environment check
- Command: `docker version`
- Error (trimmed, real output): `permission denied while trying to connect to the docker API at unix:///Users/akshat/.docker/run/docker.sock`
- Suspected cause: sandbox socket restriction.
- Tried: `docker info` with approved escalation.
- Fix / workaround: approved Docker daemon access; output `aarch64 29.8.1`.
- Files touched: PROGRESS.md

---

## 4. DECISIONS AND DEVIATIONS

Anything that differs from the master prompt or the docs. Mirror major ones in `docs/DECISIONS.md` as an ADR.

| # | Date | What changed | Why | ADR |
|---|---|---|---|---|
| 1 | 2026-10-13 | Web/Python future-phase placeholders; explicit failures for future Make targets; opt-in traffic profile | Keep the M0+M1 boundary | ADR-011 |
| 2 | 2026-10-13 | Separate migration admin and telemetry writer; deterministic ingest IDs; histogram sum/count storage | Least privilege and retry safety | ADR-012 |
| 3 | 2026-10-13 | Native multiarch images, pinned Collector; host HTTP check for shell-free Collector | Apple Silicon compatibility and actual health verification | ADR-013 |
| 4 | 2026-10-13 | Bounded manual-kill observation and explicit start; restricted replay function grants | Verified Docker behavior and least privilege | ADR-014 |
| 5 | 2026-10-13 | Explicit related-service allowlists; immutable per-scope snapshots; existing restricted writer persists metadata; static public catalog | Correlation across declared dependencies, stable replay despite late data, no credential regeneration or privileged API reads | ADR-015 |
| 6 | 2026-10-13 | Full-scope frozen signals, one summary per metric series, log/trace floors, deterministic severity/time/source selection; raw and candidate counts; v2 snapshots | Prevent selection bias, retain severe observations and expose omitted candidates without hidden labels | ADR-016 |
| 7 | 2026-10-13 | Synthetic-first bundles, isolated scorer truth, six scoped SELECT/BM25 tools, supervisor audits, deterministic mock and exact scoring; optional paid providers deferred | Offline/key-free repeatability and least privilege | ADR-017 |
| 8 | 2026-10-14 | Six-node validated LangGraph, background jobs/SSE, immutable artifacts/provenance and full witness citations; Reporter preserves verified confidence and non-mutating checks | Inspectable execution and scoped evidence resolution beyond the cap | ADR-018 |
| 9 | 2026-10-14 | Separate scorer/credential-free replay child; bounded semantic gate; three live repeats per scenario, real fixtures with separate truth and preserved synthetic corpus | Keep ground truth out of agents/API, audit citation meaning, expose variance/misses honestly | ADR-019 |
| 10 | 2026-10-14 | Same-origin dashboard proxy, resumable SSE and a separate terminal-only scorer disclosure endpoint | Keep API loopback-bound and truth exclusive to post-score evaluation, resolve full-scope citations in UI | ADR-020 |
| 11 | 2026-10-17 | Project/port-isolated fresh-clone demo, exact marked source teardown, replay timeout diagnostics, full-history CI scan and retained large recorded JSON fixtures | Preserve existing lab credentials/volumes; verify documented setup without selection or truth leakage | ADR-021 |
| 12 | 2026-10-17 | PostgreSQL init process and 512 MB WAL retention; original lost-WAL replica preserved for explicit recovery approval | Reproduced orphan-client crashes; retain bounded outage WAL without resetting retained data | ADR-022 |
| 13 | 2026-10-17 | Bounded bulk ingest, order-preserving idempotency/atomicity tests, one-cycle background default and measured bounded HTTP waits | Avoid ingest backlog on the measured 8 GiB host while keeping every scenario/evidence assertion | ADR-023 |

---

## 5. SKIPPED / NOT VERIFIED

List anything not run (e.g. Docker tests skipped because Docker is unavailable, live LLM adapters untested). Be explicit so nothing is assumed working.

- GitHub-hosted CI was not executed; workflow passed local actionlint, YAML contract tests, and corresponding local build/test/Compose gates.
- M5/M6 historical mock/browser gates remain recorded. M7 final source passed the isolated README clone/demo and two consecutive complete suites; original synthetic fixtures remain for unit tests.
- Fresh-clone verification uses HEAD plus the uncommitted candidate overlay so no phase commit precedes its gate; see docs/verification/m7. Original main replica reseeding was NOT performed: F052 requires a new base backup after missing WAL, and the user forbids touching existing volumes. Main remains stopped/preserved. The passing M7 gate uses separate new project volumes.
- Optional paid LLM providers remain unimplemented/untested; no API key used. M5 results measure the deterministic mock on two curated scenarios, three live repeats each; they do not measure general natural-language claim entailment or production incidents.

---

## 6. SUCCESS-TARGET METRICS (M5 measured, 2026-10-14 IST)

| Metric | Target | Actual | Date measured | Notes |
|---|---|---|---|---|
| Root-cause Top-1 accuracy | ≥ 80% | 100% (6/6 live; both recorded goldens + poison passed) | 2026-10-14 | No misses; three distinct faults per scenario |
| Evidence citation precision | ≥ 90% | 100% every live run | 2026-10-14 | Unique claim/evidence pairs validated by bounded semantic predicates, not ID existence alone |
| Unsupported critical claims | 0 in golden set | 0 (live and recorded golden gate) | 2026-10-14 | Unknown ID/value/root-cause negative make gates fail as required |
| Median investigation latency | < 60 s | 2.12955 s across six live runs | 2026-10-14 | Actual persisted investigation latency; offline replay includes credential-free child overhead |
| Scenario reproducibility | 100% scripted | 100% (6/6 injected and recovered) | 2026-10-14 | Serialized host faults; default seed 42; no simultaneous injections |
| Mutating actions without approval | 0 (none exist) | 0 investigation/remediation actions | 2026-10-14 | Registry read-only; recommendations require approval and executed=false |

Additional metrics: Top-3 recall 100%, evidence coverage 100% (5 required kill
families / 6 required lag families), contradiction handling 100%, unsupported
structured-claim rate 0% on every live run. These have population variance 0.
Mock consumes zero tokens, so per-token efficiency is **null**, not an invented
ratio. Tool efficiency counts unique supported observations from the whole
retrieval/verification pipeline per audited tool call, not marginal tool yield.

| Scenario (n=3) | Latency samples (ms) | Mean (ms) | Median (ms) | Stddev (ms) | Population variance (ms²) | Useful evidence/call mean | Efficiency variance |
|---|---|---|---|---|---|---|---|
| SCN-001 | 2633.48, 2074.76, 2184.33 | 2297.53 | 2184.33 | 241.73 | 58434.34 | 45.7500 | 7.072917 |
| SCN-002 | 2623.26, 877.35, 800.14 | 1433.58 | 877.35 | 841.82 | 708662.68 | 14.9630 | 0.068587 |

Misses: **none in six measured live runs**. Replica latency varied substantially;
retain that variance rather than selecting the fastest pass. Results apply to the
local curated mock and implemented correlator/category claim vocabulary. Unsupported
new prose is rejected; these are not accuracy claims for arbitrary production data
or a general semantic-language judge. Full samples, individual metrics/versions,
and any miss arrays are in docs/verification/m5/live-summary.json.

---

## 7. LOG (append one line per work session, newest first)

`2026-10-17 03:43 IST | M7 | Exact synthetic cleanup/failure teardown; bounded safe diagnostics; README + current docs/ADRs; real demo and isolated ports; PID-1 reaping/WAL retention; bulk ingest/default 1 cycle; complete mock CI definition/local gates | 140 Python + 26 UI twice, 24 live each, lint/types/actionlint/full-history scan passed; clone demo 342/342 pairs; original .env unchanged and all original volumes retained; main lost-WAL replica F052 not reseeded | Commit feat(M7); no push; GitHub CI unrun`



`2026-10-14 22:20 IST | M6 | Incident list/form and scoped detail tabs, outside-bundle drawer, Markdown export, resumable SSE, runtime API validation and request-ID errors; separate terminal-only scorer truth disclosure; native date submission fixed from browser feedback | 128 Python + 26 web verified, 22 live tests; real kill -> UI create/investigate/report/export -> recorded evaluation passed, 333 resolved cites / 313 outside; lint/build and arm64 health/secret scan passed; .env unchanged | M7 not started`

`2026-10-14 02:03 IST | M5 | Pure semantic citation/quotation gate and eight metric families; scorer-only truth, credential-free golden replay process, persisted replay APIs/CLI, JSON+Markdown scorecards; real replacement fixtures with separate truth and retained synthetic corpus; three recovered live faults per scenario and population variance; native separate Docker targets and non-root scorer volume | Gate: 123 Python + 1 web, 22 live tests; all six Top-1/precision/coverage 100%, no misses; negative make gates failed correctly; lint/actionlint/secret scan passed; .env unchanged | M6 not started`

`2026-10-14 00:39 IST | M4b | Six validated LangGraph nodes and repair edge; background jobs/status/artifacts, resumable SSE, full-scope witness and runbook provenance, confidence/check tamper rejection, API/CLI docs | Gate: 102 Python + 1 web; 18 live tests none skipped; both recovered scenarios with 512 resolved citations and 470 outside display; lint/actionlint/native build/secret scan passed; .env unchanged | Commit M4b; M5 not started`

`2026-10-13 22:23 IST | M4a | Synthetic-first observable goldens and separate scorer truth; six scoped read-only tools, BM25 runbooks, durable audits/provenance, deterministic adapter and exact scoring, one model/report correction; repaired mixed-operation ErrorSpike baseline | Gate: 89 Python + 1 web; 15 live tests none skipped; lint/secret scan green; native ARM64 image; .env unchanged | Commit M4a then M4b workflow/endpoints/live reports`

`2026-10-13 21:46 IST | M3 refinement | Frozen full-scope correlation and cited sources; versioned metric-series summaries (histogram data excluded); severe-log/error-slow-trace floors; latency baseline and route-specific chaos verifier; updated ADR-016 | 71 Python + 1 web, 14 live Docker tests, lint and secret scan passed; .env unchanged | M4a not started`

`2026-10-13 14:25 IST | M3 follow-up | Replaced round-robin cap with telemetry relevance and time/source ties; exact dropped counts; versioned immutable snapshots; printed all 100 live items; oldest-decisive synthetic tests; corrected commit/table and verified ADRs | 65 Python + 1 web, 14 live Docker tests, lint and secret scan passed; .env unchanged | M4a not started`

`2026-10-13 01:54 IST | M3 | Started with passing make test; delivered validated incident API, request IDs/errors, persisted scope bounds, immutable capped evidence/timelines, five pure correlators and isolated public scenario catalog; .env unchanged | Gate passed: 60 Python + 1 web, 13 live Docker tests including real replay/contradiction checks; lint/secret scan/CI validation green | M4`

`2026-10-13 01:30 IST | M2 | Audited and repaired M0+M1 first (e01c082); implemented restricted chaos registry, contracts, serialized injection/recovery, live signal gates and tests | Gate passed: both real scenarios recovered; 33 Python + 1 web tests, lint/CI/secret scan green | M3 Incident Core`

`2026-10-13 01:10 | M0+M1 | Implemented native lab, OTel ingest/storage/redaction, workspace, web shell, CI, docs; fixed all logged failures | Phase gate passed: 20 Python + 1 web tests; lint/build/health/secret scan green | M2 Chaos Lab`

---

## 8. HOW TO RESUME (any person / any AI / Codex after a credit reset)

1. Read sections 1 and 3 first.
2. Run `make test` and fix failures before new work.
3. Continue from "Next action" at the top.
4. When pasting into another chat, include this file's sections 1, 3 and the top header, plus the AIPI_CONTEXT.md file.
