import logging
from urllib.parse import urlparse

import requests

from config import ENABLE_HEALTHCHECK, HEALTHCHECK_URL

logger = logging.getLogger(__name__)

HEARTBEAT_TIMEOUT = 10  # seconds


def _safe_monitor_location(url):
    """Return `host:port` (or `host`) for *url*, safe to log.

    UptimeKuma-style push URLs carry the push token in the path itself
    (``/api/push/<token>``), so anything beyond scheme/host/port -- including
    the exception objects raised by requests/urllib3, whose string form
    embeds the full URL -- must never be logged.
    """
    parsed = urlparse(url or "")
    if not parsed.hostname:
        return "unconfigured-monitor"
    return f"{parsed.hostname}:{parsed.port}" if parsed.port else parsed.hostname


# Sends a heartbeat to a monitor service like UptimeKuma so it knows this service is
# alive. This is fire-and-forget: it must never affect this service's own health,
# restart behavior, or exit status, so any failure is caught, logged, and swallowed
# rather than propagated (an uncaught exception here would crash the `schedule`
# loop in main.py, which has no exception handling of its own, and take the whole
# process down with it).
def healthcheck():
    if not ENABLE_HEALTHCHECK:
        logger.debug("Healthcheck is disabled. Skipping healthcheck.")
        return
    monitor = _safe_monitor_location(HEALTHCHECK_URL)
    try:
        logger.debug(f"Sending heartbeat to monitor at {monitor}")
        response = requests.get(HEALTHCHECK_URL, timeout=HEARTBEAT_TIMEOUT)
        logger.debug(f"Received response from monitor. Status Code: {response.status_code}")
        response_json = response.json()
        ok_value = response_json.get("ok")

        logger.debug(f"Ok value: {ok_value}")

        if response.status_code != 200 or ok_value not in [True, 'true']:
            logger.error(f"Unexpected response from monitor at {monitor}: status={response.status_code}")
            return
        logger.debug("Obtained 200 status code from monitor response. Service is healthy")
    except Exception as e:
        # Never interpolate the exception itself: requests/urllib3 embed the
        # full request URL (and therefore the push token) in their exception
        # messages. The exception's type name is diagnosable without it.
        logger.error(f"Failed to push heartbeat to {monitor}: {type(e).__name__}")
