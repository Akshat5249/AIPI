#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$PGDATA"
chmod 700 "$PGDATA"
chown postgres:postgres "$PGDATA"
if [ ! -s "$PGDATA/PG_VERSION" ]; then
  export PGPASSWORD="$REPLICATION_PASSWORD"
  until gosu postgres pg_basebackup -h postgres-primary -U replicator -D "$PGDATA" -Fp -Xs -P -R; do
    # Retry only an uninitialized basebackup destination.
    find "$PGDATA" -mindepth 1 -delete
    sleep 2
  done
  unset PGPASSWORD
fi
exec /usr/local/bin/docker-entrypoint.sh postgres -c hot_standby=on
