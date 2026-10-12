"""Offline infrastructure contract checks."""

from pathlib import Path

import yaml


def test_compose_topology_and_images():
    services = yaml.safe_load(Path("infra/docker/compose.yml").read_text())["services"]
    assert set(services) == {
        "postgres-primary",
        "postgres-replica",
        "migrate",
        "api",
        "web",
        "gateway",
        "checkout-api",
        "orders-api",
        "pg-lag-probe",
        "event-watcher",
        "traffic",
        "otel-collector",
    }
    assert services["postgres-primary"]["image"] == "postgres:16"
    assert all("platform" not in service for service in services.values())
    assert "CHAOS_PASSWORD" not in services["api"]["environment"]
    assert "POSTGRES_PASSWORD" not in services["api"]["environment"]
    assert services["checkout-api"]["restart"] == "unless-stopped"


def test_collector_and_ci_contracts():
    collector = yaml.safe_load(Path("infra/otel/collector.yml").read_text())
    assert collector["exporters"]["otlphttp"]["encoding"] == "json"
    assert collector["exporters"]["otlphttp"]["endpoint"] == "http://api:8000/internal/otlp"
    workflow = yaml.safe_load(Path(".github/workflows/ci.yml").read_text())
    commands = [step.get("run") for step in workflow["jobs"]["foundation"]["steps"]]
    assert "make lint" in commands and "make up" in commands and "make test" in commands
    assert workflow["permissions"]["contents"] == "read"
