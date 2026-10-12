"""SCN-001: kill the lab checkout process, observe real failure signals, recover."""

import time

import httpx
from pydantic import JsonValue, TypeAdapter

from chaos.scenarios.contracts import ChaosError, GroundTruth, ScenarioSpec
from chaos.scenarios.lab import Lab, now, wait_for
from chaos.scenarios.runner import Run, cli
from chaos.scenarios.signals import die_then_start, error_counter, failures, runtime_events

SPEC = ScenarioSpec(
    scenario_id="SCN-001",
    name="Service Kill",
    description="Bounded forced termination of the checkout lab container.",
    target="checkout-api",
    preconditions=[
        "Steady seeded successful traffic",
        "Healthy primary and unpaused replica",
        "Healthy checkout, gateway, orders, lag probe, and event watcher",
    ],
    injection="docker kill --signal=KILL <verified aipi checkout-api container>",
    ground_truth=GroundTruth(
        injected_fault="SIGKILL checkout-api",
        expected_root_cause="checkout-api process/container forcibly terminated",
    ),
    expected_signals=[
        "Runtime die exit 137 followed by start",
        "Gateway 5xx spike",
        "Failed spans",
    ],
    expected_false_leads=["Downstream timeout resembles network or database failure"],
    recovery="Observe restart policy; explicitly docker start if manual kill suppresses "
    "restart; verify healthy checkout and replica reads",
    evaluation_thresholds={
        "die_then_start": 1,
        "gateway_5xx": 1,
        "failed_spans": 1,
        "error_logs": 1,
        "recovery_timeout_seconds": 30,
    },
)


def inject(lab: Lab, run: Run) -> None:
    target = lab.container("checkout-api")
    run.data["container_id"] = target.id
    run.data["baseline_errors"] = error_counter(lab)
    lab.docker("kill", "--signal=KILL", target.id)
    codes = []
    # Bounded foreground traffic guarantees observability independently of background timing.
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        try:
            codes.append(lab.checkout().status_code)
        except httpx.HTTPError:
            # Keep observing; require actual HTTP 5xx evidence before passing.
            run.observations["probe_transport_errors"] = True
        time.sleep(0.1)
    run.observations["gateway_5xx_requests"] = sum(code >= 500 for code in codes)
    if not run.observations["gateway_5xx_requests"]:
        raise ChaosError("Kill produced no observable gateway 5xx requests")


def recover(lab: Lab, run: Run) -> None:
    target = lab.container("checkout-api")
    if not target.running:
        lab.docker("start", target.id)
        run.observations["explicit_start_required"] = True
    else:
        run.observations["explicit_start_required"] = False
    wait_for(lab.healthy_checkout, description="checkout recovered")
    wait_for(
        lambda: all(
            lab.container(service).health == "healthy" for service in ("checkout-api", "gateway")
        ),
        description="Docker health checks confirm checkout and gateway recovery",
    )
    order = lab.create_order()
    wait_for(lambda: lab.read_visible(order), description="replica reads after checkout recovery")


def verify(lab: Lab, run: Run) -> None:
    assert run.injection_ts is not None and run.recovery_ts is not None
    start = run.injection_ts
    events = wait_for(
        lambda: items if die_then_start(items := runtime_events(lab, start, now())) else [],
        description="stored die(137) then start events",
    )
    checks = wait_for(
        lambda: items if all((items := failures(lab, start, now())).values()) else {},
        description="stored failed spans and gateway error logs",
    )
    counter = wait_for(
        lambda: value if (value := error_counter(lab, start)) > run.data["baseline_errors"] else 0,
        description="exported 5xx metric increase",
    )
    run.observations.update(
        runtime_events=TypeAdapter(JsonValue).validate_python(events),
        **checks,
        gateway_503_counter_increase=counter - run.data["baseline_errors"],
    )


if __name__ == "__main__":
    cli(SPEC, inject, recover, verify)
