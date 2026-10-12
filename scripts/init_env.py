"""Generate local-only credentials; preserve existing environment files."""

import os
import secrets
from pathlib import Path

path = Path(".env")
if not path.exists():
    values = {
        key: secrets.token_hex(24)
        for key in (
            "POSTGRES_PASSWORD",
            "REPLICATION_PASSWORD",
            "APP_RW_PASSWORD",
            "APP_RO_PASSWORD",
            "INVESTIGATOR_PASSWORD",
            "TELEMETRY_WRITER_PASSWORD",
            "CHAOS_PASSWORD",
        )
    }
    values.update(
        APP_ENV="local",
        MODEL_PROVIDER="mock",
        MODEL_NAME="deterministic-mock",
        MODEL_API_KEY="",
        OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4318",
    )
    values["DATABASE_URL"] = (
        f"postgresql+psycopg://investigator_ro:{values['INVESTIGATOR_PASSWORD']}@localhost:5432/aipi"
    )
    values["TELEMETRY_DATABASE_URL"] = (
        f"postgresql+psycopg://telemetry_writer:{values['TELEMETRY_WRITER_PASSWORD']}@localhost:5432/aipi"
    )
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write("\n".join(f"{key}={value}" for key, value in values.items()) + "\n")
    print("Created private .env with generated lab credentials")
else:
    print("Preserving existing .env")
