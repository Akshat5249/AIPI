Telemetry & Data Contracts

OpenTelemetry conventions, evidence schemas, and scenario observability

AI Production Incident Investigator

| Document ID | AIPI-04 |
| --- | --- |
| Version | 1.0 |
| Status | Implementation baseline |
| Primary audience | Developer / reviewer / interviewer |

# 1. Telemetry Standard

Instrument demo services with OpenTelemetry. Normalize service.name, deployment/environment, trace_id, span_id, severity, host/container identity, database attributes and incident time windows so cross-signal correlation is reliable.

# 2. Minimum Signals

| Signal | Required fields | Examples |
| --- | --- | --- |
| Logs | timestamp, service, severity, body, trace_id, span_id | process exit, DB errors, timeout |
| Metrics | timestamp, service, metric_name, value, labels | error_rate, latency_p95, replica_lag_seconds |
| Traces | trace_id, span_id, parent_span_id, service, operation, status, duration | HTTP -> service -> PostgreSQL |
| Deployment events | timestamp, service, version, action | deploy/restart/config change |
| Chaos events | scenario_id, injection time, target, expected effect | kill service, delay replica |

# 3. Canonical Evidence Object

{

"evidence_id": "ev_...",

"type": "log|metric|trace|event|runbook",

"service": "orders-api",

"timestamp": "ISO-8601",

"source_ref": "stable storage reference",

"summary": "short deterministic summary",

"payload": {},

"redactions": []

}

# 4. MVP Scenario Signals

| Scenario | Expected observable evidence |
| --- | --- |
| Service crash | container/process exit, availability drop, error spike, failed spans, restart event |
| Replica lag | replica_lag_seconds increase, read staleness/latency symptoms, replication status/log evidence, primary remains healthy |

# 5. Retention

- Keep curated evaluation incidents permanently in the test dataset.
- For demo telemetry, retain enough history to replay incidents.
- Do not store secrets or full sensitive payloads in logs.
- Add retention/partitioning only after measuring volume.
