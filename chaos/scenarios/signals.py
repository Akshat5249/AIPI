"""Read-only, time-bounded checks of actual telemetry emitted by the lab."""

from datetime import datetime
from typing import Any

import psycopg

from chaos.scenarios.lab import Lab


def scalar(db: psycopg.Connection, query: str, params: tuple[Any, ...] = ()) -> Any:
    row = db.execute(query, params).fetchone()
    assert row is not None
    return row[0]


def metrics(lab: Lab, name: str, start: datetime, end: datetime) -> list[tuple[datetime, float]]:
    with lab.connect("investigator_ro") as db:
        return db.execute(
            "SELECT ts, value FROM telemetry_metrics "
            "WHERE service='pg-lag-probe' AND metric_name=%s AND ts BETWEEN %s AND %s "
            "ORDER BY ts",
            (name, start, end),
        ).fetchall()


def error_counter(lab: Lab, since: datetime | None = None) -> float:
    with lab.connect("investigator_ro") as db:
        return float(
            scalar(
                db,
                "SELECT COALESCE((SELECT value FROM telemetry_metrics "
                "WHERE service='gateway' AND metric_name='requests_total' "
                "AND labels_json->>'status'='503' AND labels_json->>'route'='/checkout' "
                "AND ts >= COALESCE(%s, now()-interval '6 seconds') "
                "ORDER BY ts DESC LIMIT 1),0)",
                (since,),
            )
        )


def failures(lab: Lab, start: datetime, end: datetime) -> dict[str, int]:
    with lab.connect("investigator_ro") as db:
        return {
            "gateway_failed_spans": int(
                scalar(
                    db,
                    "SELECT count(*) FROM telemetry_spans WHERE service='gateway' "
                    "AND start_ts BETWEEN %s AND %s AND status IN ('2','STATUS_CODE_ERROR')",
                    (start, end),
                )
            ),
            "gateway_error_logs": int(
                scalar(
                    db,
                    "SELECT count(*) FROM telemetry_logs WHERE service='gateway' AND ts "
                    "BETWEEN %s AND %s "
                    "AND severity='ERROR' AND body='checkout dependency failed'",
                    (start, end),
                )
            ),
        }


def runtime_events(lab: Lab, start: datetime, end: datetime) -> list[dict[str, Any]]:
    with lab.connect("investigator_ro") as db:
        rows = db.execute(
            "SELECT event_name, ts, attributes_json->>'exit_code' FROM telemetry_events "
            "WHERE service='checkout-api' AND ts BETWEEN %s AND %s "
            "AND event_name IN ('die','start','restart') ORDER BY ts",
            (start, end),
        ).fetchall()
        return [{"event": row[0], "ts": row[1].isoformat(), "exit_code": row[2]} for row in rows]


def die_then_start(events: list[dict[str, Any]]) -> bool:
    """Require SIGKILL exit evidence followed by recovery within the same window."""
    saw_die = False
    for event in events:
        if event["event"] == "die" and event["exit_code"] == "137":
            saw_die = True
        elif saw_die and event["event"] == "start":
            return True
    return False
