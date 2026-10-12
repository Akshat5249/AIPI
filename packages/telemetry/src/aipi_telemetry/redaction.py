"""Recursive secret removal before storage and future model context construction."""

import re

from pydantic import JsonValue

SENSITIVE = re.compile(r"(?:api[_-]?key|secret|password|token|authorization)", re.I)
RULES = [
    ("bearer", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.I)),
    ("connection_credentials", re.compile(r"([a-z][a-z0-9+.-]*://)[^\s/@]+:[^\s/@]+@", re.I)),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    (
        "secret_assignment",
        re.compile(
            r"""\b(?:api[_-]?key|secret|password|token)["']?\s*[=:]\s*(?:"[^"]*"|'[^']*'|[^\s,;}]+)""",
            re.I,
        ),
    ),
]
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def redact(value: JsonValue, *, emails: bool = True) -> tuple[JsonValue, list[dict[str, str]]]:
    """Return sanitized data and field/rule markers without storing original values."""
    markers: list[dict[str, str]] = []

    def walk(item: JsonValue, path: str) -> JsonValue:
        if isinstance(item, dict):
            # OTLP attributes encode the sensitive field name as a value.
            if (
                isinstance(item.get("key"), str)
                and SENSITIVE.search(str(item["key"]))
                and "value" in item
            ):
                markers.append({"field": f"{path}.{item['key']}", "rule": "sensitive_key"})
                return {"key": item["key"], "value": {"stringValue": "[REDACTED]"}}
            result: dict[str, JsonValue] = {}
            for key, child in item.items():
                location = f"{path}.{key}"
                if SENSITIVE.search(key):
                    result[key] = "[REDACTED]"
                    markers.append({"field": location, "rule": "sensitive_key"})
                else:
                    result[key] = walk(child, location)
            return result
        if isinstance(item, list):
            return [walk(child, f"{path}[{index}]") for index, child in enumerate(item)]
        if isinstance(item, str):
            for name, pattern in RULES + ([("email", EMAIL)] if emails else []):
                replacement = r"\1[REDACTED]@" if name == "connection_credentials" else "[REDACTED]"
                item, count = pattern.subn(replacement, item)
                if count:
                    markers.append({"field": path, "rule": name})
        return item

    return walk(value, "$"), markers
