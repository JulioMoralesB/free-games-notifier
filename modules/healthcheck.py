import logging

import requests

from config import ENABLE_HEALTHCHECK, HEALTHCHECK_URL

logger = logging.getLogger(__name__)

HEARTBEAT_TIMEOUT = 10  # seconds

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
    try:
        logger.debug(f"Sending request to healthcheck monitor. URL: {HEALTHCHECK_URL}")
        response = requests.get(HEALTHCHECK_URL, timeout=HEARTBEAT_TIMEOUT)
        logger.debug(f"Received response from monitor. Status Code: {response.status_code}")
        response_json = response.json()
        ok_value = response_json.get("ok")

        logger.debug(f"Ok value: {ok_value}")

        if response.status_code != 200 or ok_value not in [True, 'true']:
            logger.error(f"Failed to get response from monitor. Status Code: {response.status_code}")
            return
        logger.debug("Obtained 200 status code from monitor response. Service is healthy")
    except Exception as e:
        logger.error(f"Failed to push heartbeat to monitor: {e}")
