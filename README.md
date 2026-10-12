# AI Production Incident Investigator

An evidence-grounded, read-only incident investigation platform under construction.
M0+M1 implements the observable lab and validated telemetry store. Agents and
chaos scenarios are scheduled for later phases; see [PROGRESS.md](PROGRESS.md).

```text
traffic → gateway → checkout-api → PostgreSQL primary
                 → orders-api   → PostgreSQL replica
services → OTel Collector → internal API JSON ingest → telemetry tables
```

Requirements: Python 3.12, uv, Node 25, Docker Desktop with Compose v2. Images
support Apple Silicon natively. No LLM API key is needed.

```sh
make setup         # dependencies and generated private lab credentials
make up            # build, migrate, wait for health (ports 5432/5433/8000/8080/5173/4318/13133)
make seed-traffic  # optional seeded background workload
make test          # unit/component tests + running-lab integration + web tests
make lint
make down          # retain PostgreSQL volumes
```

Docker tests skip when the daemon is unavailable. If Docker is available, start
the lab before `make test`; a reachable daemon with a broken lab is a test failure.

Web: http://localhost:5173 · API schema: http://localhost:8000/docs

```sh
curl -X POST http://localhost:8080/checkout -H 'Content-Type: application/json' \
  -d '{"product":"book","quantity":1}'
```

The gate test checks that this path persists a checkout log and spans sharing a
trace ID across gateway, checkout and PostgreSQL, plus request metrics. It also
checks replica reads, role isolation, ingestion retries, and redaction in storage.

Passwords in `.env` must match existing volumes: `make down` preserves them.
Changing passwords requires coordinated database role updates or a deliberate
lab reset. Never commit `.env`. See [security notes](docs/SECURITY.md).
