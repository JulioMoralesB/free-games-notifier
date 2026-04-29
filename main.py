import logging
import threading
import time

import requests
import schedule

from config import (
    API_HOST,
    API_PORT,
    CHECK_INTERVAL_HOURS,
    DB_HOST,
    ENABLED_STORES,
    HEALTHCHECK_INTERVAL,
    SCHEDULE_TIME,
    TIMEZONE,
)
from modules.database import FreeGamesDatabase
from modules.db_lifecycle import run_db_migrations, verify_required_tables
from modules.dedupe import find_new_games, is_still_active
from modules.healthcheck import healthcheck
from modules.logging_config import setup_logging
from modules.notifier import send_discord_message
from modules.scrapers import get_enabled_scrapers
from modules.storage import load_previous_games, save_games, save_last_notification

setup_logging(timezone=TIMEZONE, log_file="/mnt/logs/notifier.log")

logger = logging.getLogger(__name__)


# Filter that drops uvicorn access-log entries for the /health endpoint.
# The health endpoint is polled every minute by the scheduler and would otherwise
# flood the logs with noise that makes real entries harder to find.
class _HealthEndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # uvicorn formats access entries as: '<ip> - "GET /health HTTP/1.1" <status>'
        # Match on ' /health ' (space + path + space) to cover any HTTP method.
        return ' /health ' not in record.getMessage()


def check_games():
    """Main execution function that checks for new free games and sends Discord notification."""
    logger.info("Checking for new free games...")

    scrapers = get_enabled_scrapers(ENABLED_STORES)
    logger.info(
        "Running %d enabled scraper(s): %s",
        len(scrapers),
        [s.store_name for s in scrapers],
    )

    current_games = []
    for scraper in scrapers:
        store = scraper.store_name
        try:
            store_games = scraper.fetch_free_games()
            logger.info("Games obtained from %s scraper: %d game(s)", store, len(store_games))
            current_games.extend(store_games)
        except Exception as e:
            # Isolate failures so one broken store does not prevent others from running.
            logger.error("Failed to fetch games from %s scraper: %s", store, e)
            continue

    if current_games == []:
        logger.error("No free games found or failed to fetch.")
        return

    try:
        previous_games = load_previous_games()
        logger.info("Previous games loaded from storage: %s game(s)", previous_games)
    except Exception as e:
        logger.error("Failed to load previous games: %s", e)
        return

    new_games = find_new_games(current_games, previous_games)

    if new_games:
        logger.info("Found %d new free games! Sending Discord notification...", len(new_games))

        # Wrap Discord send with try-except to prevent scheduler crash
        try:
            send_discord_message(new_games)
            logger.info("Discord notification sent successfully")
        except ValueError as e:
            logger.error("Discord error (ValueError) while sending message: %s", e)
            logger.warning("Discord notification failed due to a ValueError, but continuing scheduler. Investigate the underlying cause (configuration or data-related).")
            # Don't save games if Discord notification fails
            return
        except requests.exceptions.RequestException as e:
            logger.error("Discord request failed (network/HTTP error): %s | Games to notify: %d", e, len(new_games))
            logger.warning("Discord notification failed due to network issue, but continuing scheduler.")
            # Don't save games if Discord notification fails
            return
        except Exception as e:
            logger.error("Unexpected error sending Discord message: %s | Games to notify: %d", e, len(new_games))
            logger.warning("Discord notification failed unexpectedly, but continuing scheduler.")
            # Don't save games if Discord notification fails
            return

        # Persist the last notification batch so the resend endpoint can replay it
        try:
            save_last_notification(new_games)
        except Exception as e:
            logger.error("Failed to save last notification: %s", e)
            logger.warning("Discord notification was sent but failed to record it for the resend endpoint.")

    else:
        logger.warning("No new free games detected.")

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
        if g.store not in stores_with_results and is_still_active(g)
    ]
    if preserved:
        logger.info(
            "Carrying forward %d still-active game(s) from store(s) with no results "
            "this run to prevent duplicate notifications: %s",
            len(preserved),
            [g.title for g in preserved],
        )
    games_to_save = current_games + preserved

    try:
        save_games(games_to_save)
        logger.info("Games saved successfully to storage")
    except IOError as e:
        logger.error("Failed to save games to storage: %s", e)
        logger.warning("Failed to update local cache. This may cause duplicate notifications next run.")
    except Exception as e:
        logger.error("Unexpected error saving games: %s", e)
        logger.warning("Failed to update local cache.")


def _start_api_server():
    """Start the FastAPI server in a background daemon thread."""
    import uvicorn

    from api import app

    # Silence /health access-log noise before uvicorn starts so the filter
    # is already registered on the logger object uvicorn will use.
    logging.getLogger("uvicorn.access").addFilter(_HealthEndpointFilter())

    logger.info("Starting REST API server on %s:%s...", API_HOST, API_PORT)
    uvicorn.run(app, host=API_HOST, port=API_PORT, log_level="info")


def main():
    if DB_HOST:
        logger.info("Database configuration detected. Initializing database...")
        db = FreeGamesDatabase()
        db.init_db()
        run_db_migrations()
        verify_required_tables()
    else:
        logger.info("No database configuration detected. Using JSON file storage.")

    # Start REST API server in a background thread
    api_thread = threading.Thread(target=_start_api_server, daemon=True)
    api_thread.start()

    check_games()
    healthcheck()

    logger.debug("Starting scheduler...")

    if CHECK_INTERVAL_HOURS is not None:
        # Interval mode: check every N hours regardless of time of day.
        # Ideal for multi-store setups where Steam games can appear at any time.
        logger.info(
            "Scheduling game checks every %.4g hour(s) (CHECK_INTERVAL_HOURS=%s).",
            CHECK_INTERVAL_HOURS,
            CHECK_INTERVAL_HOURS,
        )
        schedule.every(CHECK_INTERVAL_HOURS).hours.do(check_games)
    else:
        # Daily mode: check once per day at the configured time (legacy default).
        logger.info(
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
    logger.info("Starting service...")
    main()
