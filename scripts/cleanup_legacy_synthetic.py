"""One-time, narrowly identified pre-M7 test leftovers; dry-run unless --apply."""

import argparse
import json
from datetime import UTC, datetime, timedelta

import psycopg

from chaos.scenarios.lab import Lab


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    lab = Lab()
    cutoff = datetime.now(UTC) + timedelta(days=1)
    try:
        with psycopg.connect(
            host="127.0.0.1",
            port=lab.target.db_port,
            dbname="aipi",
            user="postgres",
            password=lab.env["POSTGRES_PASSWORD"],
        ) as db:
            # Legacy tests used UUID-prefixed source IDs, but no cleanup marker.
            anchors = db.execute(
                "SELECT DISTINCT left(id,32) FROM telemetry_logs "
                "WHERE service IN ('api','gateway','checkout-api') AND ts>%s "
                "AND attributes_json = '{\"synthetic\":true}'::jsonb AND ("
                "(service='checkout-api' AND body='synthetic noise' "
                "AND id ~ '^[0-9a-f]{32}-log-[0-9]{3}$') OR "
                "(service IN ('api','gateway') AND body='synthetic cap check' "
                "AND id ~ '^[0-9a-f]{32}(-[0-9]+|outside-service|outside-time|late)$'))",
                (cutoff,),
            ).fetchall()
            prefixes = [r[0] for r in anchors]
            predicates = {
                "logs": (
                    "ts",
                    "service IN ('api','gateway','checkout-api') AND left(id,32)=ANY(%s) "
                    "AND attributes_json = "
                    "'{\"synthetic\":true}'::jsonb AND body IN "
                    "('synthetic noise','synthetic cap check')",
                ),
                "events": (
                    "ts",
                    "service IN ('api','checkout-api') AND left(id,32)=ANY(%s) "
                    "AND event_domain='runtime' AND ("
                    "(service='api' AND length(id)=32 AND event_name='start' "
                    "AND attributes_json='{}'::jsonb) OR (service='checkout-api' "
                    "AND ((id ~ '-a-die$' AND event_name='die' AND attributes_json="
                    '\'{"synthetic":true,"exit_code":"137"}\'::jsonb) OR '
                    "(id ~ '-z-start$' AND event_name='start' AND attributes_json="
                    "'{\"synthetic\":true}'::jsonb) OR (id ~ '-heartbeat-[0-9]{3}$' "
                    "AND event_name='heartbeat' AND attributes_json="
                    "'{\"synthetic\":true}'::jsonb))))",
                ),
                "metrics": (
                    "ts",
                    "service IN ('api','pg-lag-probe') AND left(id,32)=ANY(%s) "
                    "AND ((service='api' AND length(id)=32 "
                    "AND metric_name='test_gauge' AND value=1 AND labels_json='{}'::jsonb) "
                    "OR (service='pg-lag-probe' AND id=left(id,32)||metric_name AND "
                    "labels_json='{\"synthetic\":true}'::jsonb AND (metric_name,value) IN "
                    "(('replica_lag_seconds',8),('replica_replay_paused',1),"
                    "('replica_lag_bytes',512),('primary_healthy',1))))",
                ),
                "spans": (
                    "start_ts",
                    "trace_id=ANY(%s) AND span_id=left(trace_id,16) "
                    "AND service='api' AND operation='synthetic' AND status='0' "
                    "AND duration_ms=1 AND attributes_json='{}'::jsonb",
                ),
            }
            for phase in ("before", "after"):
                counts = {}
                for kind, (stamp, predicate) in predicates.items():
                    table = f"telemetry_{kind}"
                    params = (cutoff, prefixes)
                    count = db.execute(
                        f"SELECT count(*) FROM {table} WHERE {stamp}>%s AND {predicate}", params
                    ).fetchone()[0]
                    counts[kind] = count
                print(
                    json.dumps(
                        {
                            "phase": phase,
                            "cutoff": cutoff.isoformat(),
                            "legacy_prefixes": len(prefixes),
                            "counts": counts,
                            "apply": args.apply,
                        }
                    ),
                    flush=True,
                )
                if phase == "before" and args.apply:
                    for kind, (stamp, predicate) in predicates.items():
                        db.execute(
                            f"DELETE FROM telemetry_{kind} WHERE {stamp}>%s AND {predicate}",
                            (cutoff, prefixes),
                        )
    finally:
        lab.close()


if __name__ == "__main__":
    main()
