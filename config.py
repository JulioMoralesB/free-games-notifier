import logging
import os

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Ensure data directory exists
os.makedirs("data", exist_ok=True)

# Epic Games API URL
EPIC_GAMES_API_URL = os.getenv("EPIC_GAMES_API_URL", "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions")

# Comma-separated list of store identifiers to fetch free games from (e.g. "epic,steam").
# Defaults to "epic" for backwards compatibility. Unknown stores are ignored with a warning.
_raw_enabled_stores = os.getenv("ENABLED_STORES", "epic")
ENABLED_STORES = [s.strip().lower() for s in _raw_enabled_stores.split(",") if s.strip()]

# Steam Store search URL
STEAM_SEARCH_URL = os.getenv("STEAM_SEARCH_URL", "https://store.steampowered.com/search/")

# ─────────────────────────────────────────────────────────────────────────────
# Unified region config
#
# Set REGION to an IANA timezone string (e.g. "America/Mexico_City").
# This simultaneously sets your timezone AND derives LOCALE, EPIC_GAMES_REGION,
# STEAM_LANGUAGE, and STEAM_COUNTRY from the profile table below.
# Any of those four vars can still be set individually to override the derived
# value (individual var always wins).
#
# Supported values — use exactly as written:
#   America/Mexico_City · America/New_York · America/Chicago
#   America/Los_Angeles · America/Toronto · America/Sao_Paulo
#   America/Argentina/Buenos_Aires · Europe/Madrid · Europe/London
#   Europe/Berlin · Europe/Paris · Europe/Rome · Europe/Warsaw
#   Europe/Moscow · Europe/Istanbul · Asia/Tokyo · Asia/Seoul
#   Asia/Shanghai · Australia/Sydney · Europe/Lisbon · Europe/Amsterdam
# ─────────────────────────────────────────────────────────────────────────────
REGION = os.getenv("REGION", "")

# Each key is an IANA timezone string. The value defines the locale/store
# profile for that timezone. TIMEZONE is derived directly from REGION itself.
# To add a new entry: copy an existing profile and fill in the four fields.
_REGION_PROFILES: dict[str, dict[str, str]] = {
    # ── Americas ──────────────────────────────────────────────────────────────
    "America/Mexico_City": {
        "locale":         "es_MX.UTF-8",
        "epic_region":    "es-MX",
        "steam_language": "spanish",
        "steam_country":  "MX",
    },
    "America/New_York": {
        "locale":         "en_US.UTF-8",
        "epic_region":    "en-US",
        "steam_language": "english",
        "steam_country":  "US",
    },
    "America/Chicago": {
        "locale":         "en_US.UTF-8",
        "epic_region":    "en-US",
        "steam_language": "english",
        "steam_country":  "US",
    },
    "America/Denver": {
        "locale":         "en_US.UTF-8",
        "epic_region":    "en-US",
        "steam_language": "english",
        "steam_country":  "US",
    },
    "America/Los_Angeles": {
        "locale":         "en_US.UTF-8",
        "epic_region":    "en-US",
        "steam_language": "english",
        "steam_country":  "US",
    },
    "America/Toronto": {
        "locale":         "en_CA.UTF-8",
        "epic_region":    "en-CA",
        "steam_language": "english",
        "steam_country":  "CA",
    },
    "America/Sao_Paulo": {
        "locale":         "pt_BR.UTF-8",
        "epic_region":    "pt-BR",
        "steam_language": "portuguese",
        "steam_country":  "BR",
    },
    "America/Argentina/Buenos_Aires": {
        "locale":         "es_AR.UTF-8",
        "epic_region":    "es-AR",
        "steam_language": "spanish",
        "steam_country":  "AR",
    },
    # ── Europe ────────────────────────────────────────────────────────────────
    "Europe/Madrid": {
        "locale":         "es_ES.UTF-8",
        "epic_region":    "es-ES",
        "steam_language": "spanish",
        "steam_country":  "ES",
    },
    "Europe/London": {
        "locale":         "en_GB.UTF-8",
        "epic_region":    "en-GB",
        "steam_language": "english",
        "steam_country":  "GB",
    },
    "Europe/Berlin": {
        "locale":         "de_DE.UTF-8",
        "epic_region":    "de-DE",
        "steam_language": "german",
        "steam_country":  "DE",
    },
    "Europe/Paris": {
        "locale":         "fr_FR.UTF-8",
        "epic_region":    "fr-FR",
        "steam_language": "french",
        "steam_country":  "FR",
    },
    "Europe/Rome": {
        "locale":         "it_IT.UTF-8",
        "epic_region":    "it-IT",
        "steam_language": "italian",
        "steam_country":  "IT",
    },
    "Europe/Warsaw": {
        "locale":         "pl_PL.UTF-8",
        "epic_region":    "pl-PL",
        "steam_language": "polish",
        "steam_country":  "PL",
    },
    "Europe/Moscow": {
        "locale":         "ru_RU.UTF-8",
        "epic_region":    "ru-RU",
        "steam_language": "russian",
        "steam_country":  "RU",
    },
    "Europe/Istanbul": {
        "locale":         "tr_TR.UTF-8",
        "epic_region":    "tr-TR",
        "steam_language": "turkish",
        "steam_country":  "TR",
    },
    "Europe/Lisbon": {
        "locale":         "pt_PT.UTF-8",
        "epic_region":    "pt-PT",
        "steam_language": "portuguese",
        "steam_country":  "PT",
    },
    "Europe/Amsterdam": {
        "locale":         "nl_NL.UTF-8",
        "epic_region":    "nl-NL",
        "steam_language": "dutch",
        "steam_country":  "NL",
    },
    # ── Asia / Pacific ────────────────────────────────────────────────────────
    "Asia/Tokyo": {
        "locale":         "ja_JP.UTF-8",
        "epic_region":    "ja-JP",
        "steam_language": "japanese",
        "steam_country":  "JP",
    },
    "Asia/Seoul": {
        "locale":         "ko_KR.UTF-8",
        "epic_region":    "ko-KR",
        "steam_language": "koreana",
        "steam_country":  "KR",
    },
    "Asia/Shanghai": {
        "locale":         "zh_CN.UTF-8",
        "epic_region":    "zh-CN",
        "steam_language": "schinese",
        "steam_country":  "CN",
    },
    "Australia/Sydney": {
        "locale":         "en_AU.UTF-8",
        "epic_region":    "en-AU",
        "steam_language": "english",
        "steam_country":  "AU",
    },
}


def _region_get(region: str, key: str) -> str:
    """Look up one derived value for a region/timezone. Returns '' when not in the table."""
    return _REGION_PROFILES.get(region, {}).get(key, "")


def _resolve(env_var: str, region_derived: str, default: str) -> str:
    """Resolve a config value: explicit env var (non-empty) > REGION derivation > hardcoded default.

    An empty string is treated the same as "not set", so that compose.yaml can
    forward ``${VAR}`` (which expands to '' when unset) without blocking REGION
    derivation.
    """
    explicit = os.getenv(env_var)
    if explicit:  # non-None and non-empty
        return explicit
    if region_derived:
        return region_derived
    return default


# Language for Steam appdetails API (e.g. "english", "spanish").
# Derived from REGION when not set explicitly; falls back to "english".
STEAM_LANGUAGE = _resolve("STEAM_LANGUAGE", _region_get(REGION, "steam_language"), "english")

# Country code for Steam store requests — controls price currency (e.g. "US", "MX").
# Derived from REGION when not set explicitly; falls back to "US".
STEAM_COUNTRY = _resolve("STEAM_COUNTRY", _region_get(REGION, "steam_country"), "US")

# Minimum delay in milliseconds between Steam HTTP requests to avoid rate limiting
_raw_steam_delay = os.getenv("STEAM_REQUEST_DELAY_MS")
try:
    STEAM_REQUEST_DELAY_MS = max(0, int(_raw_steam_delay)) if _raw_steam_delay not in (None, "") else 1500
except ValueError:
    STEAM_REQUEST_DELAY_MS = 1500

# Discord Webhook URL (loaded from .env)
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

# Path to store free games data
DATA_FILE_PATH = "/mnt/data/free_games.json" # This path can be overridden by mounting a volume in Docker

# Path to store the last sent notification batch (used by the resend endpoint)
LAST_NOTIFICATION_FILE_PATH = "/mnt/data/last_notification.json"

# URL to Healthcheck Monitor
HEALTHCHECK_URL = os.getenv("HEALTHCHECK_URL")

# Enable or disable healthcheck based on environment variable
ENABLE_HEALTHCHECK = os.getenv("ENABLE_HEALTHCHECK", "false").lower() == "true"

# Database configuration
DB_CONNECT_TIMEOUT = 10  # seconds; applies to all psycopg2.connect() calls
DB_HOST = os.getenv("DB_HOST") or None
_raw_db_port = os.getenv("DB_PORT")
DB_PORT = int(_raw_db_port) if _raw_db_port and _raw_db_port.strip() else 5432
DB_NAME = os.getenv("DB_NAME") or None
DB_USER = os.getenv("DB_USER") or None
DB_PASSWORD = os.getenv("DB_PASSWORD") or None

# Timezone for date display in notifications.
# REGION itself is an IANA timezone string, so it's used directly.
# Falls back to "UTC" if REGION is not set or not recognised.
TIMEZONE = _resolve("TIMEZONE", REGION, "UTC")

# Locale for date formatting (e.g. "en_US.UTF-8", "es_MX.UTF-8").
# Derived from REGION when not set explicitly; falls back to "en_US.UTF-8".
LOCALE = _resolve("LOCALE", _region_get(REGION, "locale"), "en_US.UTF-8")

# Epic Games region used in store links (e.g. "en-US", "es-MX", "de-DE").
# Derived from REGION when not set explicitly; falls back to "en-US".
EPIC_GAMES_REGION = _resolve("EPIC_GAMES_REGION", _region_get(REGION, "epic_region"), "en-US")

# How often to check for new free games, in hours.
# When set, the service runs on a repeating interval (e.g. every 6 hours).
# When left empty, the service falls back to SCHEDULE_TIME and runs once per day.
# Recommended for multi-store setups (Steam games can appear at any time).
# Minimum value is 1 hour.
_raw_check_interval = os.getenv("CHECK_INTERVAL_HOURS")
try:
    if _raw_check_interval in (None, ""):
        CHECK_INTERVAL_HOURS = None
    else:
        _parsed = float(_raw_check_interval)
        if _parsed < 1:
            logging.warning(
                "CHECK_INTERVAL_HOURS value %r is below the 1-hour minimum; defaulting to 1 hour.",
                _raw_check_interval,
            )
            CHECK_INTERVAL_HOURS = 1.0
        else:
            CHECK_INTERVAL_HOURS = _parsed
except ValueError:
    logging.error(
        "Invalid CHECK_INTERVAL_HOURS value %r (not a number); falling back to SCHEDULE_TIME.",
        _raw_check_interval,
    )
    CHECK_INTERVAL_HOURS = None

# Daily schedule time in HH:MM format at which free games are checked.
# Used only when CHECK_INTERVAL_HOURS is not set.
# NOTE: This time is interpreted in the configured TIMEZONE (see TIMEZONE above), not fixed to UTC.
SCHEDULE_TIME = os.getenv("SCHEDULE_TIME", "12:00")

# Health check ping interval in minutes
_raw_healthcheck_interval = os.getenv("HEALTHCHECK_INTERVAL")
try:
    if _raw_healthcheck_interval in (None, ""):
        HEALTHCHECK_INTERVAL = 1
    else:
        HEALTHCHECK_INTERVAL = max(1, int(_raw_healthcheck_interval))
except ValueError:
    HEALTHCHECK_INTERVAL = 1

# strftime format string used when displaying the promotion end date in Discord notifications.
# The default is English-style; change to match your locale, e.g. "%d de %B de %Y a las %I:%M %p" for LOCALE="es_ES.UTF-8".
DATE_FORMAT = os.getenv("DATE_FORMAT", "%B %d, %Y at %I:%M %p")

# REST API configuration
API_KEY = os.getenv("API_KEY")  # Secret key for mutating API endpoints; leave empty to disable auth
API_HOST = os.getenv("API_HOST", "0.0.0.0")
_raw_api_port = os.getenv("API_PORT")
try:
    if _raw_api_port in (None, ""):
        API_PORT = 8000
    else:
        _parsed_api_port = int(_raw_api_port)
        if 1 <= _parsed_api_port <= 65535:
            API_PORT = _parsed_api_port
        else:
            logging.error(
                "API_PORT '%s' is out of valid range (1–65535); defaulting to 8000",
                _raw_api_port,
            )
            API_PORT = 8000
except ValueError:
    logging.error(
        "Invalid API_PORT '%s' (not a number); defaulting to 8000",
        _raw_api_port,
    )
    API_PORT = 8000
