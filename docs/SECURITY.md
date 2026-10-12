# Foundation security boundaries

The local lab binds published ports to loopback. The MVP has no authentication;
production authentication/RBAC is deferred. No remediation is implemented.

`event-watcher` is **lab-only** and runs as root with the Docker socket mounted
read-only. A read-only mount does not make the Docker API read-only: socket access
can control the daemon. Its code only uses `_ping` and filtered event reads. Never
expose this service to an untrusted network or use it against production Docker.

Credentials are randomly generated into ignored `.env` (mode 0600). The committed
`.env.example` contains placeholders. `postgres` credentials are only supplied to
PostgreSQL and the one-shot migration container. API ingestion uses
`telemetry_writer` with SELECT/INSERT on telemetry tables only. Investigation
credentials are `investigator_ro` (SELECT and pg_monitor, default read-only).
`ground_truth` is owned by `chaos_admin`; PUBLIC and the API roles have no access.
The demo services have separate `app_rw` and `app_ro` roles for orders.

Collector sends JSON over the internal Compose network; API validates and redacts
before inserting. No raw validation errors or input payloads are returned to clients.
Before future model calls, run the same redaction function again.

M2 scenario templates are static source files; runtime causal labels and injection
records are written only to `ground_truth.scenarios` and `ground_truth.chaos_runs`.
The host runner uses `chaos_admin`, never an API identity. Migration 0002 grants
that role EXECUTE on the two replay control functions and their status functions;
it receives no superuser membership. Investigation and demo roles cannot pause
or resume replay. Each run holds a PostgreSQL advisory lock so concurrent fault
injections are refused. Operator output contains observed signals and recovery
checks, with no expected root-cause label. Workload requests carry ordinary order
fields and no scenario tags or injection timestamps.

M3 evidence SELECTs use only investigator_ro and four hard-coded telemetry sources.
ScopePolicy checks an incident's immutable service allowlist and time bounds;
the reader reloads those bounds from public.incidents, independently of the API.
Denied API queries are audited in scope_denials. Every scope snapshot is capped
at 50 and frozen on first read; evidence and bundle tables have mutation-blocking
triggers. Public scenario descriptors are static: the API never connects to or
queries ground_truth. Request IDs are validated and errors omit submitted secrets
and database driver details.

The existing telemetry_writer identity additionally receives SELECT/INSERT on
incidents, evidence, evidence_bundles and scope_denials for API bookkeeping. It
cannot update/delete them, control WAL replay, or read ground truth. This explicit
reuse avoids adding or regenerating any lab credential. Persistence remains in
the API layer; the retrieval package contains SELECTs only.
