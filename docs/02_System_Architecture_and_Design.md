System Architecture & Design

Components, data flow, deployment boundaries, and trade-offs

AI Production Incident Investigator

| Document ID | AIPI-02 |
| --- | --- |
| Version | 1.0 |
| Status | Implementation baseline |
| Primary audience | Developer / reviewer / interviewer |

# 1. Architecture Overview

[Demo Services / Chaos Lab]

| OTLP logs/metrics/traces

v

[OpenTelemetry Collector] ---> [Telemetry Store]

|                         Postgres + optional object storage

v

[Incident API / FastAPI] ---> [Incident DB]

|

v

[LangGraph Orchestrator]

| Triage | Retrieval | Hypothesis | Verification | Reporter |

|              read-only tools              |

+----> SQL / metrics / traces / runbooks <--+

|

v

[Evaluation Harness] <---- [Ground Truth Scenario Registry]

|

v

[React Investigation Dashboard]

# 2. Core Components

| Component | Responsibility | Suggested tech |
| --- | --- | --- |
| Demo services | Generate realistic request paths and failures. | FastAPI / sample microservices |
| Chaos controller | Inject deterministic failures and record ground truth. | Python scripts / Docker Compose |
| OTel Collector | Receive/export telemetry. | OpenTelemetry Collector |
| Telemetry storage | Store searchable telemetry. | PostgreSQL; optional ClickHouse later |
| Incident API | Incident lifecycle and retrieval endpoints. | FastAPI |
| Agent orchestrator | State machine for investigation. | LangGraph |
| Retriever/tools | Read-only queries over evidence. | Python tool adapters |
| Evaluation harness | Replay and score incidents. | Pytest + custom metrics |
| Dashboard | Timeline, hypotheses, evidence and traces. | React + TypeScript |

# 3. Investigation Flow

1. Incident created with affected service and time window.
1. Triage agent summarizes symptoms from deterministic telemetry queries.
1. Retrieval agent gathers relevant logs, metrics, traces, deployment metadata and runbook sections.
1. Hypothesis agent proposes a small ranked set of plausible causes.
1. Verification agent calls read-only tools to collect supporting and contradicting evidence.
1. Judge/ranker updates confidence using evidence, not model self-confidence alone.
1. Reporter produces timeline, likely root cause, evidence, uncertainty and recommended next checks.
1. Evaluation harness compares output against scenario ground truth.
# 4. Key Architecture Decisions

- Start with PostgreSQL for operational simplicity; introduce specialized telemetry storage only after profiling.
- Use LangGraph for explicit state transitions, retries and inspection rather than free-form agent chat.
- Store raw evidence identifiers so every report statement can be traced back.
- Separate retrieval from reasoning to reduce hallucination and make evaluation possible.
- Keep remediation tools disabled/read-only in MVP.
