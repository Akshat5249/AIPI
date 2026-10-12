Demo, Interview & Resume Guide

How to present the project, explain trade-offs, and demonstrate measurable AI value

AI Production Incident Investigator

| Document ID | AIPI-13 |
| --- | --- |
| Version | 1.0 |
| Status | Implementation baseline |
| Primary audience | Developer / reviewer / interviewer |

# 1. 5-Minute Demo Script

1. Show healthy services and normal telemetry.
1. Run one deterministic fault injection (service kill or replica lag).
1. Open the incident dashboard and show symptom spike/timeline.
1. Start AI investigation; show agent steps and read-only tool calls.
1. Reveal ranked hypotheses and click evidence supporting the top cause.
1. Show the final report and then the evaluation score against hidden ground truth.
# 2. Interview Architecture Story

- Problem: incident evidence is fragmented and manual correlation is slow.
- Design choice: deterministic telemetry retrieval first, LLM reasoning second.
- Agentic element: explicit planner/retriever/hypothesis/verifier/reporter state machine with tools.
- Reliability element: every conclusion is evidence-linked and regression-tested against injected faults.
- Engineering trade-off: PostgreSQL first; specialized stores/Kafka only after measured need.
# 3. Resume Bullets

- Built an agentic AI incident investigation platform using FastAPI, LangGraph, OpenTelemetry and PostgreSQL to correlate logs, metrics and traces and rank evidence-backed root causes.
- Designed deterministic chaos scenarios and an automated evaluation harness measuring root-cause accuracy, evidence precision, hallucination rate and investigation latency.
- Implemented read-only investigation tools, structured agent state, telemetry correlation and a React dashboard for incident timelines, hypotheses and post-incident reports.
# 4. Likely Interview Questions

| Question | Strong answer theme |
| --- | --- |
| Why agents instead of one prompt? | Explicit state, tool boundaries, retries, evaluation and inspectability. |
| How do you reduce hallucinations? | Deterministic retrieval, stable evidence IDs, schema validation, claim-evidence checks. |
| Why not Kafka immediately? | MVP does not need its operational cost; add when asynchronous scale is measured. |
| How do you know the AI is correct? | Fault injection provides ground truth; replay suite produces objective metrics. |
| What would you change for production? | RBAC, tenant isolation, scalable telemetry stores, queues, SLOs, approved remediation. |
