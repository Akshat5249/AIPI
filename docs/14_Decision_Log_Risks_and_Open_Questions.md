Decision Log, Risks & Open Questions

Architecture decisions, risk register, assumptions, and future experiments

AI Production Incident Investigator

| Document ID | AIPI-14 |
| --- | --- |
| Version | 1.0 |
| Status | Implementation baseline |
| Primary audience | Developer / reviewer / interviewer |

# 1. Architecture Decision Records

| ADR | Decision | Reason |
| --- | --- | --- |
| ADR-001 | LangGraph for orchestration | Explicit state machine and inspectable tool transitions. |
| ADR-002 | PostgreSQL-first storage | Lower complexity for MVP; sufficient for curated demo volume. |
| ADR-003 | OpenTelemetry standard | Vendor-neutral correlation across logs, metrics and traces. |
| ADR-004 | Read-only tools in MVP | Prevents unsafe autonomous remediation while accuracy is unproven. |
| ADR-005 | Ground-truth chaos scenarios | Makes agent quality measurable and regression-testable. |
| ADR-006 | No Kafka in first slice | Avoid infrastructure without demonstrated asynchronous throughput need. |

# 2. Risk Register

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Scope explosion | Project never reaches demo quality | Two scenarios only until evaluation passes. |
| Weak telemetry correlation | Agent sees noisy evidence | Standardize OTel attributes and stable IDs. |
| LLM hallucination | Incorrect root cause | Evidence gate, contradictions, golden tests. |
| Cost/latency | Slow investigations | Bound context, cache retrieval, smaller models for substeps. |
| Synthetic demo feels unrealistic | Weak interview credibility | Use real service/DB behavior and injected faults with actual telemetry. |

# 3. Open Questions

- Which LLM provider/model gives best structured reasoning at acceptable cost?
- Whether pgvector is needed for runbook retrieval or keyword/BM25 is sufficient initially.
- Whether logs should remain in Postgres or move to a telemetry-specific backend after profiling.
- How to calibrate confidence scores across heterogeneous scenarios.
