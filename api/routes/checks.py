"""End-to-end pipeline test endpoint: POST /check."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Security

from api.auth import verify_api_key
from api.metrics import increment_metric
from api.schemas import CheckE2EResponse, ErrorResponse, WebhookOverrideRequest
from api.serializers import get_title, to_game_item_dict
from config import ENABLED_STORES
from modules.notifier import send_discord_message
from modules.scrapers import get_enabled_scrapers
from modules.storage import load_previous_games

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/check",
    response_model=CheckE2EResponse,
    dependencies=[Security(verify_api_key)],
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

    return {
        "games_fetched": len(current_games),
        "games": [to_game_item_dict(g) for g in current_games],
        "already_in_storage": [get_title(g) for g in already_saved],
        "new_games": [get_title(g) for g in new_games],
        "notification_status": notification_status,
    }
