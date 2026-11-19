"""Fire-and-forget push to the always-on Cloudflare mirror (docs/cloudflare-mirror.md).

After every completed check, the scheduler calls ``push_to_mirror()``, which:

1. POSTs the /api/summary body to ``{MIRROR_URL}/api/mirror/summary``.
2. If that worked, syncs the full game history (what ``GET /games/history``
   serves the dashboard) to ``{MIRROR_URL}/api/mirror/games`` in chunks. Every
   chunk of one sync shares a ``sync_id``; only the last one is ``final``, and
   only a final chunk lets the mirror delete games this sync didn't include.
   A sync that fails partway therefore only ever upserts, never deletes.

Nothing here may raise: a mirror outage must never fail the check that just
ran, the heartbeat, or the process (an uncaught exception would crash the
``schedule`` loop in main.py, as the heartbeat push once did). Each request is
one attempt with a short timeout, no retries; the first failure stops the
whole push, so a down mirror costs at most one timeout per check. The next
completed check pushes everything again.

Logs never include the URL path, the token, or exception text (which can
embed the URL) — only the mirror's host.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional
from urllib.parse import urlparse

import requests

from config import MIRROR_TIMEOUT, MIRROR_TOKEN, MIRROR_URL
from modules.summary import build_summary

logger = logging.getLogger(__name__)

SUMMARY_PATH = "/api/mirror/summary"
GAMES_PATH = "/api/mirror/games"

#: Games per request — keeps each ingest well inside the Workers Free plan's
#: 10 ms CPU budget (JSON parse + one D1 batch).
GAMES_CHUNK_SIZE = 100


def _safe_location(url: Optional[str]) -> str:
    """Return ``host[:port]`` for *url* — never the path or query."""
    parsed = urlparse(url or "")
    if not parsed.hostname:
        return "unconfigured-mirror"
    return f"{parsed.hostname}:{parsed.port}" if parsed.port else parsed.hostname


def _post(path: str, payload: dict, what: str) -> Optional[requests.Response]:
    """POST *payload* to the mirror once. Returns the response on 2xx, else None."""
    target = _safe_location(MIRROR_URL)
    try:
        response = requests.post(
            f"{MIRROR_URL}{path}",
            json=payload,
            headers={"Authorization": f"Bearer {MIRROR_TOKEN}"},
            timeout=MIRROR_TIMEOUT,
        )
    except Exception as e:
        logger.warning(
            "Failed to push %s to mirror at %s: %s (continuing; next check retries)",
            what, target, type(e).__name__,
        )
        return None
    if not 200 <= response.status_code < 300:
        logger.warning(
            "Mirror at %s rejected %s: HTTP %s", target, what, response.status_code
        )
        return None
    return response


def _push_summary(games) -> bool:
    payload = build_summary(games)
    if _post(SUMMARY_PATH, payload, "the summary") is None:
        return False
    logger.info(
        "Pushed summary (%d active promotion(s)) to mirror at %s",
        len(payload["active_promotions"]), _safe_location(MIRROR_URL),
    )
    return True


def _push_games(games) -> None:
    # Lazy import: modules/ shouldn't import the api package at module load.
    from api.serializers import to_game_item_dict

    items = [to_game_item_dict(g) for g in games]
    chunks = [
        items[i:i + GAMES_CHUNK_SIZE] for i in range(0, len(items), GAMES_CHUNK_SIZE)
    ] or [[]]  # An empty history still needs one final chunk to sync deletions.
    sync_id = uuid.uuid4().hex
    skipped = 0

    for index, chunk in enumerate(chunks):
        final = index == len(chunks) - 1
        response = _post(
            GAMES_PATH,
            {"sync_id": sync_id, "final": final, "games": chunk},
            f"game history chunk {index + 1}/{len(chunks)}",
        )
        if response is None:
            return  # Stop: never send `final` after a failed chunk.
        try:
            skipped += int(response.json().get("skipped", 0))
        except Exception:
            pass

    if skipped:
        logger.warning(
            "Mirror skipped %d invalid game record(s) during history sync", skipped
        )
    logger.info(
        "Synced %d game(s) to mirror at %s in %d request(s)",
        len(items), _safe_location(MIRROR_URL), len(chunks),
    )


def push_to_mirror() -> None:
    """Push the summary, then the game history, to the mirror. Never raises."""
    if not (MIRROR_URL and MIRROR_TOKEN):
        logger.debug("Cloudflare mirror not configured; skipping push.")
        return

    try:
        # Imported lazily so a storage import problem can't break module import.
        from modules.storage import load_previous_games

        # strict=True: if storage can't be read, skip the push rather than send
        # an empty summary — or an empty history the mirror would sync-delete.
        games = load_previous_games(strict=True)
    except Exception as e:
        logger.warning(
            "Skipping mirror push: could not read storage (%s)", type(e).__name__
        )
        return

    try:
        if _push_summary(games):
            _push_games(games)
    except Exception as e:
        logger.warning(
            "Mirror push failed unexpectedly: %s (continuing; next check retries)",
            type(e).__name__,
        )
