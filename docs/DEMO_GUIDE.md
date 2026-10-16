# Five-minute demo and discussion guide

After README setup, run `make demo`. A warm run builds/starts health checks,
starts seeded traffic, gathers 30 seconds of baseline, kills checkout-api, verifies
die exit 137 → start and correlated errors, then creates the scoped incident,
investigates and evaluates the recovered window. It also runs the golden suite.
Initial dependency downloads/builds are additional time. Use the printed Incident
ID, UI URL and Evaluation URL; no manual SQL edits are needed.

In the dashboard:

1. Read the banner and the separated Facts / Hypotheses / Recommendations report.
2. Compare the root cause with a lower-ranked timeout/dependency hypothesis.
   Open FOR and AGAINST chips, including an outside-bundle citation.
3. Filter Evidence by gateway/log, inspect payload/redactions and the runtime
   die/start events. Timeline provides the chronological view.
4. Inspect Agent Trace's six nodes/tool calls, actual latency and zero mock tokens/
   cost. Export Markdown from Report.
5. Open Evaluation; scores come from the scorer. The protected expected label
   appears here only after scoring. It was never given to the investigation.

To demonstrate replica lag separately, note a UTC start 30 seconds before
`make chaos-lag`, and a UTC end after verified recovery. Copy the command's run_id.
Create an incident with service **orders-api**, related services **pg-lag-probe**
and **checkout-api**, that start/end and a symptom describing stale reads/timeouts.
Start investigation. Inspect lag/replay-paused summaries and a stale-read log or
timeout trace. Compare the lower-ranked primary-outage hypothesis with healthy
primary AGAINST evidence. In Evaluation choose recorded live mode, incident ID,
SCN-002 and the recovered chaos run ID. Do not invent or read truth from SQL.

make test and make record-golden inject faults too; serialize them with demos.
make down retains lab volumes. For isolated clones keep the README port/project
exports active throughout setup, chaos, tests and teardown.

Interview talking points:

- Deterministic full-scope correlation is independent of the 50-item presentation
  cap. Summary IDs version their actual sample membership; raw rule witnesses
  remain resolvable. Show a citation rather than merely quoting a confidence.
- Separate observable symptoms from expected labels: the scorer has its own
  credential/process and the graph has no oracle import/connection.
- Ranking uses the fixed coverage/proximity/retrieval/check formula and explicit
  contradiction penalty, not a model's self-assigned confidence.
- Show a negative gate test for fabricated values/unknown IDs. Explain the bounded
  supported claim vocabulary rather than suggesting general hallucination detection.
- State the measurement limits: deterministic mock, two curated faults, n=3 each,
  no real-LLM accuracy, no auth/RBAC and no GitHub CI run yet.

Resume bullets (accurate scope; do not describe these as production/LLM results):

- Built an OTel/PostgreSQL incident lab with scoped immutable evidence, six read-only
  tools and a Pydantic-validated six-node LangGraph investigation/report workflow.
- Implemented isolated scorer-backed replay, citation/value hallucination gates
  and JSON/Markdown scorecards; measured six recovered mock runs across two faults
  with 100% Top-1 and 2.12955 s median investigation latency.
- Built a React/TypeScript dashboard with evidence provenance, FOR/AGAINST review,
  resumable SSE and post-score evaluation disclosure; verified a real local fault
  from incident creation to evaluation without manual database edits.
