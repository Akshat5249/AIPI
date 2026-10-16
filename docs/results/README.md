# Measured mock evaluation

On 2026-10-14, three separate real Docker faults per scenario were injected,
recovered, investigated and scored on Apple Silicon with Docker Desktop. The
investigator used the **deterministic mock** with seed 42. All six reports passed.
These are results for **two curated scenarios, n=3 each**, not real-LLM accuracy,
production reliability or load/throughput measurements.

The [raw experiment record](mock-live-runs.json) is preserved byte-for-byte from
the original recording. It contains six scorecards with timestamps, investigation
IDs, provider/model, prompt/tool versions, code commit, seed, fixture/retrieval
metadata, all metric samples and any misses. Its `+working-tree` commit marker is
the original measurement provenance, not a claim that later changes were tested
by that experiment.

| Metric | Six-run result |
|---|---|
| Top-1 / Top-3 recall | 100% (6/6) / 100% |
| Evidence precision / coverage | 100% / 100% |
| Unsupported claim rate / critical unsupported claims | 0% / 0 |
| Contradiction handling | 100% |
| Verified scripted recovery | 100% (6/6) |
| Median investigation latency | 2.12955 s |
| Mutating investigation actions | 0 |

| Scenario (n=3) | Latency samples (ms) | Mean (ms) | Median (ms) | Stddev (ms) | Population variance (ms²) | Useful evidence/call mean | Efficiency variance |
|---|---|---|---|---|---|---|---|
| SCN-001 | 2633.48, 2074.76, 2184.33 | 2297.53 | 2184.33 | 241.73 | 58434.34 | 45.7500 | 7.072917 |
| SCN-002 | 2623.26, 877.35, 800.14 | 1433.58 | 877.35 | 841.82 | 708662.68 | 14.9630 | 0.068587 |

No misses occurred in those six measured runs. Quality metric population variances
were zero. Mock tokens/cost are zero; per-token efficiency is null because zero
cannot be used as a denominator. Latency covers investigation, not dependency
installation, image builds, baseline collection or fault injection/recovery.
The later default workload change to one cycle/s does not alter this historical
record. New golden or smoke latencies are separate measurements.

The scorer resolved all citations through scoped evidence lookup and opened the
protected run oracle only after reports existed. The bounded claim/category gate
is described in [Evaluation](../EVALUATION.md) and [ADR-019](../DECISIONS.md).
The results do not establish general semantic hallucination detection or
statistically reliable generalization beyond these scenarios.

## Reproduce the experiment

After [setup](../../README.md#quick-start), start the lab and traffic, then run:

```sh
make record-golden  # three new real runs per scenario; replaces recorded root fixtures
```

Run it serially, not during another chaos/demo/test command. JSON/Markdown
scorecards and `live-summary.json/.md` are generated under ignored `eval_reports/`.
`tests/fixtures/synthetic/` keeps the original unit corpus; `*.truth.json` remains
separate and scorer-only. Recording intentionally replaces the tracked root
fixtures, so review those changes before committing. Use `make eval` to replay
the existing recorded corpus without injecting another live fault.
