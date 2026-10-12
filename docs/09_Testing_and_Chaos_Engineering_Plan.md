Testing & Chaos Engineering Plan

Test pyramid, deterministic fault injection, and CI quality gates

AI Production Incident Investigator

| Document ID | AIPI-09 |
| --- | --- |
| Version | 1.0 |
| Status | Implementation baseline |
| Primary audience | Developer / reviewer / interviewer |

# 1. Test Pyramid

| Layer | Examples |
| --- | --- |
| Unit | parsers, correlation rules, confidence score, schema validation |
| Component | tool adapters against seeded telemetry |
| Integration | OTel -> storage -> incident retrieval |
| Agent regression | saved evidence bundles -> expected hypotheses |
| End-to-end | inject fault -> investigate -> score -> dashboard report |

# 2. Chaos Scenario Template

| Field | Required content |
| --- | --- |
| Scenario ID | Stable identifier |
| Preconditions | Healthy system state |
| Injection | Exact scripted fault |
| Ground truth | Actual root cause |
| Expected signals | Logs/metrics/traces/events |
| Expected false leads | Plausible but wrong symptoms |
| Recovery | How lab returns to healthy state |
| Evaluation | Pass/fail thresholds |

# 3. Scenario A - Service Kill

- Precondition: steady request traffic and healthy DB.
- Injection: terminate target service/container at recorded timestamp.
- Expected: 5xx/availability symptom, failed spans, process/container exit, restart/recovery event.
- False lead: downstream timeout may look like network/DB failure.
- Pass: true cause Top-1 with direct termination evidence.
# 4. Scenario B - Replica Lag

- Precondition: primary and replica healthy.
- Injection: intentionally delay or pause replication using a safe local lab mechanism.
- Expected: lag metric/status increases while primary remains available.
- False lead: application latency or stale reads.
- Pass: identifies replica lag and distinguishes it from primary outage.
# 5. CI Gates

- Lint/type-check/unit tests.
- Schema compatibility tests.
- Golden agent regression tests using saved evidence bundles.
- No critical hallucination-gate failures.
- Docker Compose health-check smoke test.
