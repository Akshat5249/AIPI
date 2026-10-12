#!/usr/bin/env bash
set -euo pipefail
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v replication_password="$REPLICATION_PASSWORD" -v app_rw_password="$APP_RW_PASSWORD" \
  -v app_ro_password="$APP_RO_PASSWORD" -v investigator_password="$INVESTIGATOR_PASSWORD" \
  -v writer_password="$TELEMETRY_WRITER_PASSWORD" -v chaos_password="$CHAOS_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE replicator WITH LOGIN REPLICATION PASSWORD %L', :'replication_password') \gexec
SELECT format('CREATE ROLE app_rw WITH LOGIN PASSWORD %L', :'app_rw_password') \gexec
SELECT format('CREATE ROLE app_ro WITH LOGIN PASSWORD %L', :'app_ro_password') \gexec
SELECT format('CREATE ROLE investigator_ro WITH LOGIN PASSWORD %L', :'investigator_password') \gexec
SELECT format('CREATE ROLE telemetry_writer WITH LOGIN PASSWORD %L', :'writer_password') \gexec
SELECT format('CREATE ROLE chaos_admin WITH LOGIN PASSWORD %L', :'chaos_password') \gexec
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE SCHEMA ground_truth AUTHORIZATION chaos_admin;
REVOKE ALL ON SCHEMA ground_truth FROM PUBLIC;
CREATE TABLE orders (id uuid PRIMARY KEY, product text NOT NULL, quantity integer NOT NULL, status text NOT NULL);
GRANT SELECT, INSERT ON orders TO app_rw;
GRANT SELECT ON orders TO app_ro;
GRANT pg_monitor TO investigator_ro;
GRANT USAGE ON SCHEMA public TO investigator_ro, telemetry_writer;
ALTER ROLE investigator_ro SET default_transaction_read_only=on;
-- Future application migrations must explicitly grant read-only access to public tables.
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT SELECT ON TABLES TO investigator_ro;
SQL
printf '\nhost replication replicator 0.0.0.0/0 scram-sha-256\nhost replication replicator ::/0 scram-sha-256\n' >> "$PGDATA/pg_hba.conf"
