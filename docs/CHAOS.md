# Local chaos lab

Start the lab and seeded traffic before either scenario:

```sh
make up
make seed-traffic
make chaos-kill
make chaos-lag
```

Run scenarios sequentially. They validate the fixed `aipi` Compose project,
healthy demo services, steady successful traffic, and primary/standby roles.
A session advisory lock rejects overlapping runs. Both commands print validated
JSON observations and exit nonzero on a failed verification or recovery.

SCN-001 kills the verified checkout container with SIGKILL, generates bounded
foreground traffic, recovers checkout, and checks stored die(137) followed by
start, gateway error logs, failed spans, and a rising gateway 503 counter. It
observes restart behavior for eight seconds and explicitly starts the stopped
container if needed. The restart policy remains `unless-stopped`.

SCN-002 pauses WAL replay on the standby with the restricted `chaos_admin` role,
waits for actual paused state, writes ten orders to the healthy primary, observes
a stale replica read, and holds the pause for ten seconds. Verification requires
at least three lag samples, a rise of two seconds, a maximum of four seconds,
positive WAL backlog, paused telemetry, and healthy primary samples. Recovery
resumes replay, verifies the newly written order is visible, and waits for fresh
unpaused/low-lag metrics.

The runner attempts recovery in `finally`, including injection errors and
interrupts. Failed preconditions cause no injection. A process forcibly killed
outside Python's control cannot execute cleanup: restore checkout with
`docker compose --env-file .env -f infra/docker/compose.yml start checkout-api`,
or use the host `Lab.connect('chaos_admin', replica=True)` connection to execute
`SELECT pg_wal_replay_resume()` after confirming the standby. Re-run the normal
health gate before further chaos.

Scenario contracts are in `chaos/scenarios/scenario.schema.json`. Runtime labels,
scenario snapshots, run timestamps, targets and recovery status live exclusively
in the restricted ground_truth schema. The CLI emits observed checks only.
Docker-marked integration tests execute both scenarios against the real lab;
unit tests check failure recovery, overlap refusal, event ordering and contracts.
