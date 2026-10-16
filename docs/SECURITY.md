# Security and threat model

The local lab binds published ports to loopback. The MVP has no authentication;
production authentication/RBAC is deferred. No remediation is implemented.

`event-watcher` is **lab-only** and runs as root with the Docker socket mounted
read-only. A read-only mount does not make the Docker API read-only: socket access
can control the daemon. Its code only uses `_ping` and filtered event reads. Never
expose this service to an untrusted network or use it against production Docker.

Credentials are randomly generated into ignored `.env` (mode 0600). The committed
`.env.example` contains placeholders. `postgres` credentials are only supplied to
PostgreSQL and the one-shot migration container. API ingestion uses
`telemetry_writer`; its telemetry and artifact grants are described below. Investigation
credentials are `investigator_ro` (SELECT and pg_monitor, default read-only).
`ground_truth` is owned by `chaos_admin`; PUBLIC and the API roles have no access.
The demo services have separate `app_rw` and `app_ro` roles for orders.

Collector sends JSON over the internal Compose network; API validates and redacts
before inserting. No raw validation errors or input payloads are returned to clients.
Model context is redacted again, with escaped untrusted-data boundaries.

Chaos scenario templates are static source files; runtime causal labels and injection
records are written only to `ground_truth.scenarios` and `ground_truth.chaos_runs`.
The host runner uses `chaos_admin`, never an API identity. Migration 0002 grants
that role EXECUTE on the two replay control functions and their status functions;
it receives no superuser membership. Investigation and demo roles cannot pause
or resume replay. Each run holds a PostgreSQL advisory lock so concurrent fault
injections are refused. Operator output contains observed signals and recovery
checks, with no expected root-cause label. Workload requests carry ordinary order
fields and no scenario tags or injection timestamps.

Evidence SELECTs use only investigator_ro and four hard-coded telemetry sources.
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


Investigation tools expose six fixed typed read-only operations. The runner binds its owning
incident, reloads the stored scope and logs denied attempts; no model-selected
SQL, shell or remediation operation exists. SQL sources require investigator_ro
on both primary and replica. The supervisor's telemetry_writer persists audits,
provenance and artifacts, with UPDATE grants restricted to investigation status,
latency and usage fields; artifacts remain immutable. Tools never receive a
query writer, migration administrator or ground-truth credential.

The model proposes falsifiable hypotheses only. Deterministic verification and
the fixed formula decide rank/confidence. Every report/Markdown citation must
resolve within scoped evidence, including witnesses outside the cap. Invalid
reports receive one repair, then fail. Recommendations are non-mutating checks,
require human approval and have executed=false. Poisoned logs cannot change the
mock conclusion; separate synthetic truth files are read only by the scorer.
Background jobs run in one API process; interrupted jobs fail on startup. This
MVP has no authentication and should remain a loopback-only local lab.


Ground-truth SELECTs are confined to the separate scorer container and scorer
CLI/oracle module. The incident API receives a scorer URL, with no truth credential
or truth fixture files. Golden graph replay runs in a credential-free subprocess;
its allowlisted environment excludes scorer/DB/model secrets. Only observable
scoped JSON goes to that process. Evaluation job/scorecard responses contain metric
scores and experiment metadata, not protected expected causal labels. A separate
post-score disclosure route is described below. The scorer
uses default_transaction_read_only even for its chaos_admin-class truth identity;
its artifact writer is the existing restricted telemetry_writer. Evaluation
records have explicit FK/insertion/status-update grants; investigator_ro can read
scores but cannot write them or access protected truth. The scorer has no public
host port or Docker socket. Host-only recording injects fixed bounded lab faults,
never a model/tool action. No .env regeneration is required.

## Dashboard boundary

Only the Evaluation page may request the terminal evaluation truth disclosure.
The scorer refuses disclosure before scoring; job/scorecard responses remain
score-only. Neither API nor web receives the truth DB credential. Incident and
investigation components select known fields, strip protected fields from payload
JSON and escape telemetry as React text. No dangerouslySetInnerHTML or external
telemetry-driven links exist. Evidence IDs resolve only through the owning incident.
The web /api proxy does not change host API exposure: 127.0.0.1:8000 remains the
only API host binding. The exact read-only banner appears on every page, and all
recommendations remain approval-required and not executed.


| Threat | Implemented boundary | Remaining limit |
|---|---|---|
| Model requests a write/shell action | Six fixed typed read-only tools; registry/DB grant tests; no execution endpoint | Host chaos/maintenance utilities intentionally mutate the lab under operator control |
| Scope widening or cross-incident citation | Reload authoritative scope; parameterized SELECTs; audited denials; by-ID provenance | No user authentication/tenant isolation |
| Prompt injection in telemetry/runbooks | Delimited escaped data; redaction; mock poison regression; schema/repair gates | Paid-model robustness unmeasured; adapters unimplemented |
| Hidden label leakage to agents | Separate scorer container/credential, separate truth files, credential-free replay subprocess | Operator can read source fixtures; terminal Evaluation page intentionally discloses scored truth |
| Fabricated claim/value/citation | Pure ID/quotation/claim vocabulary gate; negative CLI tests | Bounded semantic predicates, not general natural-language entailment |
| Credential disclosure | Generated ignored 0600 .env; safe errors; pre-store/context redaction; full-history scanner | Local host/Docker administrator remains trusted |
| Docker socket abuse | Lab-only watcher, project-filtered event reads, read-only socket mount | Socket still enables Docker control; root watcher is not a sandbox |
| Unauthenticated network access | Loopback host publications; scorer unexposed; same-origin web proxy | No TLS/auth/RBAC; internal ingest has no auth; not a production service |
| Process failure / telemetry accumulation | Persisted artifacts, interrupted jobs marked failed; bounded job deadlines | Single process, no queue, no automatic telemetry retention |

Human approval is a report requirement/label, not an implemented approval/execution
workflow. No recommendation can be executed through the product. Future production
work would need authentication/RBAC, credential lifecycle, retention, durable jobs
and a socket-free telemetry source; none is claimed by this release.
