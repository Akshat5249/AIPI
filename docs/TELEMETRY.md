# Telemetry and evidence

Demo service resources include service.name, deployment.environment,
service.version and host.name. Application logs carry trace_id/span_id and
structured attributes. Gateway requests produce client/server/SQL spans and
request counter/duration measurements; replica reads expose stale-read retry
symptoms. The Collector forwards JSON to POST /internal/otlp/v1/logs, metrics and
traces. These ingest routes are operational/internal, unauthenticated in this lab.

Storage is defined in packages/telemetry and Alembic migrations:

| Table | Identity / scope time | Main payload |
|---|---|---|
| telemetry_logs | id / ts | service, severity, body, trace/span IDs, attributes, redactions |
| telemetry_metrics | id / ts | service, metric_name, value, labels, redactions |
| telemetry_spans | trace_id + span_id / start_ts | service, operation, status, duration_ms, attributes, redactions |
| telemetry_events | id / ts | service, event_domain, event_name, attributes, redactions |

The normalizer makes deterministic source IDs; ON CONFLICT DO NOTHING handles
Collector retries. Redaction runs before persistence and again before model
context. It covers sensitive keys/values, bearer tokens, connection credentials,
AWS-style access keys and optionally email addresses; markers store rule/field,
never the secret value. This is a tested heuristic, not a DLP guarantee.

The watcher emits runtime die/start/restart observations with container identity,
source event timestamp and exit code. These are ordinary observable telemetry,
not injection labels. The two-second lag probe emits replica_lag_seconds,
replica_lag_bytes, replica_replay_paused and primary_healthy. Seconds are zero when
byte backlog is zero; otherwise they use time since last replay. A WARN records
delayed replay. Current DB view observations cannot be cited for historical windows.

Canonical evidence contains evidence_id, type (log/metric/trace/event/runbook),
service, timestamp, source_ref, summary, payload and redactions. The ID is exactly
`ev_` + sha256(type + "|" + source_ref)[:16]. Payloads freeze observations. Runbook
chunks use content-versioned source references and service tags.

Correlation runs on the **full scoped snapshot**, independent of the display cap.
Metric samples become one summary per service/name/canonical-label series:
first/last/min/max, count, timestamps/source references and paused/healthy
transitions. Histogram sample-data labels are excluded from series identity.
Summary references hash identity plus ordered scoped sample references; the same
samples yield the same IDs. See ADR-016 for selection details.

The cap is 50 with up to 10 severe logs and 5 error/slow traces reserved; lifecycle
events and fixed rule-supporting series have priority in remaining capacity.
Ties use timestamp then source_ref, with no scenario/truth ranking features.
raw_counts counts source rows, available_counts summary candidates, dropped_counts
omitted candidates by type; summarization is not a dropped sample. Overflow is
explicit. Every raw correlator witness remains accessible through scoped by-ID
lookup even when not displayed. First reads freeze snapshots; late arrivals do
not rewrite them. Timeline is chronological; bundle selection order is priority.

Synthetic integration sources now carry unique test_run markers and teardown
removes exactly inserted IDs plus their marker under an admin connection, even on
failure. The optional host maintenance command `uv run python -m
scripts.cleanup_legacy_synthetic` audits old test signatures; `--apply` removes
only matching legacy rows more than one day in the future. It is not retention
management and never deletes real traffic by an arbitrary time range.
