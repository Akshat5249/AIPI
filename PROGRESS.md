# PROGRESS.md — AIPI build log

> Source of truth for "where are we and where is it broken".
> Codex: update this file at the END of every phase and every time a command fails. Follow this format exactly. Never mark anything done unless you ran the verification command and saw it pass. Paste real command output (trimmed), not summaries.

**Last updated:** 2026-10-14 00:39 IST
**Current phase:** M4 complete — gate passed
**Next action:** M5 Evaluation when requested; M4 verified and committed
**Overall:** 4 / 7 phases complete
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
| M4 | Agents + Tools + Report | DONE (gate passed) | `make test`, `make lint`; synthetic goldens and live reports | 102 Python + 1 web; 18 live tests, none skipped; both scoped mock reports valid | M4a `afba25f`; `feat(M4b)` in this commit |
| M5 | Evaluation | NOT STARTED | `make eval` | — | — |
| M6 | Dashboard | NOT STARTED | `make demo` + web tests | — | — |
| M7 | Polish | NOT STARTED | fresh-clone run of README | — | — |

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
- [ ] Metrics + hallucination gate
- [ ] Scorecards in `eval_reports/`
- [ ] Replay API + CLI, experiment metadata
- [ ] `make eval`, `make record-golden`
- [ ] **GATE:** `make eval` exits non-zero on critical hallucination / Top-1 miss

### M6 Dashboard
- [ ] Incidents list + create
- [ ] Detail tabs: Timeline, Evidence, Hypotheses, Report, Agent Trace
- [ ] Evaluation page
- [ ] Vitest tests + Dockerfile/Compose service
- [ ] **GATE:** full demo path without manual DB edits

### M7 Polish
- [ ] README (quickstart, architecture, demo script)
- [ ] docs/ (ARCHITECTURE, API, TELEMETRY, EVALUATION, SECURITY, DEPLOYMENT, DECISIONS, DEMO_GUIDE)
- [ ] `make demo`, CI complete (gitleaks, hallucination gate, smoke test)
- [ ] **GATE:** fresh clone works exactly as documented

---

## 3. FAILURE LOG (newest first)

Add an entry whenever a command, test, or build fails and is not fixed immediately. Keep it until resolved, then mark `RESOLVED` (don't delete).

```
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

---

## 5. SKIPPED / NOT VERIFIED

List anything not run (e.g. Docker tests skipped because Docker is unavailable, live LLM adapters untested). Be explicit so nothing is assumed working.

- GitHub-hosted CI was not executed; workflow passed local actionlint, YAML contract tests, and corresponding local build/test/Compose gates.
- M4 is verified locally with mock, including both live scenarios. M5–M7 evaluation/replay, dashboard and final polish are not started. Synthetic bundles remain golden fixtures; real reports are verification captures, not M5 recorded goldens.
- Fresh-clone verification remains the M7 gate; this machine's documented `make setup` and M0+M1 commands were verified.
- Live LLM providers not implemented/tested; no API key used. Success-target metrics remain unmeasured until M5.

---

## 6. SUCCESS-TARGET METRICS (fill after M5; report honestly, including misses)

| Metric | Target | Actual | Date measured | Notes |
|---|---|---|---|---|
| Root-cause Top-1 accuracy | ≥ 80% | — | — | |
| Evidence citation precision | ≥ 90% | — | — | |
| Unsupported critical claims | 0 | — | — | |
| Median investigation latency | < 60 s | — | — | |
| Scenario reproducibility | 100% | — | — | |
| Mutating actions without approval | 0 | — | — | |

---

## 7. LOG (append one line per work session, newest first)

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
