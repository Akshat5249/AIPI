# AI Production Incident Investigator

An evidence-grounded, read-only incident investigation platform under construction.
M0+M1 implements the observable lab and validated telemetry store. M2 adds
verified service-kill and replica-lag scenarios. M3 adds scoped incidents, immutable
evidence/timelines and deterministic correlators. M4 adds a six-node LangGraph
with scoped read-only tools, deterministic mock reasoning and evidence-linked
reports. M5 adds isolated scoring, golden/recorded replay and repeated live evaluation.
M6 adds the incident dashboard, scoped evidence drawer, resumable agent trace,
Markdown export and post-score evaluation view. See [PROGRESS.md](PROGRESS.md).

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
make seed-traffic  # required seeded background workload for chaos gates
make chaos-kill    # real SIGKILL, telemetry checks, checkout recovery
make chaos-lag     # standby replay pause, lag/primary checks, replay recovery
make investigate ID=<incident_uuid>  # background mock investigation + report
make eval           # golden metrics + pure hallucination gate + scorecards
make record-golden  # three live repeats per scenario, real fixtures and variance
make test          # units, synthetic goldens, live chaos/reports, web tests
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

See [chaos operations and recovery](docs/CHAOS.md) for scenario details.

See [Incident Core API](docs/API.md) for creation, scoped evidence, and error contracts.

See [evaluation metrics, replay and recording](docs/EVALUATION.md).

Dashboard: open http://localhost:5173, create an incident with the observed service
and time window, then start its read-only investigation. The detail tabs expose
timeline, evidence, ranked hypotheses, report and live execution. Citations outside
the 50-item display bundle still resolve within the incident. Evaluation can replay
a saved golden or score the completed live incident with the recovered chaos run
ID. Ground truth is revealed only after scoring. See [dashboard notes](apps/web/README.md)
and the [measured M6 UI gate](docs/verification/m6/README.md).
