"""The /api/summary contract body.

``build_summary`` is the single source of truth for the summary payload: the
local ``GET /api/summary`` route serves it, and the Cloudflare mirror
(modules/mirror.py) receives the very same body, so the two can't drift.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from modules.dedupe import is_still_active
from modules.scheduler_state import get_last_check_completed_at

SERVICE_NAME = "free-games-notifier"


def build_active_promotions(games) -> list[dict]:
    """Currently-free games with a known deadline, soonest-ending first.

    Games with no known end_date are excluded: this contract promises "when
    it ends", and a poller can't act on a deadline we don't have.
    """
    active = [g for g in games if is_still_active(g) and g.end_date]
    active.sort(key=lambda g: g.end_date)
    return [
        {"title": g.title, "link": g.url, "store": g.store, "end_date": g.end_date}
        for g in active
    ]


def format_last_check_at(timestamp: Optional[float]) -> Optional[str]:
    """ISO-8601 UTC form of a Unix timestamp, or None when no check has completed."""
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def build_summary(games) -> dict:
    """The full SummaryResponse body for *games*."""
    return {
        "service": SERVICE_NAME,
        "active_promotions": build_active_promotions(games),
        "last_check_at": format_last_check_at(get_last_check_completed_at()),
    }
