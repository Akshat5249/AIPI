# Five-minute demo guide

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

## What to verify

- Service kill: die with exit 137 followed by start, gateway errors and a
  termination hypothesis supported by those observations.
- Replica pause: increasing lag and replay-paused evidence, stale-read or timeout
  evidence, and healthy-primary observations AGAINST the primary-outage hypothesis.
- Both: every cited ID opens scoped evidence, recommendations remain unexecuted,
  and the scorer reports unsupported claims rather than hiding a failed gate.

See the [captured dashboard](images/README.md) and [measured mock results](results/README.md).
