Evaluation Framework

Ground truth, scoring, hallucination checks, and regression methodology

AI Production Incident Investigator

| Document ID | AIPI-07 |
| --- | --- |
| Version | 1.0 |
| Status | Implementation baseline |
| Primary audience | Developer / reviewer / interviewer |

# 1. Why Evaluation Is a First-Class Feature

The project is valuable because the agent can be tested against incidents with known causes. Fault injection creates ground truth, allowing regression tests that measure whether the system actually improves rather than merely producing plausible explanations.

# 2. Core Metrics

| Metric | Definition |
| --- | --- |
| Root-cause Top-1 accuracy | True cause is ranked first. |
| Root-cause Top-3 recall | True cause appears in top three. |
| Evidence precision | Cited evidence genuinely supports the associated claim. |
| Evidence coverage | Important ground-truth evidence was retrieved/cited. |
| Unsupported claim rate | Material claims with no supporting evidence. |
| Contradiction handling | System notices evidence that conflicts with leading hypothesis. |
| Investigation latency | Wall-clock time from start to report. |
| Tool efficiency | Useful evidence gathered per tool call / token budget. |

# 3. Scenario Registry

| Scenario | Ground truth | Pass condition |
| --- | --- | --- |
| SCN-001 Service Kill | checkout-api process/container terminated | Top-1 cause identifies service termination and cites exit/restart + correlated failures. |
| SCN-002 Replica Lag | PostgreSQL replica lag intentionally induced | Top-1 identifies replica lag and cites lag metric/status evidence without blaming primary failure. |

# 4. Hallucination Gate

- Every cited evidence ID must exist.
- Quoted values must match stored evidence.
- No invented trace IDs, log lines or deployment events.
- A release fails if a critical unsupported claim appears in the golden test set.
# 5. Experiment Tracking

- Record model/provider/version, prompt version, tool version, retrieval parameters and code commit.
- Store per-scenario scores to compare agent changes.
- Use fixed scenario seeds/configuration for reproducibility.
