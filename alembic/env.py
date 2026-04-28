"""Alembic environment configuration for free-games-notifier.

Reads PostgreSQL connection parameters from config.py and applies
migrations within the ``free_games`` schema.
"""

import logging
import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Make the project root importable so we can use config.py
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER  # noqa: E402

# Alembic Config object, providing access to values from alembic.ini
alembic_config = context.config

# Interpret the config file for Python logging only when running from the
# Alembic CLI (i.e., logging has not been set up yet by the service).
# When invoked programmatically from main.py the root logger already has
# handlers, so we skip fileConfig to avoid clobbering the service's logging
# configuration and emitting verbose migration-progress lines.
if alembic_config.config_file_name is not None and not logging.root.handlers:
    fileConfig(alembic_config.config_file_name)

# We do not use SQLAlchemy ORM metadata — all migrations use raw SQL via
# op.execute(), so target_metadata remains None.
target_metadata = None


def get_url() -> str:
    """Build the SQLAlchemy connection URL from environment-derived config."""
    from urllib.parse import quote_plus

    host = DB_HOST or "localhost"
    port = DB_PORT or 5432

    # Alembic migrations need an explicit target database; fail fast if missing.
    if not DB_NAME:
        raise RuntimeError("DB_NAME must be set to run Alembic migrations.")
    dbname = quote_plus(DB_NAME)

    auth = ""
    if DB_USER:
        user = quote_plus(DB_USER)
        if DB_PASSWORD:
            password = quote_plus(DB_PASSWORD)
            auth = f"{user}:{password}@"
        else:
            # Username without password: rely on server-side auth configuration.
            auth = f"{user}@"
    elif DB_PASSWORD:
        # A password without a username cannot form a valid SQLAlchemy URL.
        raise RuntimeError("DB_PASSWORD is set but DB_USER is not; cannot build database URL.")

    return f"postgresql+psycopg2://{auth}{host}:{port}/{dbname}"


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (no live DB connection required)."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema="public",
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode against a live database connection."""
    configuration = dict(alembic_config.get_section(alembic_config.config_ini_section) or {})
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_schema="public",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
