"""An isolated host target never widens beyond loopback or the lab project prefix."""

import pytest
from pydantic import ValidationError

from chaos.scenarios.lab import Lab
from chaos.scenarios.target import LabTarget


def test_isolated_target_and_container_verification(monkeypatch):
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "aipi-fresh-check")
    monkeypatch.setenv("AIPI_GATEWAY_PORT", "18080")
    monkeypatch.setenv("AIPI_API_PORT", "18000")
    target = LabTarget.from_env()
    assert target.project == "aipi-fresh-check"
    assert target.api == "http://127.0.0.1:18000"
    lab = Lab()
    try:
        assert str(lab.client.base_url) == "http://127.0.0.1:18080"
        calls = []

        def docker(*args):
            calls.append(args)
            if args[0] == "compose":
                return "container-id"
            return (
                '{"id":"container-id","running":true,"health":"healthy",'
                '"restart_policy":"unless-stopped","project":"aipi",'
                '"service":"checkout-api"}'
            )

        monkeypatch.setattr(lab, "docker", docker)
        with pytest.raises(Exception, match="outside the configured aipi lab"):
            lab.container("checkout-api")
        assert calls[0][1:3] == ("--project-name", "aipi-fresh-check")
    finally:
        lab.close()


@pytest.mark.parametrize(
    "values", [{"project": "production"}, {"api_port": 80}, {"db_port": 65536}]
)
def test_invalid_lab_target(values):
    with pytest.raises(ValidationError):
        LabTarget.model_validate(values)


def test_lab_connection_diagnostic_does_not_expose_driver_text(monkeypatch):
    import psycopg

    from chaos.scenarios.contracts import ChaosError

    lab = Lab()
    monkeypatch.setitem(lab.env, "INVESTIGATOR_PASSWORD", "test-only")
    try:

        def unavailable(**kwargs):
            assert kwargs["connect_timeout"] == 10
            raise psycopg.OperationalError("credential=do-not-disclose")

        monkeypatch.setattr("chaos.scenarios.lab.psycopg.connect", unavailable)
        with pytest.raises(ChaosError) as failure:
            lab.connect("investigator_ro")
        assert "OperationalError" in str(failure.value)
        assert "do-not-disclose" not in str(failure.value)
    finally:
        lab.close()
