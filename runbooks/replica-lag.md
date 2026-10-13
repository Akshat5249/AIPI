# Replica replay lag investigation
<!-- services: orders-api,pg-lag-probe,checkout-api,postgres-replica -->

## Compare lag and replay
Inspect replica_lag_seconds, replica_lag_bytes and replica_replay_paused in the
same time window. Paused replay with increasing WAL backlog supports replication
lag. Review transitions and peak values; the last recovered sample can hide an
incident. Read streaming replication views only when their observation time falls
within the incident window. Historical metrics remain the historical evidence.

## Challenge primary outage
Compare primary_healthy gauges and successful primary writes with stale replica
read logs and timeout traces. Healthy primary evidence contradicts a primary
outage; application retries alone do not prove it. Preserve contradictory evidence.

## Next checks
Review replica replay state, WAL backlog and replica-read routing with the owner.
Recommend human review of replay configuration. Do not pause or resume replay,
change database settings, or execute remediation from this investigation.
