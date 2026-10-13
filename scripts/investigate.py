"""Start and observe a background mock investigation through the public API only."""

import argparse
import json
import time

import httpx


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("incident_id")
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    with httpx.Client(base_url=args.api, timeout=20) as client:
        response = client.post(f"/api/incidents/{args.incident_id}/investigate", json={})
        response.raise_for_status()
        job = response.json()
        deadline = time.monotonic() + 120
        while job["status"] in {"queued", "running"} and time.monotonic() < deadline:
            time.sleep(0.2)
            response = client.get(f"/api/investigations/{job['id']}")
            response.raise_for_status()
            job = response.json()
        print(json.dumps(job, indent=2))
        if job["status"] != "completed":
            raise SystemExit(1)
        response = client.get(f"/api/incidents/{args.incident_id}/report")
        response.raise_for_status()
        print(json.dumps(response.json(), indent=2))


if __name__ == "__main__":
    main()
