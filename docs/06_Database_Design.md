Database Design

Relational schema, indexes, integrity, and retention

AI Production Incident Investigator

| Document ID | AIPI-06 |
| --- | --- |
| Version | 1.0 |
| Status | Implementation baseline |
| Primary audience | Developer / reviewer / interviewer |

# 1. Core Tables

| Table | Purpose | Key fields |
| --- | --- | --- |
| incidents | Incident metadata | id, service, start_time, end_time, symptom, status |
| investigations | Each investigation run | id, incident_id, model, started_at, completed_at, status |
| evidence | Normalized evidence index | id, incident_id, type, service, timestamp, source_ref, payload_json |
| hypotheses | Candidate causes | id, investigation_id, statement, rank, confidence |
| hypothesis_evidence | Evidence relation | hypothesis_id, evidence_id, stance, weight |
| tool_calls | Agent tool audit trail | id, investigation_id, tool, args_json, result_ref, latency_ms |
| reports | Generated report | investigation_id, root_cause, markdown, version |
| scenarios | Ground truth registry | id, name, injected_fault, expected_root_cause |
| evaluation_runs | Scores per replay | id, scenario_id, investigation_id, metrics_json |

# 2. Indexes

- incidents(service, start_time, end_time)
- evidence(service, timestamp)
- evidence(incident_id, type)
- hypotheses(investigation_id, rank)
- tool_calls(investigation_id, created_at)
- evaluation_runs(scenario_id, created_at)
# 3. Data Integrity

- Foreign keys on all investigation artifacts.
- Immutable evidence records after ingestion; corrections create a new version/reference.
- JSON fields are acceptable for heterogeneous telemetry payloads, but core query fields remain typed columns.
- Ground-truth scenario fields are not exposed to the investigation agent during evaluation.
