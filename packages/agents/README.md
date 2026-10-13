# Agents

M4a provides strict schemas, a deterministic mock adapter, versioned escaped data
prompts, pure evidence verification, the section-8 scoring formula, and validated
report generation with one repair. `offline.investigate` accepts only observable
scoped evidence and correlator signals. Synthetic truth is owned by the scorer.

The default provider needs no key or network. Optional paid-provider adapters are
deferred; unsupported providers fail explicitly rather than silently using mock.
LangGraph orchestration and the HTTP supervisor are delivered in M4b.
