import logging

import requests

from config import ENABLE_HEALTHCHECK, HEALTHCHECK_URL

logger = logging.getLogger(__name__)

# Sends a hearthbeat to a monitor service like UptimeKuma to ensure that the service is running and healthy
def healthcheck():
    if not ENABLE_HEALTHCHECK:
        logger.debug("Healthcheck is disabled. Skipping healthcheck.")
        return
    logger.debug(f"Sending request to healthcheck monitor. URL: {HEALTHCHECK_URL}")
    response = requests.get(HEALTHCHECK_URL)
    logger.debug(f"Received response from monitor. Status Code: {response.status_code}")
    response_json = response.json()
    ok_value = response_json.get("ok")

    logger.debug(f"Ok value: {ok_value}")

    if response.status_code != 200 or ok_value not in [True, 'true']:
        logger.error(f"Failed to get response from monitor. Status Code: {response.status_code}")
        return
    logger.debug("Obtained 200 status code from monitor response. Service is healthy")
