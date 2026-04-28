"""Tests for the REGION-based config derivation in config.py."""
from unittest.mock import patch

import pytest

from config import _REGION_PROFILES, _region_get, _resolve


class TestRegionGet:
    """_region_get(region, key) returns the correct profile value."""

    def test_mx_timezone(self):
        # TIMEZONE comes from REGION directly, but the profile doesn't store it.
        # Verify other fields for MX.
        assert _region_get("America/Mexico_City", "locale") == "es_MX.UTF-8"

    def test_mx_locale(self):
        assert _region_get("America/Mexico_City", "locale") == "es_MX.UTF-8"

    def test_mx_epic_region(self):
        assert _region_get("America/Mexico_City", "epic_region") == "es-MX"

    def test_mx_steam_language(self):
        assert _region_get("America/Mexico_City", "steam_language") == "spanish"

    def test_mx_steam_country(self):
        assert _region_get("America/Mexico_City", "steam_country") == "MX"

    def test_us_new_york(self):
        assert _region_get("America/New_York", "steam_country") == "US"
        assert _region_get("America/New_York", "steam_language") == "english"

    def test_us_chicago_same_profile_as_new_york(self):
        """All US timezones share the same locale/language profile."""
        assert _region_get("America/Chicago", "steam_country") == "US"
        assert _region_get("America/Chicago", "locale") == "en_US.UTF-8"

    def test_us_los_angeles(self):
        assert _region_get("America/Los_Angeles", "steam_country") == "US"

    def test_us_denver(self):
        assert _region_get("America/Denver", "steam_country") == "US"

    def test_de_berlin(self):
        assert _region_get("Europe/Berlin", "locale") == "de_DE.UTF-8"
        assert _region_get("Europe/Berlin", "steam_language") == "german"
        assert _region_get("Europe/Berlin", "steam_country") == "DE"

    def test_br_sao_paulo(self):
        assert _region_get("America/Sao_Paulo", "locale") == "pt_BR.UTF-8"
        assert _region_get("America/Sao_Paulo", "steam_language") == "portuguese"
        assert _region_get("America/Sao_Paulo", "steam_country") == "BR"

    def test_jp_tokyo(self):
        assert _region_get("Asia/Tokyo", "steam_language") == "japanese"
        assert _region_get("Asia/Tokyo", "steam_country") == "JP"

    def test_returns_empty_for_unknown_region(self):
        assert _region_get("Invalid/Timezone", "locale") == ""
        assert _region_get("Invalid/Timezone", "steam_country") == ""

    def test_returns_empty_for_empty_region(self):
        assert _region_get("", "locale") == ""


class TestRegionProfilesCompleteness:
    """Every profile in _REGION_PROFILES has all required keys."""

    REQUIRED_KEYS = {"locale", "epic_region", "steam_language", "steam_country"}

    @pytest.mark.parametrize("tz", list(_REGION_PROFILES.keys()))
    def test_profile_has_all_keys(self, tz):
        profile = _REGION_PROFILES[tz]
        missing = self.REQUIRED_KEYS - profile.keys()
        assert not missing, f"Profile '{tz}' is missing keys: {missing}"

    @pytest.mark.parametrize("tz", list(_REGION_PROFILES.keys()))
    def test_profile_values_are_non_empty(self, tz):
        profile = _REGION_PROFILES[tz]
        empty = [k for k in self.REQUIRED_KEYS if not profile.get(k)]
        assert not empty, f"Profile '{tz}' has empty values for: {empty}"


class TestResolve:
    def test_explicit_env_var_takes_precedence(self):
        with patch.dict("os.environ", {"MY_VAR": "explicit"}):
            assert _resolve("MY_VAR", "derived", "default") == "explicit"

    def test_falls_through_to_region_derived_when_not_set(self):
        env = {k: v for k, v in __import__("os").environ.items() if k != "MY_VAR"}
        with patch("os.environ", env):
            assert _resolve("MY_VAR", "derived", "default") == "derived"

    def test_falls_through_to_default_when_both_missing(self):
        env = {k: v for k, v in __import__("os").environ.items() if k != "MY_VAR"}
        with patch("os.environ", env):
            assert _resolve("MY_VAR", "", "default") == "default"

    def test_empty_env_var_treated_as_unset(self):
        """Empty string (Docker Compose ${VAR} expansion) falls through to derived."""
        with patch.dict("os.environ", {"MY_VAR": ""}):
            assert _resolve("MY_VAR", "derived", "default") == "derived"


class TestRegionIntegration:
    """End-to-end: REGION=America/Mexico_City derives all five values correctly."""

    def test_timezone_is_region_itself(self):
        """TIMEZONE is derived directly from REGION — no separate lookup needed."""
        region = "America/Mexico_City"
        # _resolve("TIMEZONE", REGION, "UTC") → REGION when not overridden
        env = {k: v for k, v in __import__("os").environ.items() if k != "TIMEZONE"}
        with patch("os.environ", env):
            assert _resolve("TIMEZONE", region, "UTC") == "America/Mexico_City"

    def test_locale(self):
        assert _region_get("America/Mexico_City", "locale") == "es_MX.UTF-8"

    def test_epic_region(self):
        assert _region_get("America/Mexico_City", "epic_region") == "es-MX"

    def test_steam_language(self):
        assert _region_get("America/Mexico_City", "steam_language") == "spanish"

    def test_steam_country(self):
        assert _region_get("America/Mexico_City", "steam_country") == "MX"

    def test_individual_override_wins(self):
        """Explicit LOCALE overrides what REGION would derive."""
        with patch.dict("os.environ", {"LOCALE": "fr_FR.UTF-8"}):
            result = _resolve("LOCALE", _region_get("America/Mexico_City", "locale"), "en_US.UTF-8")
        assert result == "fr_FR.UTF-8"

    def test_region_wins_over_default(self):
        env = {k: v for k, v in __import__("os").environ.items() if k != "LOCALE"}
        with patch("os.environ", env):
            result = _resolve("LOCALE", _region_get("America/Mexico_City", "locale"), "en_US.UTF-8")
        assert result == "es_MX.UTF-8"
