from datetime import datetime as _real_datetime
from datetime import timezone as _utc_tz
from unittest.mock import MagicMock, patch

import pytest
import requests as req

from modules.scrapers.steam import SteamScraper, _parse_steam_end_date


class _FakeDatetime(_real_datetime):
    """Pins datetime.now() to 2026-01-01 UTC for deterministic year-rollover tests.

    _parse_steam_end_date uses datetime.now() to decide whether the parsed promo
    date has already passed and should roll over to next year. Without pinning 'now',
    any test that asserts a specific year (e.g. "2026-04-23") breaks as soon as the
    promo date passes in real time. _FakeDatetime is a subclass so the datetime()
    constructor used in the same function still works normally.
    """
    @classmethod
    def now(cls, tz=None):
        return _real_datetime(2026, 1, 1, tzinfo=tz if tz is not None else _utc_tz)


@pytest.fixture
def freeze_steam_now():
    """Pin datetime.now() for deterministic timestamp assertions.

    _parse_steam_end_date always treats scraped times as Pacific Time
    (America/Los_Angeles) regardless of the user's TIMEZONE setting, so we no
    longer need to patch TIMEZONE here.  The only remaining patch is to pin
    datetime.now() so the year-rollover logic gives a stable result.
    """
    with patch("modules.scrapers.steam.datetime", _FakeDatetime):
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(status_code=200, json_data=None, text=""):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data if json_data is not None else {}
    mock.text = text
    return mock


def _make_search_html(games=None):
    """Build a minimal Steam search results HTML page."""
    if games is None:
        games = [
            {
                "appid": "978520",
                "title": "Test Free Game",
                "original_price": "$19.99",
                "price_final": 0,
            }
        ]

    rows = ""
    for g in games:
        rows += f"""
        <a class="search_result_row"
           href="https://store.steampowered.com/app/{g['appid']}/Game_Title/?snr=1"
           data-ds-appid="{g['appid']}">
          <span class="title">{g['title']}</span>
          <div class="search_price_discount_combined responsive_secondrow"
               data-price-final="{g['price_final']}">
            <div class="discount_block" data-discount="100" data-price-final="{g['price_final']}">
              <div class="discount_pct">-100%</div>
              <div class="discount_prices">
                <div class="discount_original_price">{g['original_price']}</div>
                <div class="discount_final_price">Free</div>
              </div>
            </div>
          </div>
        </a>
        """

    return f"""<html><body>
    <div id="search_resultsRows">{rows}</div>
    </body></html>"""


def _make_appdetails_response(appid, short_description="A test game.", header_image="https://example.com/header.jpg", app_type="game"):
    return {
        appid: {
            "success": True,
            "data": {
                "type": app_type,
                "short_description": short_description,
                "header_image": header_image,
            },
        }
    }


def _make_appreviews_response(review_score_desc="Mostly Positive"):
    return {
        "query_summary": {
            "review_score_desc": review_score_desc,
            "total_positive": 100,
            "total_negative": 20,
            "total_reviews": 120,
        }
    }


_STORE_PAGE_HTML = """<html><body>
    <div class="game_purchase_action">
      <p class="game_purchase_discount_quantity">
        Free to keep when you get it before 23 Apr @ 10:00am. Some limitations apply.
      </p>
    </div>
</body></html>"""


def _multi_url_mock(appid="978520"):
    """Return a side_effect function that dispatches by URL."""
    def side_effect(url, **kwargs):
        if "search" in url:
            return _mock_response(200, text=_make_search_html())
        if "appdetails" in url:
            return _mock_response(200, json_data=_make_appdetails_response(appid))
        if "appreviews" in url:
            return _mock_response(200, json_data=_make_appreviews_response())
        if "store.steampowered.com/app/" in url:
            return _mock_response(200, text=_STORE_PAGE_HTML)
        return _mock_response(404)
    return side_effect


def _multi_url_mock_with_desc(description: str, appid="978520"):
    """Like _multi_url_mock but injects a custom short_description."""
    def side_effect(url, **kwargs):
        if "search" in url:
            return _mock_response(200, text=_make_search_html())
        if "appdetails" in url:
            return _mock_response(200, json_data=_make_appdetails_response(appid, short_description=description))
        if "appreviews" in url:
            return _mock_response(200, json_data=_make_appreviews_response())
        if "store.steampowered.com/app/" in url:
            return _mock_response(200, text=_STORE_PAGE_HTML)
        return _mock_response(404)
    return side_effect


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSteamScraper:
    @pytest.fixture(autouse=True)
    def no_sleep(self):
        with patch("modules.scrapers.steam.time.sleep"):
            yield

    @pytest.fixture(autouse=True)
    def no_review_sources(self):
        """Suppress external Metacritic requests in all Steam scraper tests."""
        with patch("modules.scrapers.steam.fetch_metacritic_score", return_value=None):
            yield

    def test_store_name(self):
        assert SteamScraper().store_name == "steam"

    def test_returns_free_game(self, freeze_steam_now):
        with patch("modules.scrapers.steam.requests.get", side_effect=_multi_url_mock()):
            games = SteamScraper().fetch_free_games()

        assert len(games) == 1
        g = games[0]
        assert g.title == "Test Free Game"
        assert g.store == "steam"
        assert g.url == "https://store.steampowered.com/app/978520/Game_Title/"
        assert g.original_price == "$19.99"
        assert g.description == "A test game."
        assert g.image_url == "https://example.com/header.jpg"
        assert "Mostly Positive" in g.review_scores
        assert g.is_permanent is False
        # "23 Apr @ 10:00am" Pacific = 10:00 PDT (UTC-7) = 17:00 UTC
        assert "2026-04-23T17:00:00" in g.end_date

    def test_excludes_paid_games(self):
        paid = [{"appid": "111", "title": "Paid Game", "original_price": "$9.99", "price_final": 999}]
        html = _make_search_html(paid)

        with patch("modules.scrapers.steam.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, text=html)
            games = SteamScraper().fetch_free_games()

        assert games == []

    def test_excludes_free_to_play(self):
        """Games without a .discount_original_price element are permanently F2P."""
        html = """<html><body><div id="search_resultsRows">
            <a class="search_result_row"
               href="https://store.steampowered.com/app/99999/"
               data-ds-appid="99999">
              <span class="title">F2P Game</span>
              <div data-price-final="0">
                <div class="discount_final_price">Free to Play</div>
              </div>
            </a>
        </div></body></html>"""

        with patch("modules.scrapers.steam.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, text=html)
            games = SteamScraper().fetch_free_games()

        assert games == []

    def test_returns_empty_on_http_error(self):
        with patch("modules.scrapers.steam.requests.get") as mock_get:
            mock_get.return_value = _mock_response(500)
            games = SteamScraper().fetch_free_games()

        assert games == []

    def test_returns_empty_on_connection_error(self):
        with patch("modules.scrapers.steam.requests.get", side_effect=req.exceptions.ConnectionError):
            with patch("modules.retry.time.sleep"):
                games = SteamScraper().fetch_free_games()

        assert games == []

    def test_returns_empty_on_rate_limit(self):
        """HTTP 429 on search should retry then give up and return empty list."""
        with patch("modules.scrapers.steam.requests.get") as mock_get:
            mock_get.return_value = _mock_response(429)
            with patch("modules.retry.time.sleep"):
                games = SteamScraper().fetch_free_games()

        assert games == []
        assert mock_get.call_count == 4  # max_attempts=4

    def test_request_delay_is_applied(self):
        """Each Steam HTTP call must be preceded by a sleep."""
        with patch("modules.scrapers.steam.requests.get", side_effect=_multi_url_mock()):
            with patch("modules.scrapers.steam.time.sleep") as mock_sleep:
                SteamScraper().fetch_free_games()

        assert mock_sleep.call_count >= 4  # search + appdetails + reviews + end_date

    def test_gracefully_handles_failed_appdetails(self):
        """Game is still returned even if the appdetails call fails."""
        def side_effect(url, **kwargs):
            if "search" in url:
                return _mock_response(200, text=_make_search_html())
            if "appdetails" in url:
                return _mock_response(500)
            if "appreviews" in url:
                return _mock_response(200, json_data=_make_appreviews_response())
            return _mock_response(404)

        with patch("modules.scrapers.steam.requests.get", side_effect=side_effect):
            games = SteamScraper().fetch_free_games()

        assert len(games) == 1
        assert games[0].description == ""
        assert "capsule_sm_120" in games[0].image_url

    def test_gracefully_handles_failed_review_fetch(self):
        """Game is still returned even if the review score call fails."""
        def side_effect(url, **kwargs):
            if "search" in url:
                return _mock_response(200, text=_make_search_html())
            if "appdetails" in url:
                return _mock_response(200, json_data=_make_appdetails_response("978520"))
            if "appreviews" in url:
                return _mock_response(500)
            return _mock_response(404)

        with patch("modules.scrapers.steam.requests.get", side_effect=side_effect):
            games = SteamScraper().fetch_free_games()

        assert len(games) == 1
        assert games[0].review_scores == []

    def test_multiple_free_games_returned(self):
        games_data = [
            {"appid": "111", "title": "Game One", "original_price": "$5.99", "price_final": 0},
            {"appid": "222", "title": "Game Two", "original_price": "$9.99", "price_final": 0},
        ]
        html = _make_search_html(games_data)

        def side_effect(url, **kwargs):
            if "search" in url:
                return _mock_response(200, text=html)
            params = kwargs.get("params", {})
            appid = str(params.get("appids", ""))
            if "appdetails" in url:
                return _mock_response(200, json_data=_make_appdetails_response(appid))
            if "appreviews" in url:
                return _mock_response(200, json_data=_make_appreviews_response())
            return _mock_response(404)

        with patch("modules.scrapers.steam.requests.get", side_effect=side_effect):
            games = SteamScraper().fetch_free_games()

        assert len(games) == 2
        titles = {g.title for g in games}
        assert "Game One" in titles
        assert "Game Two" in titles

    def test_parse_search_page_strips_query_from_url(self):
        html = _make_search_html()
        candidates = SteamScraper()._parse_search_page(html)
        assert candidates[0]["url"] == "https://store.steampowered.com/app/978520/Game_Title/"
        assert "?" not in candidates[0]["url"]

    def test_skips_bundle_rows_with_multiple_appids(self):
        """Rows with comma-separated appids are bundles — skip them."""
        html = """<html><body><div id="search_resultsRows">
            <a class="search_result_row"
               href="https://store.steampowered.com/bundle/999/"
               data-ds-appid="111,222">
              <span class="title">Some Bundle</span>
              <div data-price-final="0">
                <div class="discount_original_price">$29.99</div>
              </div>
            </a>
        </div></body></html>"""

        with patch("modules.scrapers.steam.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, text=html)
            games = SteamScraper().fetch_free_games()

        assert games == []

    def test_parse_search_page_empty_results(self):
        html = "<html><body><div id='search_resultsRows'></div></body></html>"
        candidates = SteamScraper()._parse_search_page(html)
        assert candidates == []

    def test_gracefully_handles_failed_end_date_fetch(self):
        def side_effect(url, **kwargs):
            if "search" in url:
                return _mock_response(200, text=_make_search_html())
            if "appdetails" in url:
                return _mock_response(200, json_data=_make_appdetails_response("978520"))
            if "appreviews" in url:
                return _mock_response(200, json_data=_make_appreviews_response())
            if "store.steampowered.com/app/" in url:
                return _mock_response(500)
            return _mock_response(404)

        with patch("modules.scrapers.steam.requests.get", side_effect=side_effect):
            games = SteamScraper().fetch_free_games()

        assert len(games) == 1
        assert games[0].end_date == ""

    def test_end_date_falls_back_to_full_page_text(self, freeze_steam_now):
        """If .game_purchase_discount_quantity is absent, the date is found in the page body."""
        store_page_no_element = """<html><body>
            <div class="game_purchase_action">
              <p>Free to keep when you get it before 23 Apr @ 10:00am. Some limitations apply.</p>
            </div>
        </body></html>"""

        def side_effect(url, **kwargs):
            if "search" in url:
                return _mock_response(200, text=_make_search_html())
            if "appdetails" in url:
                return _mock_response(200, json_data=_make_appdetails_response("978520"))
            if "appreviews" in url:
                return _mock_response(200, json_data=_make_appreviews_response())
            if "store.steampowered.com/app/" in url:
                return _mock_response(200, text=store_page_no_element)
            return _mock_response(404)

        with patch("modules.scrapers.steam.requests.get", side_effect=side_effect):
            games = SteamScraper().fetch_free_games()

        assert len(games) == 1
        # "23 Apr @ 10:00am" Pacific = 10:00 PDT (UTC-7) = 17:00 UTC
        assert "2026-04-23T17:00:00" in games[0].end_date

    def test_html_entities_in_description_are_decoded(self, freeze_steam_now):
        """HTML entities in short_description (e.g. &quot;) are unescaped before use."""
        with patch("modules.scrapers.steam.requests.get",
                   side_effect=_multi_url_mock_with_desc('&quot;8AM&quot; is a suspense game.')):
            games = SteamScraper().fetch_free_games()

        assert len(games) == 1
        assert games[0].description == '"8AM" is a suspense game.'
        assert "&quot;" not in games[0].description

    def test_appdetails_uses_configured_language(self):
        """_fetch_appdetails passes STEAM_LANGUAGE as the l= param to the API."""
        captured = {}

        def side_effect(url, **kwargs):
            if "appdetails" in url:
                captured["params"] = kwargs.get("params", {})
                return _mock_response(200, json_data=_make_appdetails_response("978520"))
            if "search" in url:
                return _mock_response(200, text=_make_search_html())
            if "appreviews" in url:
                return _mock_response(200, json_data=_make_appreviews_response())
            return _mock_response(200, text="<html></html>")

        with patch("modules.scrapers.steam.requests.get", side_effect=side_effect), \
             patch("modules.scrapers.steam.STEAM_LANGUAGE", "spanish"):
            SteamScraper().fetch_free_games()

        assert captured.get("params", {}).get("l") == "spanish"

    def test_appdetails_defaults_to_english(self):
        """Without STEAM_LANGUAGE override, the API is called with l=english."""
        captured = {}

        def side_effect(url, **kwargs):
            if "appdetails" in url:
                captured["params"] = kwargs.get("params", {})
                return _mock_response(200, json_data=_make_appdetails_response("978520"))
            if "search" in url:
                return _mock_response(200, text=_make_search_html())
            if "appreviews" in url:
                return _mock_response(200, json_data=_make_appreviews_response())
            return _mock_response(200, text="<html></html>")

        with patch("modules.scrapers.steam.requests.get", side_effect=side_effect), \
             patch("modules.scrapers.steam.STEAM_LANGUAGE", "english"):
            SteamScraper().fetch_free_games()

        assert captured.get("params", {}).get("l") == "english"

    def test_search_uses_configured_country(self):
        """fetch_free_games passes STEAM_COUNTRY as the cc= param in the search request."""
        captured = {}

        def side_effect(url, **kwargs):
            if "search" in url:
                captured["params"] = kwargs.get("params", {})
                return _mock_response(200, text=_make_search_html())
            if "appdetails" in url:
                return _mock_response(200, json_data=_make_appdetails_response("978520"))
            if "appreviews" in url:
                return _mock_response(200, json_data=_make_appreviews_response())
            return _mock_response(200, text="<html></html>")

        with patch("modules.scrapers.steam.requests.get", side_effect=side_effect), \
             patch("modules.scrapers.steam.STEAM_COUNTRY", "MX"):
            SteamScraper().fetch_free_games()

        assert captured.get("params", {}).get("cc") == "MX"

    def test_search_defaults_to_us_country(self):
        """Without a STEAM_COUNTRY override, the search uses cc=US."""
        captured = {}

        def side_effect(url, **kwargs):
            if "search" in url:
                captured["params"] = kwargs.get("params", {})
                return _mock_response(200, text=_make_search_html())
            if "appdetails" in url:
                return _mock_response(200, json_data=_make_appdetails_response("978520"))
            if "appreviews" in url:
                return _mock_response(200, json_data=_make_appreviews_response())
            return _mock_response(200, text="<html></html>")

        with patch("modules.scrapers.steam.requests.get", side_effect=side_effect), \
             patch("modules.scrapers.steam.STEAM_COUNTRY", "US"):
            SteamScraper().fetch_free_games()

        assert captured.get("params", {}).get("cc") == "US"

    def test_appdetails_uses_configured_country(self):
        """_fetch_appdetails passes STEAM_COUNTRY as the cc= param to the appdetails API."""
        captured = {}

        def side_effect(url, **kwargs):
            if "appdetails" in url:
                captured["params"] = kwargs.get("params", {})
                return _mock_response(200, json_data=_make_appdetails_response("978520"))
            if "search" in url:
                return _mock_response(200, text=_make_search_html())
            if "appreviews" in url:
                return _mock_response(200, json_data=_make_appreviews_response())
            return _mock_response(200, text="<html></html>")

        with patch("modules.scrapers.steam.requests.get", side_effect=side_effect), \
             patch("modules.scrapers.steam.STEAM_COUNTRY", "MX"):
            SteamScraper().fetch_free_games()

        assert captured.get("params", {}).get("cc") == "MX"


class TestParseSteamEndDate:
    # Steam always renders times in Pacific Time (America/Los_Angeles).
    # The fixture pins now=2026-01-01 UTC; April/May/June are PDT (UTC-7).
    # Expected UTC = scraped Pacific time + 7 hours.

    def test_parses_am_time(self, freeze_steam_now):
        text = "Free to keep when you get it before 23 Apr @ 10:00am. Some limitations apply."
        result = _parse_steam_end_date(text)
        # 10:00am PDT (UTC-7) = 17:00 UTC
        assert result.startswith("2026-04-23T17:00:00")

    def test_parses_pm_time(self, freeze_steam_now):
        text = "Free to keep when you get it before 5 Jun @ 2:00pm."
        result = _parse_steam_end_date(text)
        # 14:00 PDT (UTC-7) = 21:00 UTC
        assert "T21:00:00" in result

    def test_parses_noon(self, freeze_steam_now):
        text = "before 1 May @ 12:00pm"
        result = _parse_steam_end_date(text)
        # 12:00 PDT (UTC-7) = 19:00 UTC
        assert "T19:00:00" in result

    def test_parses_midnight(self, freeze_steam_now):
        text = "before 1 May @ 12:00am"
        result = _parse_steam_end_date(text)
        # 00:00 PDT (UTC-7) = 07:00 UTC
        assert "T07:00:00" in result

    def test_returns_empty_when_no_match(self):
        assert _parse_steam_end_date("No discount info here.") == ""

    def test_returns_empty_on_empty_string(self):
        assert _parse_steam_end_date("") == ""

    def test_handles_non_breaking_spaces(self, freeze_steam_now):
        """Steam HTML uses U+00A0 non-breaking spaces which look identical in logs."""
        text = "Free\u00a0to\u00a0keep\u00a0when\u00a0you\u00a0get\u00a0it\u00a0before\u00a023\u00a0Apr\u00a0@\u00a010:00am.\t\t\tSome limitations apply. (?)"
        result = _parse_steam_end_date(text)
        # 10:00am PDT (UTC-7) = 17:00 UTC
        assert result.startswith("2026-04-23T17:00:00")


# ---------------------------------------------------------------------------
# DLC detection tests
# ---------------------------------------------------------------------------

class TestDlcDetection:
    """Tests that game_type is read from the appdetails API 'type' field."""

    @pytest.fixture(autouse=True)
    def no_sleep(self):
        with patch("modules.scrapers.steam.time.sleep"):
            yield

    def test_fetch_free_games_returns_dlc_when_appdetails_type_is_dlc(self, freeze_steam_now):
        """Full pipeline: appdetails type='dlc' produces a FreeGame with game_type='dlc'."""
        appid = "978520"

        def side_effect(url, **kwargs):
            if "search" in url:
                return _mock_response(200, text=_make_search_html())
            if "appdetails" in url:
                return _mock_response(200, json_data=_make_appdetails_response(appid, app_type="dlc"))
            if "appreviews" in url:
                return _mock_response(200, json_data=_make_appreviews_response())
            if "store.steampowered.com/app/" in url:
                return _mock_response(200, text=_STORE_PAGE_HTML)
            return _mock_response(404)

        with patch("modules.scrapers.steam.requests.get", side_effect=side_effect):
            games = SteamScraper().fetch_free_games()

        assert len(games) == 1
        assert games[0].game_type == "dlc"

    def test_fetch_free_games_returns_game_when_appdetails_type_is_game(self, freeze_steam_now):
        """Full pipeline: appdetails type='game' produces a FreeGame with game_type='game'."""
        with patch("modules.scrapers.steam.requests.get", side_effect=_multi_url_mock()):
            games = SteamScraper().fetch_free_games()

        assert len(games) == 1
        assert games[0].game_type == "game"

    def test_fetch_free_games_defaults_to_game_when_type_absent(self, freeze_steam_now):
        """Full pipeline: missing 'type' in appdetails defaults to game_type='game'."""
        appid = "978520"

        def side_effect(url, **kwargs):
            if "search" in url:
                return _mock_response(200, text=_make_search_html())
            if "appdetails" in url:
                # Response without a 'type' field
                data = {appid: {"success": True, "data": {"short_description": "A game.", "header_image": "https://example.com/img.jpg"}}}
                return _mock_response(200, json_data=data)
            if "appreviews" in url:
                return _mock_response(200, json_data=_make_appreviews_response())
            if "store.steampowered.com/app/" in url:
                return _mock_response(200, text=_STORE_PAGE_HTML)
            return _mock_response(404)

        with patch("modules.scrapers.steam.requests.get", side_effect=side_effect):
            games = SteamScraper().fetch_free_games()

        assert len(games) == 1
        assert games[0].game_type == "game"

    def test_fetch_free_games_normalises_unknown_type_to_game(self, freeze_steam_now):
        """Unexpected 'type' values (e.g. 'music') are normalised to 'game'."""
        appid = "978520"

        def side_effect(url, **kwargs):
            if "search" in url:
                return _mock_response(200, text=_make_search_html())
            if "appdetails" in url:
                return _mock_response(200, json_data=_make_appdetails_response(appid, app_type="music"))
            if "appreviews" in url:
                return _mock_response(200, json_data=_make_appreviews_response())
            if "store.steampowered.com/app/" in url:
                return _mock_response(200, text=_STORE_PAGE_HTML)
            return _mock_response(404)

        with patch("modules.scrapers.steam.requests.get", side_effect=side_effect):
            games = SteamScraper().fetch_free_games()

        assert len(games) == 1
        assert games[0].game_type == "game"
