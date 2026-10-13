"""One immutable, source-derived summary per scoped telemetry metric series."""

import json
from collections.abc import Sequence
from hashlib import sha256

from aipi_telemetry.evidence import Evidence, evidence_id
from pydantic import JsonValue


def series_labels(item: Evidence) -> dict[str, JsonValue]:
    labels = item.payload.get("labels_json", {})
    if not isinstance(labels, dict):
        raise ValueError("Metric labels must be an object")
    # The normalizer stores histogram sample data here; it is not a series dimension.
    return {key: value for key, value in labels.items() if key != "histogram"}


def summarize_metrics(items: Sequence[Evidence]) -> tuple[Evidence, ...]:
    groups: dict[str, list[Evidence]] = {}
    other = [item for item in items if item.type != "metric"]
    for item in items:
        if item.type == "metric":
            key = json.dumps(
                [item.service, item.payload["metric_name"], series_labels(item)],
                sort_keys=True,
                separators=(",", ":"),
            )
            groups.setdefault(key, []).append(item)
    for key in sorted(groups):
        samples = sorted(groups[key], key=lambda e: (e.timestamp, e.source_ref))
        values = []
        for sample in samples:
            value = sample.payload["value"]
            if not isinstance(value, (int, float)):
                raise ValueError("Metric samples must be numeric")
            values.append(float(value))
        first, last = samples[0], samples[-1]
        # Include scoped membership: changed samples require a new immutable source version.
        digest = sha256((key + "|" + "|".join(e.source_ref for e in samples)).encode()).hexdigest()
        reference = "telemetry_metrics:series:" + digest
        name = str(first.payload["metric_name"])
        transitions: list[JsonValue] = []
        if name in {"replica_replay_paused", "primary_healthy"}:
            transitions = [
                {
                    "timestamp": after.timestamp.isoformat(),
                    "from": before.payload["value"],
                    "to": after.payload["value"],
                }
                for before, after in zip(samples, samples[1:], strict=False)
                if before.payload["value"] != after.payload["value"]
            ]
        payload: dict[str, JsonValue] = {
            "metric_name": name,
            "labels_json": series_labels(first),
            "aggregation": "series_summary",
            "first": values[0],
            "last": values[-1],
            "min": min(values),
            "max": max(values),
            "sample_count": len(samples),
            "first_timestamp": first.timestamp.isoformat(),
            "last_timestamp": last.timestamp.isoformat(),
            "first_source_ref": first.source_ref,
            "last_source_ref": last.source_ref,
            "transitions": transitions,
        }
        markers = {(r.field, r.rule): r for e in samples for r in e.redactions}
        other.append(
            Evidence(
                evidence_id=evidence_id("metric", reference),
                type="metric",
                service=first.service,
                timestamp=first.timestamp,
                source_ref=reference,
                summary=f"{name}: first={values[0]} last={values[-1]} min={min(values)} "
                f"max={max(values)} samples={len(samples)}"[:200],
                payload=payload,
                redactions=tuple(markers[k] for k in sorted(markers)),
            )
        )
    return tuple(other)
