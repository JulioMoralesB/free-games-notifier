"""Helpers that convert internal models (FreeGame, legacy dicts) to API DTOs."""

from datetime import datetime, timezone

from modules.models import FreeGame


def to_game_item_dict(game) -> dict:
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


def get_end_date(game) -> datetime:
    """Return the game's end_date as an aware UTC datetime, or datetime.min on parse error.

    Used by the history endpoint's status filter to compare against ``datetime.now(UTC)``.
    """
    try:
        raw = game.end_date if isinstance(game, FreeGame) else game.get("end_date", "")
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def get_title(game) -> str:
    """Return the game's title regardless of whether it is a FreeGame or legacy dict."""
    return game.title if isinstance(game, FreeGame) else game.get("title", "")


def get_store(game) -> str:
    """Return the game's store, defaulting to 'epic' for legacy records without one."""
    return game.store if isinstance(game, FreeGame) else game.get("store", "epic")
