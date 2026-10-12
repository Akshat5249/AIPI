"""Wait for external health including the shell-free Collector image."""

import time
import urllib.request

for url in (
    "http://localhost:8000/readyz",
    "http://localhost:8080/readyz",
    "http://localhost:5173/healthz",
    "http://localhost:13133/",
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
