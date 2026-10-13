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
| GET | /api/incidents/{id}/evidence/{evidence_id} | One frozen bundle item or full-scope signal citation, subject to the same scope |
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
`truncated`, `raw_counts`, `available_counts`, `dropped_counts`, `retrieval_version`,
`correlation_source` (full_scope), `signals`, `capped_rules`, and `items` (at most 50).
IDs are `ev_` plus the first 16 hexadecimal SHA-256 characters of `type|source_ref`.
Each item carries type, service, timestamp, source_ref, summary, payload and redactions.

Four parameterized telemetry SELECTs run with investigator_ro in one repeatable-read
transaction over the full authorized scope. Correlation runs **before** summarization
and selection; `/signals` returns these frozen full-scope results. `capped_rules`
only diagnoses which rules would fire on the selected items, and is never the
source for `/signals`. All cited observations are persisted, including raw samples
or logs beyond the display cap. Retrieve these through the evidence-by-ID endpoint;
it permits only a displayed item or citation from this exact frozen scope.

Metric samples become one summary per service/name/canonical-label series (excluding
the reserved histogram sample-data key from labels), containing
`first`, `last`, `min`, `max`, `sample_count`, first/last timestamps/source references
and paused/healthy `transitions` with timestamp/from/to. The source reference starts
`telemetry_metrics:series:` and hashes series identity plus ordered scoped sample
references. Same samples and scope produce identical IDs on replay; changed sample
membership requires a new source version. Conflicting primary health is preserved.

Inside the 50-item cap, reserve up to 10 severe logs and 5 error/slow traces, then
prioritize runtime lifecycle events and fixed rule-metric summaries in remaining
space. Fill with additional severe/error/slow observations, then ordinary telemetry.
Severity order is FATAL, ERROR, WARN/WARNING, ordinary; a trace inherits linked scoped
log severity or its error status/slow duration (>=250 ms). Ties use timestamp then
source_ref. Selection uses telemetry features only, without scenario/ground-truth
access. Metric values and causal labels do not rank candidates. Floors are bounded
by availability; if protected observations cannot all fit, dropped counts expose it.

`raw_counts` counts source rows, `available_counts` counts post-summary candidates,
and `dropped_counts` counts candidates omitted by type. Collapsing metric samples is
summarization rather than truncation. `truncated` is true when dropped counts sum
to a positive number. Metadata is frozen with the snapshot. The series-floors-v2
cache namespace preserves previous immutable snapshots and original raw-source IDs.
The evidence response preserves selection order; the timeline stays chronological.

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
