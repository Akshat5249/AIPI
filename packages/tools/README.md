# Read-only tools

The immutable registry contains six typed operations: logs_query, metric_query,
trace_lookup, runtime_events_query, db_replication_status, and runbook_search.
SQLBackend uses investigator_ro and fixed SELECTs. FixtureBackend provides the
same filters for offline tests. Every call reloads the owning incident boundary;
ScopePolicy rejects widening and foreign incidents. Results cap at 50, metric
samples compress into series summaries, and runbooks use service-tagged BM25.

ToolRunner emits audit records/spans, uses at most two timeout retries and marks
unavailable evidence explicitly. The supervisor implements the audit port; the
query backend never holds a writer. Current replication views are timestamped
observations and are excluded from completed historical windows.
