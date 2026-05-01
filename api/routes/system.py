"""System endpoints: /health, /metrics, /config."""

import logging

import requests
from fastapi import APIRouter, Security

from api import metrics
from api.auth import verify_api_key
from api.schemas import ConfigResponse, ErrorResponse, HealthResponse, MetricsResponse
from config import (
    DATA_FILE_PATH,
    DATE_FORMAT,
    DB_CONNECT_TIMEOUT,
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_PORT,
    DB_USER,
    ENABLE_HEALTHCHECK,
    EPIC_GAMES_API_URL,
    EPIC_GAMES_REGION,
    HEALTHCHECK_INTERVAL,
    HEALTHCHECK_URL,
    LOCALE,
    SCHEDULE_TIME,
    TIMEZONE,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health():
    """Active health check: Epic Games API reachability and database connectivity."""
    result = {"epic_games_api": "unknown", "database": "not_configured"}

    # Check Epic Games API
    try:
        resp = requests.get(EPIC_GAMES_API_URL, timeout=10)
        result["epic_games_api"] = "healthy" if resp.status_code == 200 else "unhealthy"
    except Exception:
        result["epic_games_api"] = "unhealthy"

    # Check database if configured
    if DB_HOST:
        try:
            import psycopg2
            conn = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                dbname=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD,
                connect_timeout=DB_CONNECT_TIMEOUT,
            )
            conn.close()
            result["database"] = "healthy"
        except Exception:
            result["database"] = "unhealthy"

    overall = "healthy"
    if result["epic_games_api"] != "healthy":
        overall = "unhealthy"
    if DB_HOST and result["database"] != "healthy":
        overall = "unhealthy"
    result["status"] = overall
    return result


@router.get("/metrics", response_model=MetricsResponse)
def metrics_endpoint():
    """Basic service metrics: uptime, games processed, notifications sent, errors."""
    return {
        "uptime_seconds": round(metrics.get_uptime_seconds(), 2),
        **metrics.snapshot(),
    }


@router.get(
    "/config",
    response_model=ConfigResponse,
    # API key verification protects both mutating endpoints and sensitive
    # read endpoints such as `/config`.
    dependencies=[Security(verify_api_key)],
    responses={
        401: {"model": ErrorResponse, "description": "Invalid or missing API key"},
    },
)
def config_endpoint():
    """Expose non-secret runtime configuration. Protected by the API key."""
    return {
        "epic_games_api_url": EPIC_GAMES_API_URL,
        "epic_games_region": EPIC_GAMES_REGION,
        "data_file_path": DATA_FILE_PATH,
        "enable_healthcheck": ENABLE_HEALTHCHECK,
        "healthcheck_configured": bool(HEALTHCHECK_URL),
        "healthcheck_interval_minutes": HEALTHCHECK_INTERVAL,
        "db_host": DB_HOST,
        "db_port": DB_PORT,
        "db_name": DB_NAME,
        "db_user": DB_USER,
        "timezone": TIMEZONE,
        "locale": LOCALE,
        "schedule_time": SCHEDULE_TIME,
        "date_format": DATE_FORMAT,
    }
