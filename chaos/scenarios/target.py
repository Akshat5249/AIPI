"""Loopback-only host ports and an explicit isolated lab project."""

import os

from pydantic import BaseModel, ConfigDict, Field


class LabTarget(BaseModel):
    """Host-side settings; never inferred from telemetry or supplied by an agent."""

    model_config = ConfigDict(frozen=True)
    project: str = Field(default="aipi", pattern=r"^aipi(?:-[a-z0-9-]+)?$")
    db_port: int = Field(default=5432, ge=1024, le=65535)
    replica_port: int = Field(default=5433, ge=1024, le=65535)
    api_port: int = Field(default=8000, ge=1024, le=65535)
    gateway_port: int = Field(default=8080, ge=1024, le=65535)
    web_port: int = Field(default=5173, ge=1024, le=65535)
    collector_port: int = Field(default=4318, ge=1024, le=65535)
    collector_health_port: int = Field(default=13133, ge=1024, le=65535)

    @classmethod
    def from_env(cls) -> "LabTarget":
        """Read optional process overrides; the credential file remains unchanged."""
        values: dict[str, str] = {}
        for name in cls.model_fields:
            key = "COMPOSE_PROJECT_NAME" if name == "project" else f"AIPI_{name.upper()}"
            if key in os.environ:
                values[name] = os.environ[key]
        return cls.model_validate(values)

    @property
    def api(self) -> str:
        return f"http://127.0.0.1:{self.api_port}"

    @property
    def web(self) -> str:
        return f"http://127.0.0.1:{self.web_port}"
