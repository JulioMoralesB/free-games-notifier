"""Discord notification endpoints: /notify/discord/resend."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Security

from api.auth import verify_api_key
from api.metrics import increment_metric
from api.schemas import ErrorResponse, ResendResponse, WebhookOverrideRequest
from modules.notifier import send_discord_message
from modules.storage import load_last_notification

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/notify/discord/resend",
    response_model=ResendResponse,
    dependencies=[Security(verify_api_key)],
    responses={
        401: {"model": ErrorResponse, "description": "Invalid or missing API key"},
        404: {"model": ErrorResponse, "description": "No games available to resend"},
        500: {"model": ErrorResponse, "description": "Failed to send Discord notification"},
    },
)
def notify_discord_resend(body: Optional[WebhookOverrideRequest] = None):
    """Re-send the last Discord notification batch to the Discord webhook."""
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
