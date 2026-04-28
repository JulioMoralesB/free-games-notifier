"""Steam store scraper implementation."""

import html
import logging
import re
import time
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from config import STEAM_COUNTRY, STEAM_LANGUAGE, STEAM_REQUEST_DELAY_MS, STEAM_SEARCH_URL
from modules.models import FreeGame
from modules.retry import with_retry
from modules.scrapers.base import BaseScraper
from modules.scrapers.review_sources import fetch_metacritic_score

logger = logging.getLogger(__name__)


class _RateLimitedError(Exception):
    pass


_RETRYABLE_ERRORS = (
    requests.exceptions.Timeout,
    requests.exceptions.ConnectionError,
    _RateLimitedError,
)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Cookies that bypass Steam's age-check interstitial. Without these, mature-rated
# store pages redirect to /agecheck/app/<id>/ which doesn't contain the discount
# expiration text, so end_date can't be parsed.
_AGE_CHECK_COOKIES = {
    "birthtime": "470707201",
    "mature_content": "1",
    "lastagecheckage": "1-January-1985",
    "wants_mature_content": "1",
}

_SEARCH_PARAMS = {
    "maxprice": "free",
    "specials": 1,
    "l": "english",
}

_APPDETAILS_URL = "https://store.steampowered.com/api/appdetails"
_APPREVIEWS_URL = "https://store.steampowered.com/appreviews"

_END_DATE_RE = re.compile(
    r"before\s+(\d{1,2})\s+(\w{3})\s+@\s+(\d{1,2}):(\d{2})(am|pm)",
    re.IGNORECASE,
)

# Defined at module level to avoid recreating the dict on every _parse_steam_end_date call.
_MONTH_MAP = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


def _steam_get(url: str, **kwargs) -> requests.Response:
    """Sleep for STEAM_REQUEST_DELAY_MS, then GET url. Raises _RateLimitedError on HTTP 429."""
    time.sleep(STEAM_REQUEST_DELAY_MS / 1000)
    response = requests.get(url, **kwargs)
    if response.status_code == 429:
        response.close()
        raise _RateLimitedError(f"Rate limited by Steam (429) for {url}")
    return response


def _parse_steam_end_date(text: str) -> str:
    """Parse 'before DD Mon @ HH:MMam/pm' into an ISO-8601 UTC string.

    Steam's server-side HTML always renders promotion end times in Pacific Time
    (America/Los_Angeles — PDT in summer, PST in winter), regardless of the
    viewer's locale or the cc= parameter.  We therefore always interpret the
    scraped time as Pacific, convert to UTC for storage, and let the notifier
    convert from UTC to the user's configured TIMEZONE for display.
    """
    # Normalize all whitespace (including tabs, non-breaking, thin, etc.) to a single space.
    text = re.sub(r"\s+", " ", text, flags=re.UNICODE)
    logger.debug("Parsing Steam end date from text: %r", text[:200])
    m = _END_DATE_RE.search(text)
    logger.debug("Regex match for end date: %r", m.groups() if m else None)

    if not m:
        return ""
    day, month_str, hour, minute, ampm = m.groups()
    try:
        # _MONTH_MAP is a module-level constant; avoids recreating the dict each call.
        month = _MONTH_MAP.get(month_str)
        if not month:
            raise ValueError(f"Unknown month abbreviation: {month_str}")
        hour = int(hour)
        if ampm.lower() == "pm" and hour != 12:
            hour += 12
        elif ampm.lower() == "am" and hour == 12:
            hour = 0
        # Steam always shows Pacific Time — use it as the source timezone.
        pacific_tz = ZoneInfo("America/Los_Angeles")
        now = datetime.now(tz=timezone.utc)
        dt = datetime(now.year, month, int(day), hour, int(minute), tzinfo=pacific_tz).astimezone(timezone.utc)
        if dt < now:
            dt = dt.replace(year=now.year + 1)
        formatted_dt = dt.isoformat().replace("+00:00", "Z")
        logger.debug("Parsed end date: %s (UTC)", formatted_dt)
        return formatted_dt
    except ValueError:
        logger.error("Error parsing end date components: Day=%s, Month=%s, Hour=%s, Minute=%s, AM/PM=%s", day, month_str, hour, minute, ampm, exc_info=True)
        return ""


class SteamScraper(BaseScraper):
    """Scraper for Steam free game promotions."""

    @property
    def store_name(self) -> str:
        return "steam"

    def fetch_free_games(self) -> list[FreeGame]:
        logger.info("Fetching free games from Steam. URL: %s", STEAM_SEARCH_URL)
        try:
            response = with_retry(
                func=lambda: _steam_get(
                    STEAM_SEARCH_URL,
                    params={**_SEARCH_PARAMS, "cc": STEAM_COUNTRY},
                    headers=_HEADERS,
                    timeout=10,
                ),
                max_attempts=4,
                base_delay=2,
                retryable_exceptions=_RETRYABLE_ERRORS,
                description="Steam search fetch",
            )
        except _RETRYABLE_ERRORS as e:
            logger.error("Failed to fetch Steam search after retries: %s", e, exc_info=True)
            return []

        if response.status_code != 200:
            logger.error("Failed to fetch Steam search. Status: %s", response.status_code)
            return []

        candidates = self._parse_search_page(response.text)
        logger.info("Found %d free game candidates.", len(candidates))

        games = [self._build_game(c) for c in candidates]
        logger.info("Returning %d Steam free games.", len(games))
        return games

    def _parse_search_page(self, html: str) -> list[dict]:
        """Return candidate dicts for games with price_final==0 and an original price."""
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select("#search_resultsRows a.search_result_row")
        logger.info("Steam search returned %d result rows.", len(rows))

        candidates = []
        for row in rows:
            price_div = row.select_one("[data-price-final]")
            if not price_div:
                continue
            try:
                price_final = int(price_div.get("data-price-final", 1))
            except (ValueError, TypeError):
                continue

            original_el = row.select_one(".discount_original_price")
            if price_final != 0 or not original_el:
                continue

            appid = row.get("data-ds-appid", "")
            if not appid or "," in appid:
                logger.debug("Skipping row with invalid or multi-appid: %r", appid)
                continue

            title_el = row.select_one(".title")
            title_str = title_el.text.strip() if title_el else ""
            logger.info("Free candidate detected: %r | appid=%s", title_str, appid)
            candidates.append({
                "appid": appid,
                "title": title_str,
                "url": row.get("href", "").split("?")[0],
                "original_price": original_el.text.strip(),
            })

        return candidates

    def _build_game(self, candidate: dict) -> FreeGame:
        """Enrich a candidate with app details and review scores, then return a FreeGame."""
        appid = candidate["appid"]
        title = candidate["title"]
        details = self._fetch_appdetails(appid)

        image_url = details.get("header_image") or (
            f"https://shared.akamai.steamstatic.com/store_item_assets"
            f"/steam/apps/{appid}/capsule_sm_120.jpg"
        )
        end_date = self._fetch_end_date(candidate["url"])
        if not end_date:
            logger.error(
                "END DATE MISSING for Steam game %r (appid=%s, url=%s). "
                "Game will be stored with empty end_date — check the store page manually.",
                title, appid, candidate["url"],
            )

        # The appdetails API returns a "type" field: "game", "dlc", "music", etc.
        # This is more reliable than inferring from search-result CSS classes.
        game_type = details.get("type", "game")
        if game_type not in ("game", "dlc"):
            game_type = "game"

        # Collect review scores from all available sources.
        review_scores: list[str] = []
        steam_score = self._fetch_review_score(appid)
        if steam_score:
            review_scores.append(steam_score)
        mc = fetch_metacritic_score(title)
        if mc:
            review_scores.append(mc)

        logger.info(
            "Built free game: %s (appid=%s, reviews=%s, type=%s)",
            title, appid, review_scores, game_type,
        )
        return FreeGame(
            title=title,
            store=self.store_name,
            url=candidate["url"],
            image_url=image_url,
            original_price=candidate["original_price"],
            end_date=end_date,
            is_permanent=False,
            description=html.unescape(details.get("short_description", "")),
            review_scores=review_scores,
            game_type=game_type,
        )

    def _fetch_appdetails(self, appid: str) -> dict:
        """Fetch short_description and header_image from the Steam appdetails API."""
        try:
            response = with_retry(
                func=lambda: _steam_get(
                    _APPDETAILS_URL,
                    params={"appids": appid, "cc": STEAM_COUNTRY, "l": STEAM_LANGUAGE},
                    headers=_HEADERS,
                    timeout=10,
                ),
                max_attempts=4,
                base_delay=2,
                retryable_exceptions=_RETRYABLE_ERRORS,
                description=f"Steam appdetails (appid={appid})",
            )
            if response.status_code == 200:
                data = response.json()
                if data.get(appid, {}).get("success"):
                    return data[appid]["data"]
        except Exception as e:
            logger.warning("Failed to fetch appdetails for appid=%s: %s", appid, e)
        return {}

    def _fetch_end_date(self, url: str) -> str:
        """Scrape the discount expiration from the game's store page.

        Steam shows 'Free to keep when you get it before DD Mon @ HH:MMam/pm'
        on the store page. The time is in UTC when scraped without session cookies.
        """
        try:
            response = with_retry(
                func=lambda: _steam_get(url, headers=_HEADERS, cookies=_AGE_CHECK_COOKIES, timeout=10),
                max_attempts=3,
                base_delay=2,
                retryable_exceptions=_RETRYABLE_ERRORS,
                description=f"Steam end date ({url})",
            )
            if response.status_code != 200:
                return ""
            soup = BeautifulSoup(response.text, "html.parser")

            # Try the dedicated discount quantity element first
            el = soup.select_one(".game_purchase_discount_quantity")
            if el:
                result = _parse_steam_end_date(el.text)
                if result:
                    return result
                logger.error(
                    "Found .game_purchase_discount_quantity but regex did not match — "
                    "Steam may have changed the date format. "
                    "Text: %r | URL: %s",
                    el.text[:200],
                    url,
                )

            # Fall back to searching the entire page text — handles cases where
            # Steam renders the element via JS or uses a different CSS class.
            result = _parse_steam_end_date(soup.get_text(" "))
            if result:
                return result

            logger.error(
                "Could not find promotion end date on Steam page: %s — "
                "page may use a different layout or the element is JS-rendered.",
                url,
            )
            return ""
        except Exception as e:
            logger.error("Failed to fetch end date from %s: %s", url, e)
            return ""

    def _fetch_review_score(self, appid: str) -> Optional[str]:
        """Fetch user review summary label from the Steam reviews API."""
        try:
            response = with_retry(
                func=lambda: _steam_get(
                    f"{_APPREVIEWS_URL}/{appid}",
                    params={"json": 1, "language": "all", "purchase_type": "all"},
                    headers=_HEADERS,
                    timeout=10,
                ),
                max_attempts=3,
                base_delay=2,
                retryable_exceptions=_RETRYABLE_ERRORS,
                description=f"Steam review score (appid={appid})",
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("query_summary", {}).get("review_score_desc") or None
        except Exception as e:
            logger.warning("Failed to fetch review score for appid=%s: %s", appid, e)
        return None
