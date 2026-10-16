"""Wait for external health including the shell-free Collector image."""

import time
import urllib.request

from chaos.scenarios.target import LabTarget

target = LabTarget.from_env()
for url in (
    target.api + "/readyz",
    f"http://127.0.0.1:{target.gateway_port}/readyz",
    target.web + "/healthz",
    f"http://127.0.0.1:{target.collector_health_port}/",
):
    for attempt in range(30):
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                assert response.status == 200
            print(f"Healthy: {url}")
            break
        except (OSError, AssertionError):
            if attempt == 29:
                raise
            time.sleep(1)
