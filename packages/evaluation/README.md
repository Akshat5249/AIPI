# Evaluation

Pure gate and scoring functions operate on validated reports and scoped evidence.
Only oracle.py reads protected DB truth or separate truth files. Offline replay
runs the observable graph in a credential-free child before opening the oracle.
The separate server persists replay jobs/cards; the public API is a score-only proxy.

Run `make eval` for deterministic golden gates and `make record-golden` for three
real repeats per scenario, replacement fixtures and variance. Metrics/limitations,
API/CLI contracts and negative tests are documented in docs/EVALUATION.md and ADR-019.
