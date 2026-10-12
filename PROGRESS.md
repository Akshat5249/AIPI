# PROGRESS.md — AIPI build log

> Source of truth for "where are we and where is it broken".
> Codex: update this file at the END of every phase and every time a command fails. Follow this format exactly. Never mark anything done unless you ran the verification command and saw it pass. Paste real command output (trimmed), not summaries.

**Last updated:** (date/time)
**Current phase:** M0+M1
**Next action:** Start M0+M1 (see section 2)
**Overall:** 0 / 7 phases complete
**Docker available:** unknown
**LLM provider:** mock

---

## 1. PHASE STATUS (one-glance table)

Status values: `NOT STARTED` · `IN PROGRESS` · `BLOCKED` · `PARTIAL` · `DONE (gate passed)`

| Phase | Name | Status | Gate command(s) | Gate result | Commit |
|---|---|---|---|---|---|
| M0+M1 | Foundation + Observability | NOT STARTED | `make up`, `make test` | — | — |
| M2 | Chaos Lab | NOT STARTED | `make chaos-kill`, `make chaos-lag` | — | — |
| M3 | Incident Core | NOT STARTED | `make test` (incident + isolation tests) | — | — |
| M4 | Agents + Tools + Report | NOT STARTED | `make test` (golden suite) | — | — |
| M5 | Evaluation | NOT STARTED | `make eval` | — | — |
| M6 | Dashboard | NOT STARTED | `make demo` + web tests | — | — |
| M7 | Polish | NOT STARTED | fresh-clone run of README | — | — |

---

## 2. PHASE CHECKLISTS

Tick a box only after verifying it. Add a one-line note (file/test name) next to each ticked item.

### M0+M1 Foundation + Observability
- [ ] Monorepo skeleton matches layout; uv workspace installs
- [ ] Typed config + `.env.example`
- [ ] Compose: PG primary + replica healthy
- [ ] Compose: otel-collector, api, gateway, checkout-api, orders-api, pg-lag-probe, event-watcher, traffic
- [ ] `/healthz` + `/readyz` on all services
- [ ] OTel traces/metrics/logs from demo services
- [ ] Collector → API `/internal/otlp/v1/*` ingest works
- [ ] Telemetry tables + normalization + redaction (with tests)
- [ ] One request → correlated trace + log (same trace_id) + metric in DB
- [ ] Makefile targets, CI workflow, lint/type/test commands
- [ ] **GATE:** `make up` healthy + `make test` green

### M2 Chaos Lab
- [ ] Scenario schema + SCN-001 + SCN-002 scripts
- [ ] Ground truth written to `ground_truth.chaos_runs`
- [ ] Precondition checks + recovery verification
- [ ] A: die→start events + 5xx spike visible
- [ ] B: lag rises, `replica_replay_paused=1`, primary healthy
- [ ] `make chaos-kill`, `make chaos-lag`
- [ ] **GATE:** both scenarios run and recover

### M3 Incident Core
- [ ] Incident CRUD + validation
- [ ] Bounded evidence retrieval + stable evidence IDs
- [ ] Immutable evidence, timeline builder, ScopePolicy
- [ ] Correlators (5 rules) + unit tests
- [ ] Error contract + request-id middleware
- [ ] Test: ground truth unreachable from APIs/tools
- [ ] **GATE:** same evidence IDs on re-run

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

_(no failures logged yet)_

---

## 4. DECISIONS AND DEVIATIONS

Anything that differs from the master prompt or the docs. Mirror major ones in `docs/DECISIONS.md` as an ADR.

| # | Date | What changed | Why | ADR |
|---|---|---|---|---|
| — | — | — | — | — |

---

## 5. SKIPPED / NOT VERIFIED

List anything not run (e.g. Docker tests skipped because Docker is unavailable, live LLM adapters untested). Be explicit so nothing is assumed working.

- (none yet)

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

`YYYY-MM-DD HH:MM | phase | what was done | result | next`

---

## 8. HOW TO RESUME (any person / any AI / Codex after a credit reset)

1. Read sections 1 and 3 first.
2. Run `make test` and fix failures before new work.
3. Continue from "Next action" at the top.
4. When pasting into another chat, include this file's sections 1, 3 and the top header, plus the AIPI_CONTEXT.md file.
