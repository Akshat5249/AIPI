"""Fixed local Docker targets, separate DB identities, and bounded polling."""

import json
import random
import subprocess
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx
import psycopg
from aipi_demo.contracts import Order
from dotenv import dotenv_values
from pydantic import BaseModel

from chaos.scenarios.contracts import ChaosError

ROOT = Path(__file__).resolve().parents[2]


def wait_for[T](check: Callable[[], T], *, timeout: float = 30, description: str) -> T:
    """Poll a bounded predicate, returning its nonempty validated result."""
    deadline = time.monotonic() + timeout
    while True:
        result = check()
        if result:
            return result
        if time.monotonic() >= deadline:
            raise ChaosError(f"Timed out: {description}")
        time.sleep(0.25)


def now() -> datetime:
    return datetime.now(UTC)


class Container(BaseModel):
    id: str
    running: bool
    health: str
    restart_policy: str
    project: str
    service: str


class Lab:
    """Uses host loopback ports and the fixed aipi Compose project only."""

    def __init__(self, seed: int = 42) -> None:
        self.env = dotenv_values(ROOT / ".env")
        self.rng = random.Random(seed)
        self.client = httpx.Client(base_url="http://127.0.0.1:8080", timeout=8)

    def close(self) -> None:
        self.client.close()

    def connect(self, role: str, *, replica: bool = False) -> psycopg.Connection:
        key = {"chaos_admin": "CHAOS_PASSWORD", "investigator_ro": "INVESTIGATOR_PASSWORD"}[role]
        try:
            return psycopg.connect(
                host="127.0.0.1",
                port=5433 if replica else 5432,
                user=role,
                dbname="aipi",
                password=self.env[key],
                autocommit=True,
                connect_timeout=5,
                options="-c statement_timeout=5000",
            )
        except psycopg.Error:
            raise ChaosError("Lab database unavailable; run make up") from None

    def docker(self, *args: str) -> str:
        result = subprocess.run(
            ["docker", *args], cwd=ROOT, capture_output=True, text=True, timeout=15, check=False
        )
        if result.returncode:
            raise ChaosError(f"Docker {args[0]} failed (exit {result.returncode})")
        return result.stdout.strip()

    def container(self, service: str) -> Container:
        if service not in {
            "checkout-api",
            "gateway",
            "orders-api",
            "traffic",
            "pg-lag-probe",
            "event-watcher",
        }:
            raise ChaosError("Container outside the lab allowlist")
        container_id = self.docker(
            "compose",
            "--env-file",
            str(ROOT / ".env"),
            "-f",
            str(ROOT / "infra/docker/compose.yml"),
            "ps",
            "--all",
            "-q",
            service,
        )
        if not container_id or "\n" in container_id:
            raise ChaosError(f"Expected one lab container: {service}")
        template = (
            '{"id":"{{.Id}}","running":{{.State.Running}},'
            '"health":"{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}",'
            '"restart_policy":"{{.HostConfig.RestartPolicy.Name}}",'
            '"project":"{{index .Config.Labels "com.docker.compose.project"}}",'
            '"service":"{{index .Config.Labels "com.docker.compose.service"}}"}'
        )
        state = Container.model_validate(
            json.loads(self.docker("inspect", "--format", template, container_id))
        )
        if state.project != "aipi" or state.service != service:
            raise ChaosError("Refusing a container outside the fixed aipi lab")
        return state

    def checkout(self) -> httpx.Response:
        return self.client.post(
            "/checkout",
            json={
                "product": self.rng.choice(["book", "keyboard", "coffee"]),
                "quantity": self.rng.randint(1, 3),
            },
        )

    def create_order(self) -> Order:
        response = self.checkout()
        if response.status_code != 200:
            raise ChaosError(f"Expected healthy checkout, got HTTP {response.status_code}")
        return Order.model_validate(response.json())

    def read_visible(self, order: Order) -> bool:
        response = self.client.get(f"/orders/{order.id}")
        if response.status_code != 200:
            return False
        return Order.model_validate(response.json()).id == order.id

    def healthy_checkout(self) -> bool:
        try:
            if self.client.get("/readyz").status_code != 200:
                return False
            return self.checkout().status_code == 200
        except httpx.HTTPError:
            return False

    def preconditions(self) -> None:
        for service in (
            "checkout-api",
            "gateway",
            "orders-api",
            "traffic",
            "pg-lag-probe",
            "event-watcher",
        ):
            state = self.container(service)
            if not state.running or state.health != "healthy":
                raise ChaosError(
                    f"Precondition failed: {service} not healthy; run make seed-traffic"
                )
        if self.container("checkout-api").restart_policy != "unless-stopped":
            raise ChaosError("Precondition failed: checkout restart policy must be unless-stopped")
        with (
            self.connect("investigator_ro") as primary,
            self.connect("investigator_ro", replica=True) as replica,
        ):
            primary_state = primary.execute("SELECT pg_is_in_recovery()").fetchone()
            assert primary_state is not None
            if primary_state[0]:
                raise ChaosError("Precondition failed: primary is in recovery")
            standby = replica.execute(
                "SELECT pg_is_in_recovery(), pg_is_wal_replay_paused()"
            ).fetchone()
            assert standby is not None
            if not standby[0] or standby[1]:
                raise ChaosError("Precondition failed: replica must be a healthy unpaused standby")

            def steady() -> bool:
                row = primary.execute(
                    "SELECT count(*) FROM telemetry_logs WHERE service='traffic' "
                    "AND ts>now()-interval '6 seconds' AND "
                    "attributes_json->>'http.status_code'='200'"
                ).fetchone()
                return bool(row and row[0] >= 3)

            wait_for(steady, description="steady healthy seeded traffic")
        order = self.create_order()
        wait_for(lambda: self.read_visible(order), description="precondition replica reads")
