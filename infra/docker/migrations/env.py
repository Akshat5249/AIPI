"""Environment-only migration credentials; no application access to admin passwords."""

import os

from aipi_telemetry.storage import metadata
from alembic import context
from sqlalchemy import create_engine

engine = create_engine(os.environ["MIGRATION_DATABASE_URL"], hide_parameters=True)
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=metadata)
    with context.begin_transaction():
        context.run_migrations()
