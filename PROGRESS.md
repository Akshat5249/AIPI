# PROGRESS.md — AIPI build log

> Source of truth for "where are we and where is it broken".
> Codex: update this file at the END of every phase and every time a command fails. Follow this format exactly. Never mark anything done unless you ran the verification command and saw it pass. Paste real command output (trimmed), not summaries.

**Last updated:** 2026-10-13 01:54 IST
**Current phase:** M3 complete (gate passed)
**Next action:** M4 read-only tool registry, mock adapter and agent workflow (not started)
**Overall:** 3 / 7 phases complete
**Docker available:** yes — Docker Desktop aarch64; daemon access requires sandbox escalation
**LLM provider:** mock

---

## 1. PHASE STATUS (one-glance table)

Status values: `NOT STARTED` · `IN PROGRESS` · `BLOCKED` · `PARTIAL` · `DONE (gate passed)`

| Phase | Name | Status | Gate command(s) | Gate result | Commit |
|---|---|---|---|---|---|
| M0+M1 | Foundation + Observability | DONE (gate passed) | `make up`, `make test`, `make lint` | Healthy native arm64 lab; follow-up audit: 21 Python + 1 web tests passed | `ea3aee2`; audit `e01c082` |
| M2 | Chaos Lab | DONE (gate passed) | `make chaos-kill`, `make chaos-lag`, `make test`, `make lint` | Both live scenarios recovered; 33 Python + 1 web tests passed | `4b73c8c` |
| M3 | Incident Core | DONE (gate passed) | `make test`, `make lint`; live incident replay/isolation tests | 60 Python + 1 web passed; both real incident windows replay identical IDs | this commit: `feat(M3): scoped incident core and immutable evidence` |
| M4 | Agents + Tools + Report | NOT STARTED | `make test` (golden suite) | — | — |
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

### M4 Agents + Tools + Report
- [ ] 6 read-only tools + registry test (no mutating tool)
- [ ] LLM adapters (mock / anthropic / openai)
- [ ] LangGraph nodes: Triage, Retriever, Hypothesis, Verifier, Ranker, Reporter
- [ ] Confidence scoring + unit tests
- [ ] Report schema validation + unknown-ID rejection
- [ ] Investigation endpoints + SSE events
- [ ] Recommendations (recommend-only)
- [ ] Prompt-injection tests
- [ ] Golden tests on synthetic bundles, then live
- [ ] **GATE:** both scenarios → valid evidence-linked report, golden green

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
### F-001 — <short title>            Status: OPEN | RESOLVED
- Phase/step:
- Command:
- Error (trimmed, real output):
- Suspected cause:
- Tried:
- Fix / workaround (if resolved):
- Files touched:
```

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

---

## 5. SKIPPED / NOT VERIFIED

List anything not run (e.g. Docker tests skipped because Docker is unavailable, live LLM adapters untested). Be explicit so nothing is assumed working.

- GitHub-hosted CI was not executed; workflow passed local actionlint, YAML contract tests, and corresponding local build/test/Compose gates.
- M4–M7 deliverables and gates are not started. Six-tool registry, agents/LLM/LangGraph, golden evaluation and the full dashboard remain deferred. No agent or model implementation was added in M3.
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

`2026-10-13 01:54 IST | M3 | Started with passing make test; delivered validated incident API, request IDs/errors, persisted scope bounds, immutable capped evidence/timelines, five pure correlators and isolated public scenario catalog; .env unchanged | Gate passed: 60 Python + 1 web, 13 live Docker tests including real replay/contradiction checks; lint/secret scan/CI validation green | M4`

`2026-10-13 01:30 IST | M2 | Audited and repaired M0+M1 first (e01c082); implemented restricted chaos registry, contracts, serialized injection/recovery, live signal gates and tests | Gate passed: both real scenarios recovered; 33 Python + 1 web tests, lint/CI/secret scan green | M3 Incident Core`

`2026-10-13 01:10 | M0+M1 | Implemented native lab, OTel ingest/storage/redaction, workspace, web shell, CI, docs; fixed all logged failures | Phase gate passed: 20 Python + 1 web tests; lint/build/health/secret scan green | M2 Chaos Lab`

---

## 8. HOW TO RESUME (any person / any AI / Codex after a credit reset)

1. Read sections 1 and 3 first.
2. Run `make test` and fix failures before new work.
3. Continue from "Next action" at the top.
4. When pasting into another chat, include this file's sections 1, 3 and the top header, plus the AIPI_CONTEXT.md file.
