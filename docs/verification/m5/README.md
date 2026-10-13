# M5 measured evaluation

Three distinct live faults per scenario were injected and recovered on Apple Silicon with the mock investigator. All six passed. The scorer resolved citations through scoped API lookup and read the protected run oracle only after reports existed.

| Scenario | Top-1 / Top-3 | Precision / coverage | Unsupported | Latency mean ± stddev | Population variance | Tool efficiency mean |
|---|---|---|---|---|---|---|
| SCN-001 (n=3) | 100% / 100% | 100% / 100% | 0% | 2.298 ± 0.242 s | 0.058434 s² | 45.7500 supported items/call |
| SCN-002 (n=3) | 100% / 100% | 100% / 100% | 0% | 1.434 ± 0.842 s | 0.708663 s² | 14.9630 supported items/call |

Contradiction handling was 100% for both scenarios. No misses occurred. Population variance of the binary/ratio quality metrics was zero; latency and tool efficiency variance are retained. Mock per-token efficiency is null because token count is zero.

These are measurements of the two curated mock scenarios and bounded correlator/category claim vocabulary. The semantic gate rejects unsupported new prose rather than assuming general natural-language entailment.

- [Every run and full variance statistics](live-summary.json)
- [Markdown distributions](live-summary.md)

Generated JSON and Markdown scorecards live under eval_reports/. Recorded root fixtures under tests/fixtures/ are synthetic=false; separate *.truth.json files are scorer-only. The original hand-authored unit corpus remains under tests/fixtures/synthetic/. The poisoned recorded fixture adds one synthetic untrusted log.
