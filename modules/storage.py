import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public interface (used by main.py and the REST API)
#
# PostgreSQL is the only storage backend. This module exists as a thin,
# stable seam between the rest of the codebase and modules.database, so
# callers don't need to know about FreeGamesDatabase.
# ---------------------------------------------------------------------------

def load_previous_games(*, strict: bool = False):
    """
    Load the last known free games from the database.

    Args:
        strict: When False (default), storage errors are swallowed and an
            empty list is returned, same as "no games yet" — this is what
            the scheduler and the read-only game endpoints want, since they
            already handle an empty result gracefully. When True, storage
            errors are re-raised instead, for callers (e.g. the dashboard
            summary endpoint) that must not report a fabricated zero when
            storage is actually unreachable.

    Returns:
        list: Previously saved games, or empty list on error / first run
            (unless strict=True, in which case errors propagate).
    """
    from modules.database import FreeGamesDatabase
    try:
        db = FreeGamesDatabase()
        games = db.get_games()
        logger.debug(f"Loaded {len(games)} previous games from database.")
        return games
    except Exception as e:
        logger.error(f"Failed to load games from database: {e}")
        if strict:
            raise
        return []


def save_games(games):
    """
    Save the current free games list to the database.

    Args:
        games: List of FreeGame objects to save.

    Raises:
        IOError: If the save operation fails.
    """
    from modules.database import FreeGamesDatabase
    if not games:
        logger.warning("Attempted to save empty games list")
        return
    try:
        db = FreeGamesDatabase()
        db.save_games(games)
    except Exception as e:
        logger.error(f"Failed to save games to database: {e}")
        raise IOError("Failed to save games to database") from e


def save_last_notification(games):
    """
    Persist the games that were included in the most recent Discord notification.

    Args:
        games: List of FreeGame objects that were sent in the notification.
    """
    from modules.database import FreeGamesDatabase
    if not games:
        logger.debug("save_last_notification called with empty list; skipping")
        return
    try:
        db = FreeGamesDatabase()
        db.save_last_notification(games)
    except Exception as e:
        logger.error(f"Failed to save last notification to database: {e}")
        raise IOError("Failed to save last notification to database") from e


def load_last_notification():
    """
    Load the games that were included in the most recent Discord notification.

    Returns:
        list: Games from the last notification, or empty list if none recorded yet.
    """
    from modules.database import FreeGamesDatabase
    try:
        db = FreeGamesDatabase()
        games = db.get_last_notification()
        logger.debug(f"Loaded {len(games)} games from last_notification table.")
        return games
    except Exception as e:
        logger.error(f"Failed to load last notification from database: {e}")
        return []
