# M6 live dashboard gate

Verified on Apple Silicon with Docker Desktop, Node 25, Python 3.12 and the mock
investigator on 2026-10-14. No manual database edits or .env regeneration.

After make up and seed-traffic, make chaos-kill recovered run
fffb2290-6bb3-4a6c-a3cf-86bde8019dd4 with die (exit 137) → start. The browser created
incident 57bccb03-2f6b-4997-b7dc-f2e8a381d716 for 16:03:25–16:04:14 UTC with
checkout-api and gateway in scope. It started investigation
6bf83863-05aa-4f74-9721-f2d41b98cbf3 and displayed the streamed execution, ranked
hypotheses, report and scoped outside-bundle payload. It exported the stored Markdown.

The recorded replay was submitted in the Evaluation page and completed as
177f9e21-e2fc-4d86-ae37-e159011765be. Top-1/Top-3/precision/coverage/contradiction
handling are 100%, unsupported and critical unsupported claims zero. Investigation
latency: 1.71952 s; 8 audited tool calls, 0 tokens and $0 estimated cost. The report
cites 333 scoped IDs, with 313 outside the 50-item display bundle. The scorer resolved
all citations. Ground truth appeared only after scoring through its dedicated route;
the normal evaluation job remains score-only.

- [Window captured around the recovered fault](gate-window.json)
- [Investigation metadata, all outside IDs and export digest](investigation-summary.json)
- [Actual scorecard](evaluation.json)
- [Markdown downloaded by the UI](exported-report.md)

Screenshots:

- [Incidents](01-incidents.jpg)
- [Timeline](02-timeline.jpg)
- [Full agent execution](03-agent-trace-full.jpg)
- [Hypotheses](04-hypotheses.jpg)
- [Outside-bundle evidence](05-outside-bundle.jpg)
- [Filtered gateway logs](06-evidence-logs.jpg)
- [Report sections](07-report.jpg)
- [Evaluation and post-score truth](08-evaluation.jpg)

Screenshots use the browser's actual desktop/compact viewport; no viewport override
was applied. A native-date regression caught during browser validation was fixed
before the real gate. The unrelated test incident 4b8442fe-19ff-4461-a3a8-f40a13868ed0
is excluded from these results. Reversed and >6-hour windows were rejected in the
corrected UI. This is a local curated mock gate; paid providers and GitHub-hosted CI
were not exercised.

Final checks: the full make test run passed 128 Python + 25 web tests (all 22
Docker tests ran). A subsequent trace presentation/accessibility refinement passed
the full updated frontend suite of 26 tests, TypeScript, ESLint, production build,
healthy container and real trace inspection. The final trace screenshot includes
visible tool identities; per-event duration appears only if supplied by the API.
Overall latency/token/cost values are the real investigation metadata above.
