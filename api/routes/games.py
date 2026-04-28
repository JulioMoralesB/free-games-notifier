"""Game history endpoints: /games/latest, /games/history."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from api.metrics import increment_metric
from api.schemas import ErrorResponse, GamesHistoryResponse, GamesLatestResponse
from api.serializers import get_end_date, get_store, to_game_item_dict
from modules.models import FreeGame
from modules.storage import load_previous_games

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/games/latest",
    response_model=GamesLatestResponse,
    responses={500: {"model": ErrorResponse, "description": "Failed to load games from storage"}},
)
def games_latest():
    """Return the most recently fetched games from the configured storage backend."""
    try:
        games = load_previous_games()
        return {"games": [to_game_item_dict(g) for g in games], "count": len(games)}
    except Exception as e:
        logger.error("Failed to load latest games: %s", e)
        increment_metric("errors")
        raise HTTPException(status_code=500, detail="Failed to load games")


@router.get(
    "/games/history",
    response_model=GamesHistoryResponse,
    responses={500: {"model": ErrorResponse, "description": "Failed to load game history"}},
)
def games_history(
    limit: int = Query(default=20, ge=1, le=100, description="Max number of games to return"),
    offset: int = Query(default=0, ge=0, description="Number of games to skip"),
    sort_by: str = Query(
        default="end_date", pattern="^(end_date|title)$", description="Field to sort by"
    ),
    sort_dir: str = Query(
        default="desc", pattern="^(asc|desc)$", description="Sort direction"
    ),
    store: str = Query(
        default="all",
        pattern="^(all|epic|steam)$",
        description="Filter by store: 'all', 'epic', or 'steam'",
    ),
    status: str = Query(
        default="all",
        pattern="^(all|active|expired)$",
        description=(
            "Filter by promotion status: 'all', 'active' (end_date in the future), or 'expired'"
        ),
    ),
):
    """Paginated access to all past fetched games.

    Filtering and sorting are applied to the full dataset **before** pagination
    so that counts and ordering are consistent across pages.
    """

    def _sort_key(game):
        if sort_by == "title":
            v = game.title if isinstance(game, FreeGame) else game.get("title", "")
            return v.lower()
        # end_date — ISO-8601 strings sort correctly as plain strings
        return game.end_date if isinstance(game, FreeGame) else game.get("end_date", "")

    try:
        all_games = load_previous_games()

        # Apply store filter — legacy dict records without a "store" key default to
        # "epic" to match the same fallback used in to_game_item_dict serialization.
        if store != "all":
            all_games = [g for g in all_games if get_store(g) == store]

        # Apply status filter
        if status != "all":
            now = datetime.now(timezone.utc)
            if status == "active":
                all_games = [g for g in all_games if get_end_date(g) > now]
            else:  # expired
                all_games = [g for g in all_games if get_end_date(g) <= now]

        all_games.sort(key=_sort_key, reverse=(sort_dir == "desc"))
        total = len(all_games)
        page = all_games[offset : offset + limit]
        return {
            "games": [to_game_item_dict(g) for g in page],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    except Exception as e:
        logger.error("Failed to load game history: %s", e)
        increment_metric("errors")
        raise HTTPException(status_code=500, detail="Failed to load game history")
