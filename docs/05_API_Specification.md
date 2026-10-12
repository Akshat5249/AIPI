API Specification

Backend endpoints, request/response contracts, and error conventions

AI Production Incident Investigator

| Document ID | AIPI-05 |
| --- | --- |
| Version | 1.0 |
| Status | Implementation baseline |
| Primary audience | Developer / reviewer / interviewer |

# 1. API Principles

- JSON over HTTP for MVP.
- Pydantic schemas for all requests/responses.
- Stable incident and evidence identifiers.
- Long-running investigation exposed as job/state transitions or streaming events.
# 2. Endpoint Catalog

| Method | Endpoint | Purpose |
| --- | --- | --- |
| POST | /api/incidents | Create incident |
| GET | /api/incidents/{id} | Get incident metadata/status |
| POST | /api/incidents/{id}/investigate | Start investigation |
| GET | /api/incidents/{id}/evidence | List correlated evidence |
| GET | /api/incidents/{id}/hypotheses | List ranked hypotheses |
| GET | /api/incidents/{id}/timeline | Get incident timeline |
| GET | /api/incidents/{id}/report | Get final report |
| GET | /api/investigations/{id}/events | Agent/tool execution events |
| POST | /api/evaluations/replay | Replay a ground-truth scenario |
| GET | /api/evaluations/{id} | Get evaluation scores |

# 3. Example Create Incident

POST /api/incidents

{

"title": "Checkout errors",

"service": "checkout-api",

"start_time": "2026-10-13T10:00:00Z",

"end_time": "2026-10-13T10:15:00Z",

"symptom": "5xx rate increased above baseline"

}

# 4. Error Contract

{ "error": { "code": "EVIDENCE_QUERY_TIMEOUT", "message": "...", "retryable": true, "request_id": "..." } }
