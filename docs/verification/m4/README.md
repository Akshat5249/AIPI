# M4 live report verification

Real Docker lab observations captured by `test_live_mock_investigation` on 2026-10-14 (IST).
The test re-ran both scenarios, confirmed recovery and stable bundle IDs, and resolved every report citation through the scoped HTTP evidence-by-ID endpoint. These are verification artifacts; synthetic golden fixtures remain under tests/fixtures/.

| Scenario | Incident | Investigation | Latency | Cited IDs | Outside 50 | Outside rule witnesses |
|---|---|---|---|---|---|---|
| SCN-001 | `36d8db4c-81d5-4f76-af55-4fbf58ec8f23` | `c87fd71c-70bc-40e1-b862-c04f99e4e3de` | 1.656 s | 372 | 353 | 352 |
| SCN-002 | `d1ac8743-02bf-46cd-9c8f-c3c689419e89` | `8c17d69d-29cb-495f-b572-9b08755ea3ab` | 0.547 s | 140 | 117 | 116 |

Both reports preserve FOR/AGAINST evidence and approval-required, unexecuted next checks. Each JSON file includes the complete `cited_outside_bundle` array, its `outside_rule_witnesses` subset, the structured report and all resolved cited evidence. One additional outside-bundle citation in each report is scoped runbook evidence.

- [SCN-001 report and complete outside-ID list](scn_001_service_kill.json)
- [SCN-002 report and complete outside-ID list](scn_002_replica_lag.json)

SCN-002 top hypothesis cites replica_lag_seconds (max 10.24426), replica_replay_paused (0→1→0 transitions), WAL backlog, a stale-read WARN log and a postgres.select_order timeout trace. Primary outage ranks third (0.20 versus replica lag 0.96), with primary_healthy=1 AGAINST evidence. SCN-001 cites checkout die(exit_code=137), start and gateway ERROR evidence.

All cited IDs were checked for incident ownership, allowlisted service and timestamps inside the incident window. Cross-incident lookup and widening were denied. SSE node/tool events, JSON snapshots and cursor validation were checked. Runtime fault labels were never supplied to the mock or API sources.
