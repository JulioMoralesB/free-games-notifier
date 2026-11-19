"""External summary endpoint for other services on the LAN: GET /api/summary.

A small, explicit, additive-only contract — separate from the general
internal API (see ADR 012 in the server documentation: services integrate
through a small owned endpoint, not by reading each other's schema/tables).
Never remove or repurpose a field in SummaryResponse; add a new path instead.
"""

import logging

from fastapi import APIRouter, HTTPException, Security

from api.auth import verify_dashboard_key
from api.schemas import ErrorResponse, SummaryResponse
from modules.scheduler_state import get_last_check_completed_at
from modules.storage import load_previous_games
from modules.summary import SERVICE_NAME, build_active_promotions, format_last_check_at

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/api/summary",
    response_model=SummaryResponse,
    dependencies=[Security(verify_dashboard_key)],
    responses={
        401: {"model": ErrorResponse, "description": "Invalid or missing shared secret"},
        503: {"model": ErrorResponse, "description": "Storage backend unavailable"},
    },
)
def summary():
    """Read-only summary for external pollers. No writes, no side effects.

    Fails with 503 rather than reporting a fabricated zero when storage is
    unreachable — an "unavailable" error is more honest than a "0 games"
    that could mean either "nothing tracked" or "couldn't check".
    """
    try:
        games = load_previous_games(strict=True)
    except Exception as e:
        logger.error("Failed to load games for summary: %s", e)
        raise HTTPException(status_code=503, detail="Storage backend unavailable")

    # Same body the summary mirror receives (modules/summary.py), so the
    # local endpoint and the always-on mirror can't drift apart.
    return {
        "service": SERVICE_NAME,
        "active_promotions": build_active_promotions(games),
        "last_check_at": format_last_check_at(get_last_check_completed_at()),
    }
