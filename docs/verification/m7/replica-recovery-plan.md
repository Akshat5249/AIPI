# Retained replica recovery plan — not executed

The retained main project is stopped. Its replica reports:

```text
requested WAL segment 0000000100000004000000F5 has already been removed
pg_stat_wal_receiver: no rows
observed replay backlog: 89,969,640 bytes; replay age approximately 1942 seconds
```

The missing segment cannot be obtained by waiting or resuming replay. The primary
is the authoritative copy. The original .env, primary and evaluation-results
volumes have not been regenerated/reset/removed. PostgreSQL now uses init:true;
a live regression proved both SQL sessions survived orphan-client exit 2.

Read-only size checks: aipi_primary-data 8.2G, aipi_replica-data 8.1G; host Data
volume had 4.0 GiB free. A second full replica alongside the old one needs more
space than is currently free. Replacing only the derivative replica avoids that
extra simultaneous copy, but explicitly conflicts with the user's current
instruction not to touch existing volumes.

Required authorization: reseed **aipi_replica-data only** from the retained primary.
No other volume and no .env would be deleted or regenerated. Proposed sequence:

1. Keep the original environment and all primary/evaluation data. Verify the exact
   named volumes and that the primary starts healthy with init enabled.
2. Remove only the stopped postgres-replica container if present. With explicit
   approval, remove only the old aipi_replica-data volume (not make down --volumes
   and not a prune).
3. Start postgres-replica so its existing entrypoint creates a new base backup
   from postgres-primary using the unchanged replication credential. Allow up to
   15 minutes for the approximately 8.2G copy before the normal health gate.
4. Require standby=true, replay unpaused, receiver streaming, healthy primary,
   backlog caught up and a new order visible on the replica. Start remaining
   services/traffic and rerun both consecutive full make test gates and lint.
5. Verify original .env checksum and retained primary/evaluation volume identities.
   Record the separately authorized recovery verification; do not push.

The requested M7 fresh-clone gate uses a separate project and leaves all original
volumes intact. Retained-replica recovery is a separate operation requiring new
authorization; it is not an investigation recommendation or an agent-executable
tool. No reseed or volume removal has been performed.
