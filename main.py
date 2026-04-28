import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone

import psycopg2
import pytz
import requests
import schedule
from alembic.config import Config as AlembicConfig

from alembic import command as alembic_command
from config import (
    API_HOST,
    API_PORT,
    CHECK_INTERVAL_HOURS,
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_PORT,
    DB_USER,
    ENABLED_STORES,
    HEALTHCHECK_INTERVAL,
    SCHEDULE_TIME,
    TIMEZONE,
)
from modules.database import FreeGamesDatabase
from modules.healthcheck import healthcheck
from modules.logging_config import setup_logging
from modules.notifier import send_discord_message
from modules.scrapers import get_enabled_scrapers
from modules.storage import load_previous_games, save_games, save_last_notification

setup_logging(timezone=TIMEZONE, log_file="/mnt/logs/notifier.log")


# Filter that drops uvicorn access-log entries for the /health endpoint.
# The health endpoint is polled every minute by the scheduler and would otherwise
# flood the logs with noise that makes real entries harder to find.
class _HealthEndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # uvicorn formats access entries as: '<ip> - "GET /health HTTP/1.1" <status>'
        # Match on ' /health ' (space + path + space) to cover any HTTP method.
        return ' /health ' not in record.getMessage()


def _is_still_active(game) -> bool:
    """Return True if *game*'s promotion has not yet expired.

    Games with an empty or un-parseable end_date are treated as still-active to
    avoid false "new game" alerts caused by transient scraping failures.
    """
    end_date = game.end_date
    if not end_date:
        # Treat unknown end dates as active to avoid duplicate notifications.
        return True

    normalized = end_date.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    try:
        ends_at = datetime.fromisoformat(normalized)
    except ValueError:
        # Keep legacy/malformed records from causing false "new" alerts.
        return True

    if ends_at.tzinfo is None:
        ends_at = ends_at.replace(tzinfo=timezone.utc)

    return ends_at >= datetime.now(timezone.utc)


_RECENTLY_EXPIRED_GRACE_PERIOD_HOURS = 24


def _recently_expired_urls(previous_games) -> set[str]:
    """Return URLs whose promo expired within the last grace period.

    Steam (and other stores) occasionally return a wrong end_date for a game
    whose promo just ended (e.g. off-by-one year).  Without this guard,
    a URL that expired minutes ago would pass both the ``previous_active_urls``
    and ``previous_seen`` checks and trigger a duplicate notification.
    """
    now = datetime.now(timezone.utc)
    grace = timedelta(hours=_RECENTLY_EXPIRED_GRACE_PERIOD_HOURS)
    urls: set[str] = set()
    for game in previous_games:
        if not game.url or not game.end_date:
            continue
        normalized = game.end_date.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        try:
            ends_at = datetime.fromisoformat(normalized)
        except ValueError:
            continue
        if ends_at.tzinfo is None:
            ends_at = ends_at.replace(tzinfo=timezone.utc)
        if ends_at < now <= ends_at + grace:
            urls.add(game.url)
    return urls


def _find_new_games(current_games, previous_games):
    """Return games that are newly free compared to still-active previous promos.

    Three checks prevent duplicate notifications:

    1. ``previous_active_urls`` — URLs whose promos are still running.  A game
       whose URL is already active is suppressed regardless of its end_date.
    2. ``recently_expired_urls`` — URLs whose promo ended within the last
       ``_RECENTLY_EXPIRED_GRACE_PERIOD_HOURS`` hours.  This prevents a store
       returning a bad end_date (e.g. wrong year) right after expiry from
       triggering a re-notification for the same promotion.
    3. ``previous_seen`` — (url, end_date) pairs ever persisted.  Prevents
       re-notification for an expired promo even if the URL no longer appears
       in the active set.

    A game that passes *all* checks is genuinely new or has started a fresh
    promo with a different end_date after the grace period.

    Same-run deduplication: ``notified_urls`` tracks URLs already added to
    ``new_games`` in this loop so that a URL appearing twice in ``current_games``
    (e.g. duplicate search-result rows) is only notified once.
    """
    # A (url, end_date) pair that already appeared in previous games should not
    # trigger a new notification, regardless of whether the promo is still active.
    # This prevents re-notifying for the same expired promo while still allowing
    # re-notification when the same game has a new promo (different end_date).
    previous_seen = {
        (game.url, game.end_date)
        for game in previous_games
        if game.url
    }

    # Also track active URLs to suppress games seen before whose promos are still running.
    previous_active_urls = {
        game.url
        for game in previous_games
        if game.url and _is_still_active(game)
    }

    # Suppress re-notification for URLs whose promo just expired — store data
    # errors (e.g. Steam returning a wrong year) would otherwise bypass both
    # previous_active_urls and previous_seen when the end_date differs.
    recently_expired = _recently_expired_urls(previous_games)

    new_games = []
    notified_urls: set[str] = set()
    for game in current_games:
        url = game.url
        if url:
            if (
                url not in previous_active_urls
                and url not in recently_expired
                and (url, game.end_date) not in previous_seen
                and url not in notified_urls
            ):
                new_games.append(game)
                notified_urls.add(url)
            continue

        # Fallback for malformed records that do not have a url.
        if game not in previous_games:
            new_games.append(game)

    return new_games

def check_games():

    """Main execution function that checks for new free games and sends Discord notification."""
    logging.info("Checking for new free games...")

    scrapers = get_enabled_scrapers(ENABLED_STORES)
    logging.info(
        "Running %d enabled scraper(s): %s",
        len(scrapers),
        [s.store_name for s in scrapers],
    )

    current_games = []
    for scraper in scrapers:
        store = scraper.store_name
        try:
            store_games = scraper.fetch_free_games()
            logging.info(f"Games obtained from {store} scraper: {len(store_games)} game(s)")
            current_games.extend(store_games)
        except Exception as e:
            # Isolate failures so one broken store does not prevent others from running.
            logging.error(f"Failed to fetch games from {store} scraper: {str(e)}")
            continue

    if current_games == []:
        logging.error("No free games found or failed to fetch.")
        return

    try:
        previous_games = load_previous_games()
        logging.info(f"Previous games loaded from storage: {previous_games} game(s)")
    except Exception as e:
        logging.error(f"Failed to load previous games: {str(e)}")
        return

    new_games = _find_new_games(current_games, previous_games)

    if new_games:
        logging.info(f"Found {len(new_games)} new free games! Sending Discord notification...")

        # Wrap Discord send with try-except to prevent scheduler crash
        try:
            send_discord_message(new_games)
            logging.info("Discord notification sent successfully")
        except ValueError as e:
            logging.error(f"Discord error (ValueError) while sending message: {str(e)}")
            logging.warning("Discord notification failed due to a ValueError, but continuing scheduler. Investigate the underlying cause (configuration or data-related).")
            # Don't save games if Discord notification fails
            return
        except requests.exceptions.RequestException as e:
            logging.error(f"Discord request failed (network/HTTP error): {str(e)} | Games to notify: {len(new_games)}")
            logging.warning("Discord notification failed due to network issue, but continuing scheduler.")
            # Don't save games if Discord notification fails
            return
        except Exception as e:
            logging.error(f"Unexpected error sending Discord message: {str(e)} | Games to notify: {len(new_games)}")
            logging.warning("Discord notification failed unexpectedly, but continuing scheduler.")
            # Don't save games if Discord notification fails
            return

        # Persist the last notification batch so the resend endpoint can replay it
        try:
            save_last_notification(new_games)
        except Exception as e:
            logging.error(f"Failed to save last notification: {str(e)}")
            logging.warning("Discord notification was sent but failed to record it for the resend endpoint.")

    else:
        logging.warning("No new free games detected.")

    # Always persist so that the DB upsert keeps end_date values fresh, preventing
    # stale promos from triggering false re-notifications.
    #
    # Guard against scraper failures causing re-notifications: if an enabled store
    # returned no games this run (network error, rate-limit, or a genuinely empty
    # day), its previously-stored still-active games would be erased from storage.
    # The next run that does return those games would then treat them as new and
    # send a duplicate Discord notification.  To prevent this, we carry forward
    # still-active previous games from any store that produced no results.
    stores_with_results = {g.store for g in current_games}
    preserved = [
        g for g in previous_games
        if g.store not in stores_with_results and _is_still_active(g)
    ]
    if preserved:
        logging.info(
            "Carrying forward %d still-active game(s) from store(s) with no results "
            "this run to prevent duplicate notifications: %s",
            len(preserved),
            [g.title for g in preserved],
        )
    games_to_save = current_games + preserved

    try:
        save_games(games_to_save)
        logging.info("Games saved successfully to storage")
    except IOError as e:
        logging.error(f"Failed to save games to storage: {str(e)}")
        logging.warning("Failed to update local cache. This may cause duplicate notifications next run.")
    except Exception as e:
        logging.error(f"Unexpected error saving games: {str(e)}")
        logging.warning("Failed to update local cache.")

def _run_db_migrations():
    """Apply any pending Alembic migrations up to the latest revision."""
    logging.info("Applying database migrations...")
    # Suppress verbose per-revision Alembic log lines from service logs.
    # env.py skips fileConfig when the service's logging is already configured,
    # but raise the level here as well to guard against any propagation.
    logging.getLogger("alembic").setLevel(logging.WARNING)
    cfg = AlembicConfig(os.path.join(os.path.dirname(__file__), "alembic.ini"))
    alembic_command.upgrade(cfg, "head")
    logging.info("Database migrations applied successfully.")


def _verify_required_tables():
    """Fail fast when required DB tables are missing after migrations."""
    logging.info("Verifying required database tables...")

    conn_params = {
        "host": DB_HOST,
        "port": DB_PORT,
        "dbname": DB_NAME,
        "user": DB_USER,
        "password": DB_PASSWORD,
    }

    with psycopg2.connect(**conn_params) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT to_regclass('free_games.last_notification')")
            if cursor.fetchone()[0] is None:
                raise RuntimeError(
                    "Required table free_games.last_notification is missing after migrations. "
                    "Run 'alembic upgrade head' and verify DB permissions."
                )

    logging.info("Required database tables verified successfully.")


def _start_api_server():
    """Start the FastAPI server in a background daemon thread."""
    import uvicorn

    from api import app

    # Silence /health access-log noise before uvicorn starts so the filter
    # is already registered on the logger object uvicorn will use.
    logging.getLogger("uvicorn.access").addFilter(_HealthEndpointFilter())

    logging.info("Starting REST API server on %s:%s...", API_HOST, API_PORT)
    uvicorn.run(app, host=API_HOST, port=API_PORT, log_level="info")


def main():
    if DB_HOST:
        logging.info("Database configuration detected. Initializing database...")
        db = FreeGamesDatabase()
        db.init_db()
        _run_db_migrations()
        _verify_required_tables()
    else:
        logging.info("No database configuration detected. Using JSON file storage.")

    # Start REST API server in a background thread
    api_thread = threading.Thread(target=_start_api_server, daemon=True)
    api_thread.start()

    check_games()
    healthcheck()

    logging.debug("Starting scheduler...")

    if CHECK_INTERVAL_HOURS is not None:
        # Interval mode: check every N hours regardless of time of day.
        # Ideal for multi-store setups where Steam games can appear at any time.
        logging.info(
            "Scheduling game checks every %.4g hour(s) (CHECK_INTERVAL_HOURS=%s).",
            CHECK_INTERVAL_HOURS,
            CHECK_INTERVAL_HOURS,
        )
        schedule.every(CHECK_INTERVAL_HOURS).hours.do(check_games)
    else:
        # Daily mode: check once per day at the configured time (legacy default).
        logging.info(
            "Scheduling game checks once daily at %s %s (SCHEDULE_TIME=%s).",
            SCHEDULE_TIME,
            TIMEZONE,
            SCHEDULE_TIME,
        )
        schedule.every().day.at(SCHEDULE_TIME, tz=TIMEZONE).do(check_games)

    schedule.every(HEALTHCHECK_INTERVAL).minutes.do(healthcheck)

    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    logging.info("Starting service...")
    main()
