Codex / AI Coding Build Instructions

Repository rules and staged prompts for implementing the project safely

AI Production Incident Investigator

| Document ID | AIPI-15 |
| --- | --- |
| Version | 1.0 |
| Status | Implementation baseline |
| Primary audience | Developer / reviewer / interviewer |

# 1. Build Objective

Implement the project incrementally as a production-style monorepo. Prioritize deterministic behavior, tests and observability over breadth. Do not add technologies merely because they appear in the long-term architecture.

# 2. Non-Negotiable Engineering Rules

- Every feature must include tests.
- All external/model/tool outputs must be schema-validated.
- No secrets in code, fixtures or logs.
- No mutating investigation tool in MVP.
- Every agent conclusion must reference evidence IDs.
- Do not expose ground-truth scenario labels to the agent during evaluation.
- Keep modules small and typed; document public interfaces.
- Prefer deterministic parsers/correlation rules before LLM calls.
# 3. First Implementation Prompt

Create the repository foundation for AI Production Incident Investigator.

Use Python + FastAPI for backend, React + TypeScript for frontend, PostgreSQL, OpenTelemetry Collector, Docker Compose, Pytest, and LangGraph.

Implement only Milestone M0/M1: health endpoints, one demo service request path, PostgreSQL connectivity, OpenTelemetry traces/metrics/structured logs, local Compose stack, typed configuration, lint/type-check/test commands, and CI.

Do NOT implement the AI agents yet.

Acceptance: `make up` starts a healthy stack; one demo request produces correlated trace/log/metric data; tests pass from a fresh clone.

# 4. Second Implementation Prompt

Implement the chaos-lab and incident-core slice. Add two deterministic scenarios: target service termination and PostgreSQL replica lag. Record scenario_id, injection timestamp, target, expected root cause and recovery status. Add incident CRUD and read-only evidence retrieval bounded by service and time window. Do NOT expose scenario ground truth to investigation APIs. Add integration tests and reproducible seed traffic.

# 5. Agent Slice Prompt

Implement a LangGraph investigation workflow with Triage, Evidence Retrieval, Hypothesis Generation, Verification, Ranking and Reporting nodes. All tools are read-only and return structured evidence objects with stable IDs. Require hypotheses to be falsifiable and store evidence FOR/AGAINST each hypothesis. Reject final reports containing unknown evidence IDs. Add golden regression tests using saved evidence bundles before connecting live telemetry.

# 6. Completion Checklist

- Fresh-clone setup documented.
- Both chaos scenarios reproducible.
- Investigation output structured and evidence-linked.
- Golden evaluation suite automated.
- Dashboard demo path works without manual database edits.
- README and architecture docs match actual implementation.
