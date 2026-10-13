"""Versioned prompts, redaction and delimiter-safe untrusted evidence context."""

import json
import re
from pathlib import Path

from aipi_telemetry.redaction import redact
from aipi_tools.correlators import Signal
from pydantic import BaseModel, ConfigDict, JsonValue

PROMPT_VERSION = "v1"
SYSTEM = (Path(__file__).parent / "prompts" / "v1.txt").read_text()


class Prompt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    system: str = SYSTEM
    data_block: str
    signals: tuple[Signal, ...]
    repair: bool = False


def data_block(value: JsonValue) -> str:
    clean, _ = redact(value)
    raw = json.dumps(clean, sort_keys=True, ensure_ascii=True)
    raw = re.sub(r"[\x00-\x1f\x7f]", "", raw)
    # Escape tags/control tokens rather than trusting evidence to preserve the boundary.
    raw = raw.replace("<", "\\u003c").replace(">", "\\u003e").replace("`", "\\u0060")
    return "<UNTRUSTED_DATA>\n" + raw + "\n</UNTRUSTED_DATA>"
