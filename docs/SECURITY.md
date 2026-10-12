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
