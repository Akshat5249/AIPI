Deployment, DevOps & Observability

Local stack, environments, CI/CD, and monitoring of the investigator itself

AI Production Incident Investigator

| Document ID | AIPI-11 |
| --- | --- |
| Version | 1.0 |
| Status | Implementation baseline |
| Primary audience | Developer / reviewer / interviewer |

# 1. Local Deployment

- Docker Compose: demo services, PostgreSQL primary/replica lab, OTel Collector, backend, frontend.
- Optional model provider can be cloud API or local model adapter.
- Seed command creates normal traffic and reproducible incidents.
# 2. Environment Variables

| Variable | Purpose |
| --- | --- |
| DATABASE_URL | Application metadata database |
| TELEMETRY_DATABASE_URL | Telemetry/evidence store |
| OTEL_EXPORTER_OTLP_ENDPOINT | Collector endpoint |
| MODEL_PROVIDER | Selected LLM adapter |
| MODEL_NAME | Model identifier |
| MODEL_API_KEY | Provider secret; never commit |
| APP_ENV | local/test/demo/prod |

# 3. CI/CD

1. Install dependencies and cache packages.
1. Lint and type-check Python/TypeScript.
1. Run unit + integration + golden agent tests.
1. Build backend/frontend container images.
1. Run Compose smoke test.
1. Publish artifacts/deploy only if quality gates pass.
# 4. Project Observability

- Trace each investigation and nested agent/tool calls with OpenTelemetry.
- Track latency, token usage, tool failures, evidence count, confidence and evaluation score.
- Create dashboards for investigation success rate and failure categories.
# 5. Production Evolution

- Replace local telemetry store with scalable log/trace backends only when needed.
- Add authentication/RBAC and tenant isolation.
- Introduce queue/worker model for concurrent investigations.
- Add approved remediation workflows after read-only accuracy is proven.
