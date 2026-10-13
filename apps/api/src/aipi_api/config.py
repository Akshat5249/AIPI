"""Validated runtime configuration; credentials remain environment-only."""

from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: Literal["local", "test", "demo", "prod"] = "local"
    database_url: SecretStr
    telemetry_database_url: SecretStr
    otel_exporter_otlp_endpoint: str = "http://localhost:4318"
    model_provider: Literal["mock", "anthropic", "openai"] = "mock"
    replica_database_url: SecretStr | None = None
    scorer_url: str = "http://127.0.0.1:8001"
    runbooks_path: str = "runbooks"
    model_name: str = "deterministic-mock"
    model_api_key: SecretStr = SecretStr("")
    redact_emails: bool = True
    otel_enabled: bool = False
