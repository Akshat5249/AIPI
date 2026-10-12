Master Project Blueprint

Complete documentation map, MVP boundary, and execution order

AI Production Incident Investigator

| Document ID | AIPI-00 |
| --- | --- |
| Version | 1.0 |
| Status | Implementation baseline |
| Primary audience | Developer / reviewer / interviewer |

# 1. Project Definition

An AI-assisted incident investigation platform that ingests production telemetry, correlates evidence across logs, metrics, traces and runbooks, forms competing root-cause hypotheses, tests them with read-only tools, and produces an evidence-backed incident report. The system is designed around measurable fault-injection scenarios rather than open-ended chatbot behavior.

# 2. MVP Boundary

- Scenario A: application/service process crash or forced termination.
- Scenario B: PostgreSQL replica lag / unhealthy replication.
- Telemetry: OpenTelemetry traces + metrics + structured logs.
- Investigation output: ranked hypotheses, evidence links, confidence, timeline, recommended next checks, and post-incident summary.
- Human approval is required before any mutating remediation action; MVP is read-only.
# 3. Documentation Map

| # | Document | Purpose |
| --- | --- | --- |
| 00 | Master Project Blueprint | Single source of truth and build order |
| 01 | PRD & Scope | Users, requirements, MVP and acceptance criteria |
| 02 | System Architecture | Components, flows, deployment and trade-offs |
| 03 | Agentic AI Design | Agents, orchestration, tools, prompts and guardrails |
| 04 | Telemetry & Data Contracts | Logs, metrics, traces, schemas and ingestion |
| 05 | API Specification | Backend endpoints and payload contracts |
| 06 | Database Design | Relational schema, indexes and retention |
| 07 | Evaluation Framework | Ground truth, scoring and hallucination checks |
| 08 | Implementation Roadmap | Milestones, backlog and definition of done |
| 09 | Testing & Chaos Plan | Unit/integration/e2e/fault injection scenarios |
| 10 | Security & Threat Model | Access control, prompt injection, secrets and safety |
| 11 | Deployment & DevOps | Local, Docker, CI/CD, observability and environments |
| 12 | README & Developer Setup | Repository-facing quickstart and commands |
| 13 | Demo & Interview Guide | Demo script, architecture story and resume bullets |
| 14 | Decision Log & Risks | ADRs, assumptions, risks and open questions |
| 15 | Codex Build Instructions | Repository rules and implementation prompts |

# 4. Recommended Build Sequence

1. Create deterministic fault-injection lab and capture ground truth.
1. Instrument services with OpenTelemetry and normalize telemetry.
1. Build ingestion, storage and incident-window retrieval.
1. Implement deterministic correlation before adding LLM reasoning.
1. Add hypothesis-generation and evidence-verification agents.
1. Create evaluation harness and regression dataset.
1. Build dashboard and incident report UI.
1. Containerize, automate tests, and prepare demo.
# 5. Success Targets

| Metric | MVP target |
| --- | --- |
| Root-cause Top-1 accuracy | >= 80% on curated scenarios |
| Evidence citation precision | >= 90% cited evidence exists and supports claim |
| Unsupported critical claims | 0 in release test set |
| Median investigation latency | < 60 seconds on local demo dataset |
| Scenario reproducibility | 100% scripted fault injection |
| Mutating production actions | 0 without explicit human approval |
