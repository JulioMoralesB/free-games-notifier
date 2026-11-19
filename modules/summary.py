"""The /api/summary contract body, and the optional push of it to a mirror.

``build_summary`` is the single source of truth for the summary payload: the
local ``GET /api/summary`` route serves it, and ``push_summary_snapshot``
sends the very same body to an always-on mirror (see docs/summary-mirror.md)
so external pollers keep working while this host is powered off.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import requests

from config import SUMMARY_MIRROR_TIMEOUT, SUMMARY_MIRROR_TOKEN, SUMMARY_MIRROR_URL
from modules.dedupe import is_still_active
from modules.scheduler_state import get_last_check_completed_at

logger = logging.getLogger(__name__)

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


def _safe_location(url: Optional[str]) -> str:
    """Return ``host[:port]`` for *url* — never the path or query, which may hold secrets."""
    parsed = urlparse(url or "")
    if not parsed.hostname:
        return "unconfigured-mirror"
    return f"{parsed.hostname}:{parsed.port}" if parsed.port else parsed.hostname


def push_summary_snapshot() -> None:
    """Push the current summary to the configured mirror. Fire-and-forget.

    Never raises: a mirror outage must not fail the check that just ran, the
    heartbeat, or the process (an uncaught exception here would crash the
    ``schedule`` loop in main.py, as the heartbeat push once did). One attempt
    with a short timeout, no retries — the next completed check pushes again.
    Failures are logged at WARNING, without the URL or the exception text,
    either of which could carry the token.
    """
    if not (SUMMARY_MIRROR_URL and SUMMARY_MIRROR_TOKEN):
        logger.debug("Summary mirror not configured; skipping snapshot push.")
        return

    target = _safe_location(SUMMARY_MIRROR_URL)
    try:
        # Imported lazily so a storage import problem can't break module import.
        from modules.storage import load_previous_games

        # strict=True: if storage can't be read, skip the push rather than
        # overwrite the mirror with a fabricated empty list.
        payload = build_summary(load_previous_games(strict=True))
        response = requests.post(
            SUMMARY_MIRROR_URL,
            json=payload,
            headers={"Authorization": f"Bearer {SUMMARY_MIRROR_TOKEN}"},
            timeout=SUMMARY_MIRROR_TIMEOUT,
        )
        if not 200 <= response.status_code < 300:
            logger.warning(
                "Summary mirror at %s rejected the snapshot: HTTP %s",
                target,
                response.status_code,
            )
            return
        logger.info(
            "Pushed summary snapshot (%d active promotion(s)) to %s",
            len(payload["active_promotions"]),
            target,
        )
    except Exception as e:
        logger.warning(
            "Failed to push summary snapshot to %s: %s (continuing; next check retries)",
            target,
            type(e).__name__,
        )
