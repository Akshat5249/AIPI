"""Canonical, deeply immutable evidence and deterministic chronological timelines."""

from datetime import datetime
from hashlib import sha256
from typing import Any, Literal, NoReturn

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    JsonValue,
    field_validator,
    model_validator,
)

EvidenceType = Literal["log", "metric", "trace", "event", "runbook"]


def deny_mutation(*args: Any, **kwargs: Any) -> NoReturn:
    raise TypeError("Evidence payload is immutable")


class FrozenDict(dict[str, JsonValue]):
    __setitem__ = deny_mutation
    __delitem__ = deny_mutation
    clear = deny_mutation
    pop = deny_mutation
    popitem = deny_mutation
    setdefault = deny_mutation
    update = deny_mutation
    __ior__ = deny_mutation


class FrozenList(list[JsonValue]):
    __setitem__ = deny_mutation
    __delitem__ = deny_mutation
    append = deny_mutation
    clear = deny_mutation
    extend = deny_mutation
    insert = deny_mutation
    pop = deny_mutation
    remove = deny_mutation
    reverse = deny_mutation
    sort = deny_mutation
    __iadd__ = deny_mutation
    __imul__ = deny_mutation


def freeze(value: JsonValue) -> JsonValue:
    if isinstance(value, dict):
        return FrozenDict({key: freeze(child) for key, child in value.items()})
    if isinstance(value, list):
        return FrozenList(freeze(child) for child in value)
    return value


def evidence_id(kind: EvidenceType, source_ref: str) -> str:
    return "ev_" + sha256(f"{kind}|{source_ref}".encode()).hexdigest()[:16]


class Redaction(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    field: str
    rule: str


class Evidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    evidence_id: str
    type: EvidenceType
    service: str
    timestamp: AwareDatetime
    source_ref: str
    summary: str
    payload: dict[str, JsonValue]
    redactions: tuple[Redaction, ...] = ()

    @field_validator("payload")
    @classmethod
    def immutable_payload(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return FrozenDict({key: freeze(child) for key, child in value.items()})

    @model_validator(mode="after")
    def check_id(self) -> "Evidence":
        if self.evidence_id != evidence_id(self.type, self.source_ref):
            raise ValueError("Evidence ID does not match its source reference")
        return self


class TimelineItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    ts: datetime
    label: str
    evidence_ids: tuple[str, ...]


def build_timeline(items: tuple[Evidence, ...]) -> tuple[TimelineItem, ...]:
    """Keep each observation in time/ID order and cite its immutable source."""
    return tuple(
        TimelineItem(ts=item.timestamp, label=item.summary, evidence_ids=(item.evidence_id,))
        for item in sorted(items, key=lambda item: (item.timestamp, item.evidence_id))
    )
