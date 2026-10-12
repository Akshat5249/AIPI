Implementation Roadmap & Backlog

Milestones, build order, scope control, and definition of done

AI Production Incident Investigator

| Document ID | AIPI-08 |
| --- | --- |
| Version | 1.0 |
| Status | Implementation baseline |
| Primary audience | Developer / reviewer / interviewer |

# 1. Milestones

| Milestone | Deliverable | Definition of done |
| --- | --- | --- |
| M0 Foundation | Repo, Compose, CI, sample services | One command starts stack; tests run in CI. |
| M1 Observability | OTel instrumentation + collector + storage | Trace/log/metric correlation works for a normal request. |
| M2 Chaos Lab | Service kill + replica lag scripts | Each scenario records exact injection and expected cause. |
| M3 Incident Core | Incident API + evidence retrieval | Incident window returns deterministic evidence bundle. |
| M4 Agent Investigation | LangGraph agents + tools | Both MVP scenarios produce structured hypotheses and evidence. |
| M5 Evaluation | Replay harness + scorecard | Automated Top-1/evidence/hallucination metrics. |
| M6 Dashboard | React investigation UI | Timeline, evidence, hypotheses and report visible. |
| M7 Polish | Docs, demo seed, deployment | Fresh clone can run documented demo. |

# 2. MVP Backlog

- Repository scaffolding and environment validation.
- Demo request path: gateway -> service -> PostgreSQL.
- OTel collector configuration.
- Telemetry normalization and storage adapter.
- Incident CRUD + investigation state machine.
- Read-only tools: logs query, metric query, trace lookup, DB replication status, runbook search.
- Structured hypothesis schema and verification loop.
- Scenario registry + fault injection scripts.
- Evaluation CLI/API.
- Dashboard and final report export.
# 3. Scope Discipline

Do not add Kubernetes, multiple clouds, autonomous remediation, a vector database, or more than two fault scenarios until the evaluation harness is working. Each additional technology must solve a measured bottleneck.
