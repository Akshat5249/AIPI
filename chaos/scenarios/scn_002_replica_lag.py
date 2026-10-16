"""SCN-002: pause standby replay while continuing healthy primary writes."""

import time

from chaos.scenarios.contracts import ChaosError, GroundTruth, ScenarioSpec
from chaos.scenarios.lab import Lab, now, wait_for
from chaos.scenarios.runner import Run, cli
from chaos.scenarios.signals import metrics, scalar

SPEC = ScenarioSpec(
    scenario_id="SCN-002",
    name="Replica Lag",
    description="Bounded standby replay pause with healthy primary writes.",
    target="postgres-replica",
    preconditions=["Healthy seeded traffic", "Primary writable", "Replica unpaused and caught up"],
    injection="pg_wal_replay_pause() on verified standby, then seeded primary write burst",
    ground_truth=GroundTruth(
        injected_fault="standby WAL replay paused",
        expected_root_cause="postgres-replica WAL replay intentionally paused",
    ),
    expected_signals=[
        "replica_lag_seconds rises",
        "replica_replay_paused=1",
        "primary_healthy=1",
        "Stale replica read",
        "Healthy checkout writes",
    ],
    expected_false_leads=["Stale reads resemble missing application writes"],
    recovery="Resume standby replay; verify new orders visible and fresh lag/paused "
    "gauges recovered",
    evaluation_thresholds={
        "lag_rise_seconds": 2,
        "max_lag_seconds": 4,
        "healthy_primary_writes": 10,
        "recovery_timeout_seconds": 30,
    },
)


def inject(lab: Lab, run: Run) -> None:
    with lab.connect("chaos_admin", replica=True) as db:
        db.execute("SELECT pg_wal_replay_pause()")
        wait_for(
            lambda: scalar(db, "SELECT pg_get_wal_replay_pause_state()") == "paused",
            description="standby replay actually paused",
        )
    orders = [lab.create_order() for _ in range(10)]
    run.data["last_order"] = orders[-1]
    run.observations["healthy_primary_writes"] = len(orders)
    # Observe each newly written order, so the false-lead error/latency signal does
    # not depend on background traffic scheduling or one lucky request sample.
    for order in orders:
        response = lab.client.get(f"/orders/{order.id}")
        if response.status_code != 404:
            raise ChaosError("Paused replica did not expose the expected stale read")
    run.observations["stale_read_probes"] = len(orders)
    healthy = []
    with lab.connect("investigator_ro") as db:
        for _ in range(10):
            healthy.append(scalar(db, "SELECT NOT pg_is_in_recovery() AND 1=1"))
            time.sleep(1)
    run.observations["direct_primary_health_samples"] = healthy
    run.data["direct_primary_health_samples"] = healthy
    run.data["pause_end"] = now()


def recover(lab: Lab, run: Run) -> None:
    with lab.connect("chaos_admin", replica=True) as db:
        db.execute("SELECT pg_wal_replay_resume()")
        wait_for(
            lambda: not scalar(db, "SELECT pg_is_wal_replay_paused()"),
            description="standby replay resumed",
        )
    resumed = now()
    if "last_order" in run.data:
        wait_for(
            lambda: lab.read_visible(run.data["last_order"]),
            description="written order visible after replay resumes",
        )

    def recovered() -> bool:
        end = now()
        lag = metrics(lab, "replica_lag_seconds", resumed, end)
        paused = metrics(lab, "replica_replay_paused", resumed, end)
        return bool(lag and paused and lag[-1][1] <= 2 and paused[-1][1] == 0)

    wait_for(recovered, description="fresh recovered lag and paused telemetry")
    run.observations["replica_read_recovered"] = True
    run.observations["replay_resumed"] = True


def verify(lab: Lab, run: Run) -> None:
    assert run.injection_ts is not None
    start, end = run.injection_ts, run.data["pause_end"]
    lag = metrics(lab, "replica_lag_seconds", start, end)
    paused = metrics(lab, "replica_replay_paused", start, end)
    primary = metrics(lab, "primary_healthy", start, end)
    lag_bytes = metrics(lab, "replica_lag_bytes", start, end)
    if len(lag) < 3 or max(v for _, v in lag) < 4 or lag[-1][1] - lag[0][1] < 2:
        raise ChaosError("Stored replica lag did not measurably rise")
    if not paused or not any(v == 1 for _, v in paused):
        raise ChaosError("Stored replay-paused signal missing")
    if (
        not primary
        or not all(v == 1 for _, v in primary)
        or not all(run.data["direct_primary_health_samples"])
    ):
        raise ChaosError("Primary health metric failed during pause")
    if not lag_bytes or max(v for _, v in lag_bytes) <= 0:
        raise ChaosError("No WAL backlog observed")
    with lab.connect("investigator_ro") as db:
        stale = scalar(
            db,
            "SELECT count(*) FROM telemetry_logs WHERE service='orders-api' "
            "AND body='stale replica read' AND ts BETWEEN %s AND %s",
            (start, end),
        )
    if not stale:
        raise ChaosError("Expected stale-read log missing")
    run.observations.update(
        lag_samples=[{"ts": ts.isoformat(), "seconds": v} for ts, v in lag],
        max_lag_bytes=max(v for _, v in lag_bytes),
        replay_paused_samples=sum(v == 1 for _, v in paused),
        primary_healthy_samples=len(primary),
        stale_read_logs=stale,
    )


if __name__ == "__main__":
    cli(SPEC, inject, recover, verify)
