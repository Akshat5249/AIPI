# Local deployment and verification

Use the fresh-clone commands and optional isolated port exports in [README](../README.md).
Python is locked to 3.12, npm dependencies are lockfile-driven, and uv sync uses
--frozen. Dockerfiles use Python 3.12 slim bookworm and Node 25 bookworm slim;
PostgreSQL is official postgres:16. Native arm64 images are used on Apple Silicon;
CI is an Ubuntu x86 runner definition. No production deployment is supplied.

make setup-env creates .env only if absent (0600, generated local role passwords).
make setup installs dependencies and preserves existing credentials. make up
builds api/demo/migration, separate scorer and web targets, runs Alembic, waits
for Compose health and checks API/gateway/web/Collector from the host. Collector
uses HTTP health extension / because its image has no shell. Then make seed-traffic
starts the optional workload profile. Seed 42 and default rate 1 are configurable.

The public ports bind to 127.0.0.1. Scorer has no host port. Web proxies /api within
Compose; no broad CORS rule is needed. For local npm development, Vite defaults
to 127.0.0.1:8000; set API_PROXY_TARGET for a different API port. The dev server is
used for the local lab, not represented as a hardened production static server.

COMPOSE_PROJECT_NAME defaults to aipi. Optional process overrides AIPI_DB_PORT,
AIPI_REPLICA_PORT, AIPI_API_PORT, AIPI_GATEWAY_PORT, AIPI_WEB_PORT,
AIPI_COLLECTOR_PORT and AIPI_COLLECTOR_HEALTH_PORT isolate another checkout.
Project names for host chaos must match aipi or aipi- followed by lowercase lab
characters. Lab container inspection verifies project + service before killing.
The watcher receives the project and filters only its lifecycle events.

Named volumes hold primary-data, replica-data and evaluation-results, all prefixed
by the Compose project. make down stops/removes project containers/network and
**retains volumes**. Never regenerate an existing .env against old volumes.
For a disposable isolated clone only, after verification, remove only that
project's volumes if desired:

```sh
# Keep the isolated exports active; never run this against your retained lab.
docker compose --env-file .env -f infra/docker/compose.yml --profile traffic down --volumes
```

Run make test with lab and traffic healthy. Docker-unavailable tests skip; a broken
reachable lab is an error. Tests inject both faults serially; do not run them
concurrently with make demo, chaos commands or record-golden. make lint checks
Python format/lint/strict types and frontend ESLint/types. make build-web compiles
Vite. make eval runs recorded golden + poison gates with mock, including pure
citation/quotation checks. Negative CLI tests require nonzero exit for unknown
ID, fabricated value and wrong root cause.

CI installs locked dependencies, scans full git history, runs lint/types, offline
unit/schema/golden tests and hallucination gate, builds frontend and all Compose
images, waits for health, starts traffic, runs full live integration + frontend
checks and cleans containers on every outcome. Publication is an explicit no-op.
**GitHub CI has not run.** Local workflow validation:

```sh
docker run --rm -v "$PWD:/repo:ro" -w /repo rhysd/actionlint:1.7.7 -color
docker run --rm -v "$PWD:/repo:ro" ghcr.io/gitleaks/gitleaks:v8.24.2 \
  git /repo --redact --no-banner --log-opts=--all
```

Full-history scanning uses --all, including reachable prior commits. A separate
working-tree scan can supplement it; it does not substitute for history. .gitignore
excludes .env variants (except .env.example), .venv, node_modules and caches.
LICENSE is MIT. Recorded fixtures intentionally retain complete raw scoped
witnesses for reproducible out-of-bundle citation validation. The two largest
files are tests/fixtures/scn-001.json (7,523,593 bytes) and poisoned-log.json
(7,524,096 bytes), intentionally reviewable without decompression. Generated
scorecards and debug logs stay ignored. Full-history scans do not rewrite history.

Troubleshooting: inspect `docker compose --env-file .env -f
infra/docker/compose.yml ps` and targeted logs. A 5432 authentication error after
editing .env usually indicates volume/password mismatch; restore the matching
credentials instead of resetting valuable data. Wait for PostgreSQL automatic
crash recovery before retrying tests. A failed scenario always attempts recovery;
confirm standby replay is resumed using the SCN-002 recovery procedure in CHAOS.md.
App/scorer restarts mark interrupted in-process jobs failed; resubmit after health.
If replay times out, integration diagnostics print job ID/status/elapsed time with
a 90-second deadline. No blanket retries hide a failed gate.


Both PostgreSQL services use Compose init:true and a 60-second stop grace. The
init process reaps orphaned health-check clients, preventing their abnormal exits
from being mistaken for PostgreSQL worker crashes. This mechanism was reproduced
in disposable tmpfs containers; see [ADR-022](DECISIONS.md#adr-022--postgresql-init-reaping-and-bounded-wal-retention). A live
regression holds an existing SQL connection across a failing orphan client.


The primary retains at least 512 MB of recent WAL for bounded lab interruptions.
This is not an archive or an indefinite offline-replica guarantee. If the replica
reports "requested WAL segment ... has already been removed", waiting or replay
resume cannot supply it; it needs a new base backup from the primary. A reseed
writes/replaces replica data and must respect operator constraints on retained
volumes. Preserve primary data and matching credentials; take a backup and
explicitly identify the derivative replica volume before any operator-approved
reseed. Do not use a blanket volume prune. A new isolated project can validate
the software without changing retained data.
