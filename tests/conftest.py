"""Docker-dependent tests skip only when the daemon cannot be reached."""

import shutil
import subprocess

import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    try:
        available = (
            bool(shutil.which("docker"))
            and subprocess.run(
                ["docker", "info", "--format", "{{.ServerVersion}}"],
                capture_output=True,
                timeout=10,
                check=False,
            ).returncode
            == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        available = False
    if not available:
        for item in items:
            if item.get_closest_marker("docker"):
                item.add_marker(pytest.mark.skip(reason="Docker daemon unavailable"))
