import locale
import logging
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import pytz
import requests

from config import DATE_FORMAT, DISCORD_WEBHOOK_URL, EPIC_GAMES_REGION, LOCALE, TIMEZONE
from modules.retry import with_retry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Locale-aware strings
# ---------------------------------------------------------------------------

_TRANSLATIONS = {
    "en": {
        "ends_on": "Ends on",
        "permanently_free": "Permanently free",
        "end_date_unavailable": "End date unavailable",
        "original_price": "💰 Original Price",
        "user_reviews": "💬 Steam Reviews:",
        "metacritic_reviews": "📊 Metacritic:",
        "new_free_game": "**New Free Game on {store}! 🎮**\n",
        "new_free_games": "**New Free Games! 🎮**\n",
        "new_free_dlc": "**New Free DLC on {store}! 🎮**\n",
        "dlc_badge": "📦 DLC",
        "requires_base_game": "Requires the base game",
        "review_labels": {
            "overwhelmingly positive": "Overwhelmingly Positive",
            "very positive": "Very Positive",
            "mostly positive": "Mostly Positive",
            "positive": "Positive",
            "mixed": "Mixed",
            "mostly negative": "Mostly Negative",
            "negative": "Negative",
            "very negative": "Very Negative",
            "overwhelmingly negative": "Overwhelmingly Negative",
            "no user reviews": "No user reviews",
        },
    },
    "es": {
        "ends_on": "Finaliza el",
        "permanently_free": "Gratis de forma permanente",
        "end_date_unavailable": "Fecha de fin no disponible",
        "original_price": "💰 Precio original",
        "user_reviews": "💬 Reseñas en Steam:",
        "metacritic_reviews": "📊 Metacritic:",
        "new_free_game": "**¡Nuevo Juego Gratis en {store}! 🎮**\n",
        "new_free_games": "**¡Nuevos Juegos Gratis! 🎮**\n",
        "new_free_dlc": "**¡Nuevo DLC Gratis en {store}! 🎮**\n",
        "dlc_badge": "📦 DLC",
        "requires_base_game": "Requiere el juego base",
        "review_labels": {
            "overwhelmingly positive": "Extremadamente Positivo",
            "very positive": "Muy Positivo",
            "mostly positive": "Mayormente Positivo",
            "positive": "Positivo",
            "mixed": "Mixto",
            "mostly negative": "Mayormente Negativo",
            "negative": "Negativo",
            "very negative": "Muy Negativo",
            "overwhelmingly negative": "Extremadamente Negativo",
            "no user reviews": "Sin reseñas",
        },
    },
}


def _get_lang(locale_str: str) -> str:
    """Derive a two-letter language code from a LOCALE string (e.g. 'es_MX.UTF-8' → 'es')."""
    if locale_str:
        lang = locale_str.split("_")[0].split("-")[0].lower()
        if lang in _TRANSLATIONS:
            return lang
    return "en"


_LANG = _get_lang(LOCALE)
_T = _TRANSLATIONS[_LANG]

_DISCORD_RETRYABLE = (
    requests.exceptions.Timeout,
    requests.exceptions.ConnectionError,
)

if LOCALE:
    try:
        locale.setlocale(locale.LC_TIME, LOCALE)
    except locale.Error as exc:
        logger.warning(
            "Locale %s is not available, falling back to system locale. "
            "Date formatting may differ. Underlying error: %s",
            LOCALE,
            exc,
            exc_info=True,
        )

_ALLOWED_DISCORD_HOSTS = frozenset({"discord.com", "discordapp.com"})


def validate_discord_webhook_url(url: str) -> None:
    """
    Validate that a URL is a legitimate Discord webhook URL.

    Checks that the URL uses HTTPS, targets an allowed Discord host, and has
    the expected /api/webhooks/ path prefix.  Raises ``ValueError`` with a
    descriptive message when any check fails.  This is the primary guard
    against SSRF attacks via user-supplied webhook URLs.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        raise ValueError("Invalid webhook URL format")

    if parsed.scheme != "https":
        raise ValueError("Webhook URL must use HTTPS")

    if parsed.hostname not in _ALLOWED_DISCORD_HOSTS:
        raise ValueError(
            f"Webhook URL host must be discord.com or discordapp.com, got: {parsed.hostname!r}"
        )

    if not parsed.path.startswith("/api/webhooks/"):
        raise ValueError("Webhook URL path must start with /api/webhooks/")


def _get_safe_webhook_identifier(webhook_url: str) -> str:
    """
    Return a redacted identifier for a webhook URL that is safe to log.
    For Discord webhooks, this will be `<host>/api/webhooks/<id>` (no token).
    For other URLs, this falls back to the hostname or a generic placeholder.
    """
    if not webhook_url:
        return "unknown-webhook"
    try:
        parsed = urlparse(webhook_url)
        # Use parsed.hostname (not .netloc) to avoid logging userinfo credentials
        # if a crafted URL like user:pass@discord.com is somehow supplied.
        host = parsed.hostname or "unknown-host"
        path = parsed.path or ""

        # Expected Discord webhook pattern: /api/webhooks/<id>/<token>
        segments = path.strip("/").split("/")
        if len(segments) >= 3 and segments[0] == "api" and segments[1] == "webhooks":
            webhook_id = segments[2]
            return f"{host}/api/webhooks/{webhook_id}"

        # Fallback: only host if path does not match expected pattern
        return host
    except Exception:
        # In case of any parsing error, avoid logging the raw URL
        return "invalid-webhook-url"

def send_discord_message(new_games, webhook_url: Optional[str] = None):
    """
    Send a Discord webhook message for new free games.

    Args:
        new_games: List of game dictionaries to send to Discord
        webhook_url: Optional webhook URL override. Defaults to DISCORD_WEBHOOK_URL.
            Must be a valid Discord webhook URL on either discord.com or discordapp.com
            (e.g. https://discord.com/api/webhooks/... or https://discordapp.com/api/webhooks/...).

    Raises:
        ValueError: If webhook URL is not configured or fails validation
        requests.RequestException: If the HTTP request fails
    """
    # Determine effective webhook URL, giving precedence to an explicit override
    if webhook_url is not None:
        override = webhook_url.strip()
        if not override:
            error_msg = "Explicit Discord webhook URL override is empty or whitespace-only"
            logger.error(error_msg)
            raise ValueError(error_msg)
        effective_webhook_url = override
    else:
        effective_webhook_url = DISCORD_WEBHOOK_URL

    if not effective_webhook_url:
        error_msg = "Discord webhook URL not configured in environment variables"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Validate user-supplied webhook URLs to prevent SSRF
    if webhook_url is not None:
        validate_discord_webhook_url(effective_webhook_url)

    try:
        _STORE_META = {
            "epic": {
                "name": "Epic Games Store",
                "url": f"https://store.epicgames.com/{EPIC_GAMES_REGION}/free-games",
                "color": 0x2ECC71,
                "icon_url": "https://images.icon-icons.com/2407/PNG/512/epic_games_icon_146062.png",
            },
            "steam": {
                "name": "Steam",
                "url": "https://store.steampowered.com/search/?maxprice=free&specials=1",
                "color": 0x1B2838,
                "icon_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/83/Steam_icon_logo.svg/64px-Steam_icon_logo.svg.png",
            },
        }

        embeds = []
        for game in new_games:
            try:
                if game.is_permanent or not game.end_date:
                    formatted_end_date = None
                else:
                    try:
                        end_date = datetime.strptime(game.end_date, "%Y-%m-%dT%H:%M:%S.%fZ")
                    except ValueError:
                        # Try without microseconds (e.g. Steam ISO strings)
                        end_date = datetime.strptime(game.end_date, "%Y-%m-%dT%H:%M:%SZ")

                    dt_obj = pytz.utc.localize(end_date)
                    try:
                        configured_tz = pytz.timezone(TIMEZONE)
                    except pytz.exceptions.UnknownTimeZoneError:
                        logger.warning(
                            "Unknown timezone %r — falling back to UTC. "
                            "Set a valid IANA timezone in the TIMEZONE environment variable.",
                            TIMEZONE,
                        )
                        configured_tz = pytz.utc
                    localized_end_date = dt_obj.astimezone(configured_tz)

                    # Compute UTC offset dynamically from the localized date (e.g. "UTC+05:30")
                    tz_offset_str = localized_end_date.strftime("%z")  # e.g. "-0600" or "+0530"
                    if tz_offset_str and len(tz_offset_str) == 5:
                        sign = "+" if tz_offset_str[0] == "+" else "-"
                        hours = tz_offset_str[1:3]
                        minutes = tz_offset_str[3:5]
                        utc_label = f"UTC{sign}{hours}:{minutes}"
                    else:
                        utc_label = "UTC"

                    # Format the final string, including the timezone name for context
                    formatted_end_date = f"{localized_end_date.strftime(DATE_FORMAT)} {utc_label} ({TIMEZONE})"

                store_meta = _STORE_META.get(game.store, _STORE_META["epic"])
                if formatted_end_date:
                    footer_text = f"{_T['ends_on']} {formatted_end_date}"
                elif game.is_permanent:
                    footer_text = _T["permanently_free"]
                else:
                    footer_text = _T["end_date_unavailable"]

                fields = []
                if game.game_type == "dlc":
                    fields.append({
                        "name": _T["dlc_badge"],
                        "value": _T["requires_base_game"],
                        "inline": True,
                    })
                if game.original_price:
                    fields.append({
                        "name": _T["original_price"],
                        "value": game.original_price,
                        "inline": True,
                    })

                embed = {
                    "author": {
                        "name": store_meta["name"],
                        "url": store_meta["url"],
                        "icon_url": store_meta["icon_url"],
                    },
                    "title": game.title,
                    "url": game.url,
                    "description": game.description.replace("'", ""),
                    "color": store_meta["color"],
                    "image": {
                        "url": game.image_url
                    },
                    "footer": {
                        "text": footer_text
                    },
                }
                if fields:
                    embed["fields"] = fields
                if game.review_scores:
                    _REVIEW_EMOJIS = {
                        "overwhelmingly positive": "🏆",
                        "very positive": "⭐",
                        "mostly positive": "👍",
                        "positive": "✅",
                        "mixed": "⚖️",
                        "mostly negative": "👎",
                        "negative": "❌",
                        "very negative": "⛔",
                        "overwhelmingly negative": "💀",
                    }

                    def _critic_emoji(score_val: int) -> str:
                        if score_val >= 90:
                            return "🏆"
                        if score_val >= 75:
                            return "⭐"
                        if score_val >= 61:
                            return "👍"
                        if score_val >= 40:
                            return "⚖️"
                        return "👎"

                    score_lines = []
                    for score_str in game.review_scores:
                        if score_str.startswith("Metascore: "):
                            try:
                                val = int(score_str.split(": ", 1)[1])
                                score_lines.append(
                                    f"{_T['metacritic_reviews']} {score_str} {_critic_emoji(val)}"
                                )
                            except (ValueError, IndexError):
                                score_lines.append(f"{_T['metacritic_reviews']} {score_str}")
                        else:
                            # Steam-style user review label
                            key = score_str.lower()
                            emoji = _REVIEW_EMOJIS.get(key, "🎮")
                            label = _T["review_labels"].get(key, score_str)
                            score_lines.append(f"{_T['user_reviews']} {label} {emoji}")

                    if score_lines:
                        embed["description"] += "\n\n" + "\n".join(score_lines) + "\n\n"
                embeds.append(embed)
            except (AttributeError, ValueError) as e:
                logger.error(f"Error processing game data for embed: {str(e)} | Game data: {game}")
                raise

        stores_in_batch = {game.store for game in new_games}
        all_dlcs = all(g.game_type == "dlc" for g in new_games)
        if len(stores_in_batch) == 1:
            store_key = next(iter(stores_in_batch))
            store_name = _STORE_META.get(store_key, _STORE_META["epic"])["name"]
            if all_dlcs:
                content = _T["new_free_dlc"].format(store=store_name)
            else:
                content = _T["new_free_game"].format(store=store_name)
        else:
            content = _T["new_free_games"]

        data = {
            "content": content,
            "embeds": embeds
        }
        logger.info(f"Sending Discord message with {len(embeds)} game(s)")

        safe_webhook_id = _get_safe_webhook_identifier(effective_webhook_url)

        # Send the request with retry logic for transient network errors
        response = with_retry(
            func=lambda: requests.post(effective_webhook_url, json=data, timeout=10),
            max_attempts=2,
            base_delay=1,
            retryable_exceptions=_DISCORD_RETRYABLE,
            description=f"Discord webhook send ({safe_webhook_id})",
        )

        # Validate HTTP response status (200-299 range)
        if 200 <= response.status_code <= 299:
            logger.info(f"Discord message sent successfully (Status: {response.status_code})")
        else:
            error_context = {
                "status_code": response.status_code,
                "webhook_url_pattern": safe_webhook_id,
                "response_text": response.text[:200],  # Limit response text for logging
                "num_games": len(new_games)
            }
            logger.error(f"Discord API returned non-success status: {error_context}")
            response.raise_for_status()  # Raise exception for bad status codes

    except requests.exceptions.Timeout:
        safe_webhook_id = _get_safe_webhook_identifier(effective_webhook_url)
        logger.error(
            f"Discord request timed out (10s per-attempt limit, all attempts exhausted) | Webhook identifier: {safe_webhook_id} | Games: {len(new_games)}"
        )
        raise
    except requests.exceptions.ConnectionError as e:
        safe_webhook_id = _get_safe_webhook_identifier(effective_webhook_url)
        logger.error(
            f"Discord connection error: {str(e)} | Webhook identifier: {safe_webhook_id} | Games: {len(new_games)}"
        )
        raise
    except requests.exceptions.RequestException as e:
        safe_webhook_id = _get_safe_webhook_identifier(effective_webhook_url)
        logger.error(
            f"Discord request failed: {str(e)} | Webhook identifier: {safe_webhook_id} | Games: {len(new_games)}"
        )
        raise
    except Exception as e:
        logger.error(f"Unexpected error sending Discord message: {str(e)} | Games: {len(new_games)}")
        raise

