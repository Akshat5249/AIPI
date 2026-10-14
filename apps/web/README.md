# AIPI dashboard

Run `npm run dev` from this directory with Node 25, or use `make up` at the repo
root. Host Vite proxies `/api` to http://127.0.0.1:8000; Compose sets
API_PROXY_TARGET=http://api:8000. No model/DB credential belongs in this app.

Hash routes: `#/incidents`, `#/incidents/{id}`, `#/evaluations`. Create a positive
incident window up to six hours and explicitly select related services. Start an
investigation and inspect Timeline, Evidence, Hypotheses, Report or Agent Trace.
Click a citation to inspect its scoped payload/redactions; outside-bundle IDs are
fetched individually. Export Markdown downloads the stored report.

Agent Trace consumes SSE with Last-Event-ID resumption and duplicate suppression.
Evaluation can replay a saved golden or score a completed live incident using the
run ID printed by the host chaos command. Truth is disclosed only by the scorer's
terminal evaluation endpoint after scoring; other routes/components never request it.

`npm test` runs Vitest + React Testing Library. `npm run build` checks TypeScript
and builds the production bundle; `npm run lint` runs ESLint.
