"""Fixture oracle only: hidden synthetic labels are read here, never by the agent."""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class SyntheticTruth(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    expected_category: str


def expected_category(path: Path) -> str:
    if not path.name.endswith(".truth.json"):
        raise ValueError("Scorer accepts a separate truth file only")
    return SyntheticTruth.model_validate(json.loads(path.read_text())).expected_category
