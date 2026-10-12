README & Developer Setup

Repository-facing overview, structure, stack, and quickstart

AI Production Incident Investigator

| Document ID | AIPI-12 |
| --- | --- |
| Version | 1.0 |
| Status | Implementation baseline |
| Primary audience | Developer / reviewer / interviewer |

# What This Project Does

AI Production Incident Investigator is an evidence-grounded agentic AI system for diagnosing production incidents. It correlates OpenTelemetry logs, metrics and traces, generates falsifiable root-cause hypotheses, verifies them through read-only tools, and scores itself against known fault-injection ground truth.

# MVP Demo

- Inject a service crash or PostgreSQL replica lag.
- Create an incident for the affected time window.
- Run the investigation graph.
- Inspect ranked hypotheses, supporting/contradicting evidence, timeline and final report.
- Replay the scenario to compute accuracy and hallucination metrics.
# Suggested Repository Structure

apps/

api/

web/

services/

demo-services/

packages/

agents/

tools/

telemetry/

evaluation/

infra/

docker/

otel/

postgres/

chaos/

scenarios/

docs/

tests/

unit/ integration/ golden/ e2e/

# Core Stack

Python, FastAPI, LangGraph, OpenTelemetry, PostgreSQL, React/TypeScript, Docker Compose, Pytest. Kafka is an optional later addition when asynchronous event volume justifies it; it is not required for the first MVP.

# Developer Commands

make up              # start local stack

make seed-traffic    # generate normal workload

make chaos-kill      # inject service termination

make chaos-lag       # inject replica lag

make investigate ID=<incident_id>

make eval            # run golden scenario suite

make test            # unit/integration tests

# Definition of a Good Investigation

- Correct cause ranked highly.
- Evidence IDs are real and relevant.
- Contradictions are acknowledged.
- No invented telemetry.
- Recommendations are clearly marked and remain non-mutating in MVP.
