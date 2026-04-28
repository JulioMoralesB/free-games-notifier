"""Shared review-score fetchers used by all store scrapers.

Each public function returns a single formatted string, or ``None`` when the
score is unavailable.  Callers aggregate results into a ``review_scores`` list
on the ``FreeGame`` model.

Supported formats
-----------------
- ``"Very Positive"``   — Steam-style user-review label (passed through as-is)
- ``"Metascore: 83"``   — Metacritic critic score (0–100), scraped via JSON-LD
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Metacritic
# ---------------------------------------------------------------------------

_METACRITIC_BASE = "https://www.metacritic.com/game"

# Mimic a real browser so Metacritic serves the full HTML page with JSON-LD.
_MC_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def make_metacritic_slug(title: str) -> str:
    """Convert a game title to a Metacritic URL slug.

    Examples
    --------
    >>> make_metacritic_slug("The Witcher 3: Wild Hunt")
    'the-witcher-3-wild-hunt'
    >>> make_metacritic_slug("Baldur's Gate 3")
    'baldurs-gate-3'
    """
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    slug = ascii_title.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug).strip("-")
    slug = re.sub(r"-+", "-", slug)
    return slug


def fetch_metacritic_score(title: str) -> str | None:
    """Return ``"Metascore: 83"`` for *title* scraped from Metacritic, or ``None``.

    Metacritic embeds the critic score as JSON-LD structured data in the page
    HTML, so no API key is required.  Any network or parsing failure is logged
    as a warning and returns ``None`` so a single game never blocks the scrape.
    """
    slug = make_metacritic_slug(title)
    url = f"{_METACRITIC_BASE}/{slug}/"
    logger.info("Metacritic: fetching score for %r → %s", title, url)

    try:
        resp = requests.get(url, headers=_MC_HEADERS, timeout=10)
        if resp.status_code != 200:
            logger.info(
                "Metacritic: HTTP %s for %r — skipping review score",
                resp.status_code, title,
            )
            return None

        blocks = re.findall(
            r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>',
            resp.text,
            re.DOTALL,
        )
        for raw_block in blocks:
            try:
                data = json.loads(raw_block)
            except json.JSONDecodeError:
                continue

            agg = data.get("aggregateRating") or {}
            value = agg.get("ratingValue")
            if value is not None:
                try:
                    score = int(value)
                    logger.info("Metacritic: %r → Metascore %d", title, score)
                    return f"Metascore: {score}"
                except (ValueError, TypeError):
                    continue

        logger.info("Metacritic: no aggregateRating found for %r", title)

    except Exception as exc:
        logger.warning("Metacritic: failed to fetch score for %r: %s", title, exc)

    return None


