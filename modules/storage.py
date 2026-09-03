import json
import logging
import os

from config import DATA_FILE_PATH, DB_HOST, LAST_NOTIFICATION_FILE_PATH
from modules.models import FreeGame

logger = logging.getLogger(__name__)


def _is_db_configured():
    """Return True when DB_HOST is configured (PostgreSQL backend enabled)."""
    return bool(DB_HOST)


# ---------------------------------------------------------------------------
# Public interface (used by main.py)
# ---------------------------------------------------------------------------

def load_previous_games(*, strict: bool = False):
    """
    Load the last known free games from the configured storage backend.

    Uses PostgreSQL when DB_HOST is set, otherwise falls back to the JSON file.

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
    if _is_db_configured():
        return _load_from_db(strict=strict)
    return _load_from_file(strict=strict)


def save_games(games):
    """
    Save the current free games list to the configured storage backend.

    Uses PostgreSQL when DB_HOST is set, otherwise falls back to the JSON file.

    Args:
        games: List of game dictionaries to save.

    Raises:
        IOError: If the save operation fails.
        TypeError: If games data cannot be serialised (file backend only).
    """
    if _is_db_configured():
        _save_to_db(games)
    else:
        _save_to_file(games)


def save_last_notification(games):
    """
    Persist the games that were included in the most recent Discord notification.

    Uses PostgreSQL when DB_HOST is set, otherwise falls back to a JSON file.

    Args:
        games: List of game dictionaries that were sent in the notification.
    """
    if not games:
        logger.debug("save_last_notification called with empty list; skipping")
        return
    if _is_db_configured():
        _save_last_notification_to_db(games)
    else:
        _save_last_notification_to_file(games)


def load_last_notification():
    """
    Load the games that were included in the most recent Discord notification.

    Uses PostgreSQL when DB_HOST is set, otherwise falls back to a JSON file.

    Returns:
        list: Games from the last notification, or empty list if none recorded yet.
    """
    if _is_db_configured():
        return _load_last_notification_from_db()
    return _load_last_notification_from_file()


# ---------------------------------------------------------------------------
# PostgreSQL backend
# ---------------------------------------------------------------------------

def _load_from_db(*, strict: bool = False):
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


def _save_to_db(games):
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


def _save_last_notification_to_db(games):
    from modules.database import FreeGamesDatabase
    try:
        db = FreeGamesDatabase()
        db.save_last_notification(games)
    except Exception as e:
        logger.error(f"Failed to save last notification to database: {e}")
        raise IOError("Failed to save last notification to database") from e


def _load_last_notification_from_db():
    from modules.database import FreeGamesDatabase
    try:
        db = FreeGamesDatabase()
        games = db.get_last_notification()
        logger.debug(f"Loaded {len(games)} games from last_notification table.")
        return games
    except Exception as e:
        logger.error(f"Failed to load last notification from database: {e}")
        return []


# ---------------------------------------------------------------------------
# JSON file backend (development / fallback when DB_HOST is not set)
# ---------------------------------------------------------------------------

def _load_from_file(*, strict: bool = False):
    """
    Load the last known free games from file.

    Returns:
        list: Previously saved games as FreeGame objects, or empty list if file doesn't exist or is corrupted
            (unless strict=True, in which case corruption/IO errors raise instead of returning []).
    """
    if not os.path.exists(DATA_FILE_PATH):
        # Legitimately empty state (first run) — not an error, so this is
        # never raised even in strict mode.
        logger.debug(f"Data file does not exist yet: {DATA_FILE_PATH}")
        return []

    try:
        with open(DATA_FILE_PATH, "r") as file:
            data = json.load(file)

            # Validate that the loaded data is a list
            if not isinstance(data, list):
                logger.error(
                    f"Unexpected JSON structure in data file: expected list, got {type(data).__name__} | "
                    f"File path: {DATA_FILE_PATH}"
                )
                if strict:
                    raise ValueError(f"Unexpected JSON structure in data file: expected list, got {type(data).__name__}")
                logger.warning("Returning empty list due to invalid JSON structure to prevent incorrect processing.")
                return []

            if not all(isinstance(game, dict) for game in data):
                logger.error(
                    f"Unexpected item types in games list from data file. "
                    f"Expected list of dicts. File path: {DATA_FILE_PATH}"
                )
                if strict:
                    raise ValueError("Unexpected item types in games list from data file: expected list of dicts")
                logger.warning("Returning empty list due to invalid game entries to prevent incorrect processing.")
                return []

            games = [FreeGame.from_dict(game) for game in data]
            logger.debug(f"Successfully loaded {len(games)} previous games from {DATA_FILE_PATH}")
            return games
    except FileNotFoundError:
        logger.error(f"Data file not found when attempting to read: {DATA_FILE_PATH}")
        if strict:
            raise
        return []
    except IOError as e:
        logger.error(f"I/O error reading data file: {str(e)} | File path: {DATA_FILE_PATH}")
        if strict:
            raise
        return []
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error in data file: {str(e)} | File path: {DATA_FILE_PATH} | Line: {e.lineno}, Column: {e.colno}")
        if strict:
            raise
        logger.warning("Returning empty list to prevent scheduler crash. File may be corrupted.")
        return []
    except Exception as e:
        logger.error(f"Unexpected error loading previous games: {str(e)} | File path: {DATA_FILE_PATH}")
        if strict:
            raise
        return []


def _save_to_file(games):
    """
    Save the current free games list to file.

    Args:
        games: List of FreeGame objects to save.

    Raises:
        IOError: If file write fails due to I/O issues.
        TypeError: If games data cannot be serialized to JSON.
    """
    if not games:
        logger.warning("Attempted to save empty games list")
        return

    try:
        # Ensure directory exists
        directory = os.path.dirname(DATA_FILE_PATH)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)
            logger.debug(f"Created directory: {directory}")

        serializable = [g.to_dict() for g in games]
        with open(DATA_FILE_PATH, "w") as file:
            json.dump(serializable, file, indent=4)
            logger.info(f"Successfully saved {len(games)} games to {DATA_FILE_PATH}")

    except PermissionError as e:
        logger.error(f"Permission denied writing to data file: {str(e)} | File path: {DATA_FILE_PATH}")
        logger.warning("File save failed due to permission issues. Scheduler will continue.")
        raise IOError(f"Permission denied saving games to {DATA_FILE_PATH}") from e
    except IOError as e:
        logger.error(f"I/O error writing data file: {str(e)} | File path: {DATA_FILE_PATH}")
        logger.warning("File save failed. Scheduler will continue.")
        raise
    except TypeError as e:
        logger.error(f"JSON serialization error: {str(e)} | Games data type: {type(games)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error saving games: {str(e)} | File path: {DATA_FILE_PATH}")
        raise IOError("Unexpected error saving games") from e


def _save_last_notification_to_file(games):
    """Persist the last notification batch to a JSON file."""
    try:
        directory = os.path.dirname(LAST_NOTIFICATION_FILE_PATH)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)
        serializable = [g.to_dict() for g in games]
        with open(LAST_NOTIFICATION_FILE_PATH, "w") as f:
            json.dump(serializable, f, indent=4)
        logger.info(f"Saved {len(games)} games to last notification file.")
    except TypeError as e:
        logger.error(
            f"JSON serialization error saving last notification: {e} | "
            f"Games data type: {type(games)}"
        )
        raise
    except PermissionError as e:
        logger.error(
            f"Permission denied saving last notification to file: {e} | "
            f"File path: {LAST_NOTIFICATION_FILE_PATH}"
        )
        raise IOError("Failed to save last notification to file") from e
    except (IOError, OSError) as e:
        logger.error(
            f"I/O error saving last notification to file: {e} | "
            f"File path: {LAST_NOTIFICATION_FILE_PATH}"
        )
        raise IOError("Failed to save last notification to file") from e


def _load_last_notification_from_file():
    """Load the last notification batch from the JSON file."""
    if not os.path.exists(LAST_NOTIFICATION_FILE_PATH):
        logger.debug(f"Last notification file does not exist yet: {LAST_NOTIFICATION_FILE_PATH}")
        return []
    try:
        with open(LAST_NOTIFICATION_FILE_PATH, "r") as f:
            data = json.load(f)
        if not isinstance(data, list):
            logger.error("Unexpected structure in last notification file: expected list")
            return []
        if not all(isinstance(game, dict) for game in data):
            logger.error("Unexpected item types in last notification file: expected list of dicts")
            return []
        games = [FreeGame.from_dict(game) for game in data]
        logger.debug(f"Loaded {len(games)} games from last notification file.")
        return games
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error in last notification file: {e}")
        return []
    except IOError as e:
        logger.error(f"I/O error reading last notification file: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error loading last notification from file: {e}")
        return []
