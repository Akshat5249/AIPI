# Evaluation

`make eval` replays the two golden bundles and poisoned-log regression with mock,
prints per-scenario Top-1/Top-3, semantic citation precision, coverage, unsupported
rate and latency, and writes JSON + Markdown scorecards to `eval_reports/`.
It exits non-zero on Top-1 miss, critical hallucination, missing decisive coverage,
precision below 90%, or missed contradiction. CI runs this gate before image builds.

Every experiment records provider/model, prompt/tool versions, code commit, seed,
retrieval params and fixture digest. Recorded API replay uses investigation metadata.
Pure `hallucination_gate(report, scoped_evidence)` never reads truth, files, DB or
network. Unknown IDs, irrelevant citations, fabricated numeric quotes, trace IDs,
log/deploy text, unsupported critical prose and inconsistent Markdown/timelines fail.
Its critical root also requires direct causal conjunction evidence; relevant
symptoms alone cannot support a primary-outage conclusion.
Its claim vocabulary is deliberately the MVP correlator facts and category/next-check
contracts; it rejects unsupported new prose rather than claiming general entailment.

`make record-golden` runs at least three live repeats of each real fault, recovers
each, creates/investigates its scoped incident and calls the scorer. It replaces
synthetic root fixtures with real observable raw bundles; preserves originals in
`tests/fixtures/synthetic/`; writes separate scorer-only `*.truth.json`; and writes
per-run cards and `live-summary.json/.md` including variance and any misses. The
recorded poison fixture combines real telemetry with an added untrusted test log.
Do not run recording concurrently with another fault-injection command.

The scorer persists its API scorecards in the evaluation-results volume at
/app/eval_reports; host CLI scorecards are written to ./eval_reports. The volume
is initialized for its non-root UID so a fresh Linux CI checkout can write cards.

The scorer is a separate Compose service. Only it receives the protected truth
URL; neither public API nor investigator tools do. Golden agent replay is in a
credential-free subprocess and gets only observable JSON. Recorded replay reads
a completed protected run server-side after the report, checking the incident
covers that run and recovery succeeded. Returned job/scorecard API scores contain no expected
causal labels; the separate terminal-only /ground-truth route discloses the label
to the Evaluation page after scoring. Fault injection is host-only, never a model/tool action.

POST `/api/evaluations/replay` accepts `{"scenario_id":"SCN-001"}` for golden,
or `{"scenario_id":"SCN-002","mode":"recorded","incident_id":"...", "chaos_run_id":"..."}`
for a completed live incident. It returns 202 with a queued evaluation ID. Poll
GET `/api/evaluations/{id}` for completed/failed state and scorecard. Request IDs and
validation errors use the API envelope. The scorer has no public host port.

Metric definitions and tradeoffs are in ADR-019. Mock token efficiency is null;
zero tokens cannot be used as a denominator. Repeated runs report population
variance with n shown, so a single pass never stands in for reproducibility.

To review a saved report or exercise a negative gate:

```sh
make eval EVAL_ARGS="--report-override /tmp/report.json --output /tmp/scorecards"
```

The override is scored against SCN-002's scoped golden evidence. Unit tests invoke
this actual make command separately for unknown ID, fabricated metric and wrong
root cause, and assert both failure exit and the relevant failure code.


Results are the deterministic mock on **two curated scenarios, n=3 each**, not
real-LLM accuracy figures. The measured six runs, variance and no-miss record are
in PROGRESS.md section 6 and verification/m5/live-summary.json. Optional paid
adapters are unimplemented. New smoke/golden replay latencies are separate
verification measurements and do not replace that experiment. GitHub CI has not
run; local actionlint/tests do not establish a hosted CI result.
