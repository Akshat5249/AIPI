# Incident Core API (M3)

The public API listens on http://localhost:8000. OpenAPI is at `/docs`.
No authentication is provided in this local MVP. There are no investigation
agents, model calls, or remediation endpoints in M3.

| Method | Endpoint | Response |
|---|---|---|
| POST | /api/incidents | Created incident (201) |
| GET | /api/incidents | Most recent 100 incidents; optional service/status filters |
| GET | /api/incidents/{id} | Immutable incident metadata |
| GET | /api/incidents/{id}/evidence | Immutable evidence bundle, at most 50 items |
| GET | /api/incidents/{id}/timeline | Chronological observations with evidence IDs |
| GET | /api/incidents/{id}/signals | Deterministic, evidence-citing correlator signals |
| GET | /api/scenarios | Static public catalog: id, name, description only |

Example creation body:

```json
{
  "title": "Checkout errors",
  "service": "checkout-api",
  "related_services": ["gateway"],
  "start_time": "2026-10-13T10:00:00Z",
  "end_time": "2026-10-13T10:15:00Z",
  "symptom": "5xx rate increased above baseline"
}
```

Timestamps must include a timezone. The end must follow the start and the window
must be at most six hours. Title/symptom must be nonblank; unknown body fields
are rejected. Services come from the lab allowlist. Related services are optional
and explicitly declared at creation; the incident freezes this service allowlist.
Without related services, only the primary incident service is permitted.
For replica symptoms use orders-api with pg-lag-probe and checkout-api declared
as related services, so lag/health gauges and successful writes remain in scope.

Evidence, timeline and signals accept optional `service`, `start_time`, `end_time`
query parameters. They may narrow the stored incident scope. Another service,
an earlier start, or a later end returns 403 SCOPE_POLICY_DENIED and creates a
sanitized scope_denials audit row. The reader independently reloads authoritative
incident bounds before selecting telemetry; it cannot trust a caller's enlarged
in-memory metadata. The API has no incident update/delete route in this phase.

Evidence bundles contain `source_id`, `window`, `query_params`, `snapshot_at`,
`truncated`, `available_counts`, `dropped_counts`, `retrieval_version`, and `items`. IDs are `ev_` plus the first 16 hexadecimal SHA-256
characters of `type|source_ref`. Source references identify telemetry rows
(trace sources include both trace_id and span_id). Every item carries type,
service, timestamp, source_ref, deterministic summary, payload, redactions.

The four signal queries and four scoped COUNT queries run with investigator_ro
in one repeatable-read transaction. Each signal fetches at most 50 candidates.
Relevance tiers are runtime event names (die/start/restart/deploy), a fixed list
of rule-supporting metric names, ERROR/FATAL/WARN/WARNING severity, then the rest.
Traces inherit an error tier only from a linked, scoped log with that severity;
span status is never a ranking input. Neither metric values nor status labels,
scenario IDs, hidden causal labels, or ground-truth tables affect ranking.

Both SQL and the final global cap break ties by timestamp then source_ref.
The evidence response preserves relevance order; the timeline remains chronological.
`available_counts` and `dropped_counts` report exact counts by event/metric/log/trace,
including rows excluded by per-source candidate limits. `truncated` is true when
the sum of dropped counts is positive. Counts are frozen with the snapshot.
The policy version is part of the cache key: existing immutable snapshots remain
stored, and relevance-v1 gets a separate snapshot without overwriting old evidence.

The first retrieval for a normalized incident/service/window scope is persisted
atomically under an advisory lock. Repeated requests return that exact snapshot,
including after late telemetry arrives; a narrower scope gets its own snapshot.
Evidence objects are deeply immutable; SQL triggers reject UPDATE, DELETE and
TRUNCATE on evidence and bundles. Corrections require a new versioned source
reference, never rewriting a saved observation.

All errors use this envelope, including invalid UUIDs, invalid bodies, unknown
routes and policy denials:

```json
{"error":{"code":"NOT_FOUND","message":"Incident not found","retryable":false,"request_id":"..."}}
```

`X-Request-ID` appears on every response. A supplied ID must contain 1–64 ASCII
letters/digits/dots/underscores/hyphens; otherwise the API generates a fresh ID.
Validation messages omit submitted values and driver details. Stable codes
include VALIDATION_ERROR (422), NOT_FOUND (404), SCOPE_POLICY_DENIED (403),
EVIDENCE_QUERY_TIMEOUT (503, retryable), and INTERNAL_ERROR (500).

The public catalog does not query ground_truth. Its static descriptors deliberately
have no import dependency on the chaos scenario definitions or hidden labels.
The API's reader and writer identities both lack ground_truth schema access.
