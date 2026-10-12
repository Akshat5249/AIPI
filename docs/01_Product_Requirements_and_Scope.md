Product Requirements Document

Users, requirements, scope, and acceptance criteria

AI Production Incident Investigator

| Document ID | AIPI-01 |
| --- | --- |
| Version | 1.0 |
| Status | Implementation baseline |
| Primary audience | Developer / reviewer / interviewer |

# 1. Problem Statement

Production incidents generate fragmented signals across logs, metrics, traces, deployments and runbooks. Engineers spend time manually correlating these signals under pressure. The project aims to reduce mean time to identify (MTTI) by automating evidence collection and structured hypothesis testing while keeping conclusions traceable and human-verifiable.

# 2. Target Users

| Persona | Need |
| --- | --- |
| On-call SRE / backend engineer | Fast evidence correlation and likely root cause. |
| Incident commander | Clear timeline, confidence and next actions. |
| Engineering manager | Repeatable post-incident report and measurable investigation quality. |
| AI/Platform engineer | Evaluation traces showing where the agent succeeded or failed. |

# 3. Functional Requirements

| ID | Requirement | Priority |
| --- | --- | --- |
| FR-01 | Ingest structured logs, metrics and traces from instrumented services. | P0 |
| FR-02 | Create an incident with service, time window and symptoms. | P0 |
| FR-03 | Retrieve correlated telemetry for the incident window. | P0 |
| FR-04 | Generate multiple root-cause hypotheses. | P0 |
| FR-05 | Use read-only tools to gather evidence for/against each hypothesis. | P0 |
| FR-06 | Rank hypotheses and expose confidence with evidence citations. | P0 |
| FR-07 | Generate incident timeline and investigation report. | P0 |
| FR-08 | Replay saved incidents for evaluation. | P0 |
| FR-09 | Show agent/tool execution trace and token/cost metadata. | P1 |
| FR-10 | Recommend remediation but require approval before execution. | P1 |

# 4. Non-Functional Requirements

- Traceability: every material conclusion links to source telemetry or runbook evidence.
- Determinism where possible: retrieval and correlation rules precede generative reasoning.
- Security: least privilege, read-only investigation tools, secret redaction.
- Observability: every agent step and tool call is traced.
- Extensibility: new failure scenarios and tools can be added without rewriting orchestration.
- Performance: local demo investigation completes within roughly one minute.
# 5. Out of Scope for MVP

- Autonomous production remediation.
- Full enterprise multi-tenancy and billing.
- Arbitrary cloud-provider control plane changes.
- General-purpose chatbot functionality.
- Training a foundation model from scratch.
# 6. Acceptance Criteria

- Given a forced service crash, the system identifies the terminated service/process as Top-1 cause and cites the supporting telemetry.
- Given induced replica lag, the system identifies replication delay as the likely cause and cites replication metrics/logs.
- The report distinguishes facts, hypotheses, and recommendations.
- A saved scenario can be replayed and scored automatically.
