"""Database lifecycle helpers: Alembic migrations and post-migration sanity checks.

These helpers are invoked from the scheduler entry point at startup when
``DB_HOST`` is configured.  They isolate the database-bootstrap logic from
the rest of ``main.py``, making each step testable in isolation.
"""

import logging
import os

import psycopg2
from alembic.config import Config as AlembicConfig

from alembic import command as alembic_command
from config import DB_CONNECT_TIMEOUT, DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER

logger = logging.getLogger(__name__)


def run_db_migrations() -> None:
    """Apply any pending Alembic migrations up to the latest revision."""
    logger.info("Applying database migrations...")
    # Suppress verbose per-revision Alembic log lines from service logs.
    # env.py skips fileConfig when the service's logging is already configured,
    # but raise the level here as well to guard against any propagation.
    logging.getLogger("alembic").setLevel(logging.WARNING)
    cfg = AlembicConfig(
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic.ini")
    )
    alembic_command.upgrade(cfg, "head")
    logger.info("Database migrations applied successfully.")


def verify_required_tables() -> None:
    """Fail fast when required DB tables are missing after migrations."""
    logger.info("Verifying required database tables...")

    conn_params = {
        "host": DB_HOST,
        "port": DB_PORT,
        "dbname": DB_NAME,
        "user": DB_USER,
        "password": DB_PASSWORD,
        "connect_timeout": DB_CONNECT_TIMEOUT,
    }

    with psycopg2.connect(**conn_params) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT to_regclass('free_games.last_notification')")
            if cursor.fetchone()[0] is None:
                raise RuntimeError(
                    "Required table free_games.last_notification is missing after migrations. "
                    "Run 'alembic upgrade head' and verify DB permissions."
                )

    logger.info("Required database tables verified successfully.")
