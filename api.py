"""REST API for the Free Games Notifier service."""

import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import List, Optional

import requests as requests_lib
from fastapi import FastAPI, HTTPException, Query, Security
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from config import (
    API_KEY,
    DATA_FILE_PATH,
    DATE_FORMAT,
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_PORT,
    DB_USER,
    ENABLE_HEALTHCHECK,
    ENABLED_STORES,
    EPIC_GAMES_API_URL,
    EPIC_GAMES_REGION,
    HEALTHCHECK_INTERVAL,
    HEALTHCHECK_URL,
    LOCALE,
    SCHEDULE_TIME,
    TIMEZONE,
)
from modules.models import FreeGame
from modules.notifier import validate_discord_webhook_url

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic response models (for OpenAPI / Swagger documentation)
# ---------------------------------------------------------------------------


class GameItem(BaseModel):
    """A free game as returned by the scraper."""
    title: str = Field(..., description="Name of the free game", examples=["Celeste"])
    store: str = Field("epic", description="Store identifier where the game is offered for free", examples=["epic", "steam"])
    link: str = Field(..., description="Store URL for the game")
    end_date: str = Field(..., description="ISO-8601 timestamp when the free promotion ends", examples=["2024-01-31T15:00:00.000Z"])
    description: str = Field(..., description="Short description of the game")
    thumbnail: str = Field(..., description="URL to the game's thumbnail image")
    game_type: str = Field("game", description="Content type: 'game' or 'dlc'", examples=["game", "dlc"])
    original_price: Optional[str] = Field(default=None, description="Original retail price before the free promotion", examples=["$19.99", "€14.99"])
    review_scores: List[str] = Field(default_factory=list, description="Review scores from available sources", examples=[["Very Positive", "Metascore: 83"]])


class HealthResponse(BaseModel):
    """Response from the health check endpoint."""
    status: str = Field(..., description="Overall health status", examples=["healthy", "unhealthy"])
    epic_games_api: str = Field(..., description="Epic Games API reachability", examples=["healthy", "unhealthy"])
    database: str = Field(..., description="Database connectivity status", examples=["healthy", "unhealthy", "not_configured"])


class GamesLatestResponse(BaseModel):
    """Response from the latest games endpoint."""
    games: List[GameItem] = Field(..., description="List of the most recently fetched games")
    count: int = Field(..., description="Number of games returned", examples=[3])


class GamesHistoryResponse(BaseModel):
    """Response from the paginated game history endpoint."""
    games: List[GameItem] = Field(..., description="List of games for the current page")
    total: int = Field(..., description="Total number of games in storage", examples=[42])
    limit: int = Field(..., description="Maximum number of games per page", examples=[20])
    offset: int = Field(..., description="Number of games skipped", examples=[0])


class ResendResponse(BaseModel):
    """Response after re-sending a Discord notification."""
    status: str = Field(..., description="Result of the operation", examples=["success"])
    games_sent: int = Field(..., description="Number of games included in the notification", examples=[2])


class MetricsResponse(BaseModel):
    """Service metrics snapshot."""
    uptime_seconds: float = Field(..., description="Seconds since the API server started", examples=[3600.5])
    games_processed: int = Field(..., description="Total games processed since startup", examples=[12])
    discord_notifications_sent: int = Field(..., description="Successful Discord notifications sent", examples=[5])
    discord_notification_errors: int = Field(..., description="Failed Discord notification attempts", examples=[1])
    errors: int = Field(..., description="Total error count across all operations", examples=[2])


class ConfigResponse(BaseModel):
    """Non-secret runtime configuration."""
    epic_games_api_url: str = Field(..., description="Epic Games API endpoint URL")
    epic_games_region: str = Field(..., description="Region code used in store links", examples=["en-US"])
    data_file_path: str = Field(..., description="Path to the JSON storage file")
    enable_healthcheck: bool = Field(..., description="Whether the external health check ping is enabled")
    healthcheck_configured: bool = Field(..., description="Whether an external health check monitor URL is configured")
    healthcheck_interval_minutes: int = Field(..., description="Interval in minutes between health check pings", examples=[1])
    db_host: Optional[str] = Field(None, description="PostgreSQL host (None when DB is not configured)")
    db_port: int = Field(..., description="PostgreSQL port", examples=[5432])
    db_name: Optional[str] = Field(None, description="PostgreSQL database name")
    db_user: Optional[str] = Field(None, description="PostgreSQL user")
    timezone: str = Field(..., description="Configured timezone for date display", examples=["UTC"])
    locale: str = Field(..., description="Locale used for date formatting", examples=["en_US.UTF-8"])
    schedule_time: str = Field(..., description="Daily check time in HH:MM format", examples=["12:00"])
    date_format: str = Field(..., description="strftime format string for promotion end dates")


class CheckE2EResponse(BaseModel):
    """Response from the end-to-end check endpoint."""
    games_fetched: int = Field(..., description="Number of free games fetched from all enabled stores", examples=[2])
    games: List[GameItem] = Field(..., description="Full list of fetched game objects")
    already_in_storage: List[str] = Field(..., description="Titles of games that were already saved in storage")
    new_games: List[str] = Field(..., description="Titles of games not yet in storage")
    notification_status: str = Field(..., description="Discord notification result", examples=["sent", "skipped", "failed: ..."])


class ErrorResponse(BaseModel):
    """Standard error response."""
    detail: str = Field(..., description="Human-readable error message")


class WebhookOverrideRequest(BaseModel):
    """Optional request body for Discord notification endpoints.

    Allows callers to specify an alternative Discord webhook URL so that
    test/E2E runs can target a non-default channel without changing global
    configuration.  The ``webhook_url`` field is validated to allow only
    legitimate Discord webhook URLs, preventing SSRF attacks.
    """

    webhook_url: Optional[str] = Field(
        None,
        description=(
            "Override Discord webhook URL for this request. "
            "Must be a valid Discord webhook URL "
            "(https://discord.com/api/webhooks/... or https://discordapp.com/api/webhooks/...)."
        ),
    )

    @field_validator("webhook_url")
    @classmethod
    def _validate_webhook_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None

        v_stripped = v.strip()
        if not v_stripped:
            raise ValueError("webhook_url must not be empty or whitespace")

        validate_discord_webhook_url(v_stripped)
        return v_stripped


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _to_game_item_dict(game) -> dict:
    """Convert a FreeGame object (or legacy dict) to a GameItem-compatible dict."""
    if isinstance(game, FreeGame):
        return {
            "title": game.title,
            "store": game.store,
            "link": game.url,
            "end_date": game.end_date,
            "description": game.description,
            "thumbnail": game.image_url,
            "game_type": game.game_type,
            "original_price": game.original_price,
            "review_scores": game.review_scores,
        }
    # Legacy dict format – ensure store key is present with a safe default.
    if isinstance(game, dict) and "store" not in game:
        return {**game, "store": "epic"}
    return game


# ---------------------------------------------------------------------------
# Metrics state (module-level, shared across requests)
# ---------------------------------------------------------------------------

_start_time = time.time()
_metrics = {
    "games_processed": 0,
    "discord_notifications_sent": 0,
    "discord_notification_errors": 0,
    "errors": 0,
}
_metrics_lock = threading.Lock()


def increment_metric(key: str, amount: int = 1):
    """Safely increment a metric counter."""
    with _metrics_lock:
        if key in _metrics:
            _metrics[key] += amount


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Free Games Notifier API",
    description="REST API for monitoring and managing the Free Games Notifier service.",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# API Key authentication
# ---------------------------------------------------------------------------

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def _verify_api_key(api_key: str = Security(_api_key_header)):
    """Validate the API key for mutating endpoints and sensitive read endpoints.

    Used by both state-changing (POST) endpoints and sensitive GET endpoints
    such as ``/config``.  When ``API_KEY`` is not set the check is skipped so
    that local / development deployments work out-of-the-box without auth.
    """
    if not API_KEY:
        return
    if api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse)
def health():
    """Active health check: Epic Games API reachability and database connectivity."""
    result = {"epic_games_api": "unknown", "database": "not_configured"}

    # Check Epic Games API
    try:
        resp = requests_lib.get(EPIC_GAMES_API_URL, timeout=10)
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
                connect_timeout=5,
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


@app.get(
    "/games/latest",
    response_model=GamesLatestResponse,
    responses={500: {"model": ErrorResponse, "description": "Failed to load games from storage"}},
)
def games_latest():
    """Return the most recently fetched games from the configured storage backend."""
    from modules.storage import load_previous_games

    try:
        games = load_previous_games()
        return {"games": [_to_game_item_dict(g) for g in games], "count": len(games)}
    except Exception as e:
        logger.error("Failed to load latest games: %s", e)
        increment_metric("errors")
        raise HTTPException(status_code=500, detail="Failed to load games")


@app.get(
    "/games/history",
    response_model=GamesHistoryResponse,
    responses={500: {"model": ErrorResponse, "description": "Failed to load game history"}},
)
def games_history(
    limit: int = Query(default=20, ge=1, le=100, description="Max number of games to return"),
    offset: int = Query(default=0, ge=0, description="Number of games to skip"),
    sort_by: str = Query(default="end_date", pattern="^(end_date|title)$", description="Field to sort by"),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$", description="Sort direction"),
    store: str = Query(default="all", pattern="^(all|epic|steam)$", description="Filter by store: 'all', 'epic', or 'steam'"),
    status: str = Query(default="all", pattern="^(all|active|expired)$", description="Filter by promotion status: 'all', 'active' (end_date in the future), or 'expired'"),
):
    """Paginated access to all past fetched games.

    Query parameters:
    - **limit**: Max number of games to return (1–100, default: 20)
    - **offset**: Number of games to skip (default: 0)
    - **sort_by**: Field to sort by — ``end_date`` (default) or ``title``
    - **sort_dir**: Sort direction — ``desc`` (default) or ``asc``
    - **store**: Store filter — ``all`` (default), ``epic``, or ``steam``
    - **status**: Promotion status filter — ``all`` (default), ``active`` (promotion still live), or ``expired``

    Filtering and sorting are applied to the full dataset **before** pagination
    so that counts and ordering are consistent across pages.
    """
    from modules.storage import load_previous_games

    def _get_end_date(game) -> datetime:
        """Return the game's end_date as an aware UTC datetime, or datetime.min on parse error."""
        try:
            raw = game.end_date if isinstance(game, FreeGame) else game.get("end_date", "")
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)

    def _sort_key(game):
        if sort_by == "title":
            v = game.title if isinstance(game, FreeGame) else game.get("title", "")
            return v.lower()
        # end_date — ISO-8601 strings sort correctly as plain strings
        return game.end_date if isinstance(game, FreeGame) else game.get("end_date", "")

    try:
        all_games = load_previous_games()

        # Apply store filter — legacy dict records without a "store" key default to
        # "epic" to match the same fallback used in _to_game_item_dict serialization.
        if store != "all":
            all_games = [
                g for g in all_games
                if (g.store if isinstance(g, FreeGame) else g.get("store", "epic")) == store
            ]

        # Apply status filter
        if status != "all":
            now = datetime.now(timezone.utc)
            if status == "active":
                all_games = [g for g in all_games if _get_end_date(g) > now]
            else:  # expired
                all_games = [g for g in all_games if _get_end_date(g) <= now]

        all_games.sort(key=_sort_key, reverse=(sort_dir == "desc"))
        total = len(all_games)
        page = all_games[offset : offset + limit]
        return {"games": [_to_game_item_dict(g) for g in page], "total": total, "limit": limit, "offset": offset}
    except Exception as e:
        logger.error("Failed to load game history: %s", e)
        increment_metric("errors")
        raise HTTPException(status_code=500, detail="Failed to load game history")


@app.post(
    "/notify/discord/resend",
    response_model=ResendResponse,
    dependencies=[Security(_verify_api_key)],
    responses={
        401: {"model": ErrorResponse, "description": "Invalid or missing API key"},
        404: {"model": ErrorResponse, "description": "No games available to resend"},
        500: {"model": ErrorResponse, "description": "Failed to send Discord notification"},
    },
)
def notify_discord_resend(body: Optional[WebhookOverrideRequest] = None):
    """Re-send the last Discord notification batch to the Discord webhook."""
    from modules.notifier import send_discord_message
    from modules.storage import load_last_notification

    webhook_url = body.webhook_url if body else None

    try:
        games = load_last_notification()
    except Exception as e:
        logger.error("Failed to load games for resend: %s", e)
        increment_metric("errors")
        raise HTTPException(status_code=500, detail="Failed to load games")

    if not games:
        raise HTTPException(status_code=404, detail="No games available to resend")

    try:
        send_discord_message(games, webhook_url=webhook_url)
        increment_metric("discord_notifications_sent")
        return {"status": "success", "games_sent": len(games)}
    except Exception as e:
        logger.error("Failed to resend Discord notification: %s", e, exc_info=True)
        increment_metric("discord_notification_errors")
        increment_metric("errors")
        raise HTTPException(status_code=500, detail="Failed to send Discord notification")


@app.get("/metrics", response_model=MetricsResponse)
def metrics():
    """Basic service metrics: uptime, games processed, notifications sent, errors."""
    uptime_seconds = time.time() - _start_time
    with _metrics_lock:
        snapshot = dict(_metrics)
    return {
        "uptime_seconds": round(uptime_seconds, 2),
        **snapshot,
    }


@app.get(
    "/config",
    response_model=ConfigResponse,
    # API key verification protects both mutating endpoints and sensitive
    # read endpoints such as `/config`.
    dependencies=[Security(_verify_api_key)],
    responses={
        401: {"model": ErrorResponse, "description": "Invalid or missing API key"},
    },
)
def config_endpoint():
    """Expose non-secret runtime configuration for this sensitive read endpoint protected by the API key."""
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


@app.post(
    "/check",
    response_model=CheckE2EResponse,
    dependencies=[Security(_verify_api_key)],
    responses={
        401: {"model": ErrorResponse, "description": "Invalid or missing API key"},
        404: {"model": ErrorResponse, "description": "No free games found from any enabled store"},
        500: {"model": ErrorResponse, "description": "Failed to fetch games from all enabled stores"},
    },
)
def check_e2e(body: Optional[WebhookOverrideRequest] = None):
    """End-to-end test: fetch games from all enabled stores, check DB presence, and send Discord notification regardless.

    This endpoint runs the full flow even when the games already exist in the
    database so you can test the pipeline without deleting stored data.
    """
    from modules.notifier import send_discord_message
    from modules.scrapers import get_enabled_scrapers
    from modules.storage import load_previous_games

    webhook_url = body.webhook_url if body else None

    # 1. Fetch current free games from all enabled stores
    current_games = []
    fetch_failed = False
    for scraper in get_enabled_scrapers(ENABLED_STORES):
        try:
            games = scraper.fetch_free_games()
            current_games.extend(games)
            increment_metric("games_processed", len(games))
        except Exception as e:
            logger.error("E2E check – failed to fetch from %s: %s", scraper.store_name, e)
            fetch_failed = True
            increment_metric("errors")

    if not current_games and fetch_failed:
        raise HTTPException(status_code=500, detail="Failed to fetch games")

    if not current_games:
        raise HTTPException(status_code=404, detail="No free games found")

    # 2. Check which games already exist in storage
    try:
        previous_games = load_previous_games()
    except Exception as e:
        logger.error("E2E check – failed to load previous games: %s", e)
        previous_games = []

    already_saved = [g for g in current_games if g in previous_games]
    new_games = [g for g in current_games if g not in previous_games]

    # 3. Send Discord notification regardless of DB state
    notification_status = "skipped"
    try:
        send_discord_message(current_games, webhook_url=webhook_url)
        notification_status = "sent"
        increment_metric("discord_notifications_sent")
    except Exception as e:
        logger.error("E2E check – Discord notification failed: %s", e)
        notification_status = f"failed: {e}"
        increment_metric("discord_notification_errors")
        increment_metric("errors")

    def _get_title(game) -> str:
        return game.title if isinstance(game, FreeGame) else game.get("title", "")

    return {
        "games_fetched": len(current_games),
        "games": [_to_game_item_dict(g) for g in current_games],
        "already_in_storage": [_get_title(g) for g in already_saved],
        "new_games": [_get_title(g) for g in new_games],
        "notification_status": notification_status,
    }


# ---------------------------------------------------------------------------
# Dashboard – serve the pre-built React/TypeScript frontend
# ---------------------------------------------------------------------------

_dashboard_dist = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard", "dist")
if os.path.isdir(_dashboard_dist):
    app.mount("/dashboard", StaticFiles(directory=_dashboard_dist, html=True), name="dashboard")
