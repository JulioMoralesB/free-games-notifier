from unittest.mock import MagicMock, patch

import pytest

from config import EPIC_GAMES_REGION
from modules.models import FreeGame
from modules.scrapers.epic import EpicGamesScraper
from modules.scrapers.review_sources import fetch_metacritic_score, make_metacritic_slug

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_element(
    title="Test Game",
    discount_price=0,
    offer_slug=None,
    catalog_slug=None,
    product_slug=None,
    has_promotions=True,
    end_date="2024-01-31T15:00:00.000Z",
    thumbnail_type="Thumbnail",
    thumbnail_url="https://example.com/img.jpg",
    description="A game description",
):
    """Build a minimal Epic Games API element dict for testing."""
    element = {
        "title": title,
        "description": description,
        "price": {
            "totalPrice": {
                "discountPrice": discount_price,
                "originalPrice": 1999,
                "fmtPrice": {
                    "originalPrice": "$19.99",
                    "discountPrice": "$0.00",
                },
            }
        },
        "offerMappings": [{"pageSlug": offer_slug}] if offer_slug else [],
        "catalogNs": {
            "mappings": [{"pageSlug": catalog_slug}] if catalog_slug else []
        },
        "promotions": (
            {
                "promotionalOffers": [
                    {
                        "promotionalOffers": [
                            {
                                "discountSetting": {"discountPercentage": 0},
                                "endDate": end_date,
                            }
                        ]
                    }
                ]
            }
            if has_promotions
            else {"promotionalOffers": []}
        ),
        "keyImages": [{"type": thumbnail_type, "url": thumbnail_url}],
    }
    if product_slug is not None:
        element["productSlug"] = product_slug
    return element


def _make_api_response(elements):
    return {
        "data": {
            "Catalog": {
                "searchStore": {
                    "elements": elements
                }
            }
        }
    }


def _mock_response(status_code=200, json_data=None):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data or {}
    return mock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFetchFreeGames:
    @pytest.fixture(autouse=True)
    def no_review_sources(self):
        """Suppress external Metacritic requests in tests that don't need them."""
        with patch("modules.scrapers.epic.fetch_metacritic_score", return_value=None):
            yield

    def test_returns_free_game(self, epic_api_response):
        with patch("modules.scrapers.epic.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, epic_api_response)
            scraper = EpicGamesScraper()
            games = scraper.fetch_free_games()

        assert len(games) == 1
        assert games[0].title == "Test Free Game"
        assert games[0].url == f"https://store.epicgames.com/{EPIC_GAMES_REGION}/p/test-free-game"
        assert games[0].end_date == "2024-01-31T15:00:00.000Z"
        assert games[0].description == "A free game for testing"
        assert games[0].image_url == "https://example.com/thumbnail.jpg"
        assert games[0].original_price == "$19.99"

    def test_excludes_paid_games(self):
        paid = _make_element(discount_price=1999)
        with patch("modules.scrapers.epic.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, _make_api_response([paid]))
            scraper = EpicGamesScraper()
            games = scraper.fetch_free_games()

        assert games == []

    def test_skips_mystery_games(self):
        mystery = _make_element(title="Mystery Game", discount_price=0)
        with patch("modules.scrapers.epic.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, _make_api_response([mystery]))
            scraper = EpicGamesScraper()
            games = scraper.fetch_free_games()

        assert games == []

    def test_returns_empty_on_api_error(self):
        with patch("modules.scrapers.epic.requests.get") as mock_get:
            mock_get.return_value = _mock_response(500)
            scraper = EpicGamesScraper()
            games = scraper.fetch_free_games()

        assert games == []

    def test_uses_offer_slug_for_link(self):
        element = _make_element(discount_price=0, offer_slug="offer-slug-123")
        with patch("modules.scrapers.epic.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, _make_api_response([element]))
            scraper = EpicGamesScraper()
            games = scraper.fetch_free_games()

        assert "offer-slug-123" in games[0].url

    def test_falls_back_to_catalog_slug(self):
        element = _make_element(
            discount_price=0,
            offer_slug=None,
            catalog_slug="catalog-slug-456",
        )
        with patch("modules.scrapers.epic.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, _make_api_response([element]))
            scraper = EpicGamesScraper()
            games = scraper.fetch_free_games()

        assert "catalog-slug-456" in games[0].url

    def test_falls_back_to_product_slug(self):
        element = _make_element(
            discount_price=0,
            offer_slug=None,
            catalog_slug=None,
            product_slug="product-slug-789",
        )
        with patch("modules.scrapers.epic.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, _make_api_response([element]))
            scraper = EpicGamesScraper()
            games = scraper.fetch_free_games()

        assert "product-slug-789" in games[0].url

    def test_uses_default_link_when_no_slug(self):
        element = _make_element(
            discount_price=0,
            offer_slug=None,
            catalog_slug=None,
        )
        element.pop("productSlug", None)
        with patch("modules.scrapers.epic.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, _make_api_response([element]))
            scraper = EpicGamesScraper()
            games = scraper.fetch_free_games()

        expected_link = f"https://store.epicgames.com/{EPIC_GAMES_REGION}/free-games"
        assert games[0].url == expected_link

    def test_skips_game_with_no_promotional_offers(self):
        element = _make_element(discount_price=0, has_promotions=False)
        with patch("modules.scrapers.epic.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, _make_api_response([element]))
            scraper = EpicGamesScraper()
            games = scraper.fetch_free_games()

        assert games == []

    def test_uses_first_image_when_no_thumbnail(self):
        element = _make_element(
            discount_price=0,
            thumbnail_type="OfferImageWide",
            thumbnail_url="https://example.com/wide.jpg",
        )
        with patch("modules.scrapers.epic.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, _make_api_response([element]))
            scraper = EpicGamesScraper()
            games = scraper.fetch_free_games()

        assert games[0].image_url == "https://example.com/wide.jpg"

    def test_returns_empty_when_no_elements(self):
        with patch("modules.scrapers.epic.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, _make_api_response([]))
            scraper = EpicGamesScraper()
            games = scraper.fetch_free_games()

        assert games == []

    def test_original_price_populated_from_fmt_price(self):
        element = _make_element(discount_price=0, offer_slug="game-one")
        with patch("modules.scrapers.epic.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, _make_api_response([element]))
            games = EpicGamesScraper().fetch_free_games()

        assert games[0].original_price == "$19.99"

    def test_original_price_is_none_when_int_price_is_zero(self):
        element = _make_element(discount_price=0, offer_slug="always-free")
        element["price"]["totalPrice"]["originalPrice"] = 0
        element["price"]["totalPrice"]["fmtPrice"]["originalPrice"] = "0"
        with patch("modules.scrapers.epic.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, _make_api_response([element]))
            games = EpicGamesScraper().fetch_free_games()

        assert games[0].original_price is None

    def test_original_price_is_none_when_fmt_price_missing(self):
        element = _make_element(discount_price=0, offer_slug="game-one")
        del element["price"]["totalPrice"]["fmtPrice"]
        with patch("modules.scrapers.epic.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, _make_api_response([element]))
            games = EpicGamesScraper().fetch_free_games()

        assert games[0].original_price is None

    def test_multiple_free_games_returned(self):
        elements = [
            _make_element(title="Game One", discount_price=0, offer_slug="game-one"),
            _make_element(title="Game Two", discount_price=0, offer_slug="game-two"),
        ]
        with patch("modules.scrapers.epic.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, _make_api_response(elements))
            scraper = EpicGamesScraper()
            games = scraper.fetch_free_games()

        assert len(games) == 2
        titles = [g.title for g in games]
        assert "Game One" in titles
        assert "Game Two" in titles


# ---------------------------------------------------------------------------
# FreeGame model tests
# ---------------------------------------------------------------------------

class TestFreeGameModel:
    """Unit tests for the FreeGame dataclass and its from_dict factory."""

    @pytest.fixture(autouse=True)
    def no_review_sources(self):
        """Suppress external Metacritic requests in tests that don't need them."""
        with patch("modules.scrapers.epic.fetch_metacritic_score", return_value=None):
            yield

    def _base_dict(self, **overrides):
        data = {
            "title": "Sample Game",
            "store": "epic",
            "url": "https://store.epicgames.com/p/sample",
            "image_url": "https://example.com/img.jpg",
            "original_price": "$9.99",
            "end_date": "2024-01-31T15:00:00.000Z",
            "is_permanent": False,
            "description": "A game.",
        }
        data.update(overrides)
        return data

    def test_game_type_defaults_to_game(self):
        """FreeGame.game_type defaults to 'game' when not specified."""
        g = FreeGame(
            title="X",
            store="epic",
            url="https://store.epicgames.com/p/x",
            image_url="",
            original_price=None,
            end_date="",
            is_permanent=False,
            description="",
        )
        assert g.game_type == "game"

    def test_review_scores_defaults_to_empty_list(self):
        """FreeGame.review_scores defaults to [] when not specified."""
        g = FreeGame(
            title="X",
            store="epic",
            url="https://store.epicgames.com/p/x",
            image_url="",
            original_price=None,
            end_date="",
            is_permanent=False,
            description="",
        )
        assert g.review_scores == []

    def test_review_scores_can_hold_multiple_sources(self):
        """FreeGame.review_scores accepts a list of score strings from multiple sources."""
        g = FreeGame(
            title="X",
            store="steam",
            url="https://store.steampowered.com/app/1/",
            image_url="",
            original_price=None,
            end_date="",
            is_permanent=False,
            description="",
            review_scores=["Very Positive", "Metascore: 83", "OpenCritic: 78"],
        )
        assert g.review_scores == ["Very Positive", "Metascore: 83", "OpenCritic: 78"]

    def test_game_type_can_be_set_to_dlc(self):
        """FreeGame.game_type can be explicitly set to 'dlc'."""
        g = FreeGame(
            title="X DLC",
            store="steam",
            url="https://store.steampowered.com/app/1/",
            image_url="",
            original_price=None,
            end_date="",
            is_permanent=False,
            description="",
            game_type="dlc",
        )
        assert g.game_type == "dlc"

    def test_from_dict_reads_review_scores_list(self):
        """from_dict reads a review_scores list directly."""
        data = self._base_dict(review_scores=["Very Positive", "Metascore: 83"])
        g = FreeGame.from_dict(data)
        assert g.review_scores == ["Very Positive", "Metascore: 83"]

    def test_from_dict_migrates_legacy_review_score_string(self):
        """from_dict wraps a legacy review_score string in a list."""
        data = self._base_dict(review_score="Very Positive")
        g = FreeGame.from_dict(data)
        assert g.review_scores == ["Very Positive"]

    def test_from_dict_defaults_review_scores_to_empty_list_when_absent(self):
        """from_dict returns [] when neither review_scores nor review_score is set."""
        data = self._base_dict()  # no review fields
        g = FreeGame.from_dict(data)
        assert g.review_scores == []

    def test_from_dict_preserves_game_type_game(self):
        """from_dict reads game_type='game' from the dict."""
        data = self._base_dict(game_type="game")
        g = FreeGame.from_dict(data)
        assert g.game_type == "game"

    def test_from_dict_preserves_game_type_dlc(self):
        """from_dict reads game_type='dlc' from the dict."""
        data = self._base_dict(game_type="dlc")
        g = FreeGame.from_dict(data)
        assert g.game_type == "dlc"

    def test_from_dict_defaults_game_type_to_game_when_absent(self):
        """from_dict falls back to 'game' when game_type key is missing."""
        data = self._base_dict()  # no game_type key
        g = FreeGame.from_dict(data)
        assert g.game_type == "game"

    def test_epic_scraper_returns_game_type_game(self):
        """EpicGamesScraper always sets game_type='game' on returned FreeGame objects."""
        element = _make_element(discount_price=0, offer_slug="test")
        with patch("modules.scrapers.epic.requests.get") as mock_get:
            mock_get.return_value = _mock_response(200, _make_api_response([element]))
            games = EpicGamesScraper().fetch_free_games()

        assert len(games) == 1
        assert games[0].game_type == "game"


# ---------------------------------------------------------------------------
# Metacritic review score tests
# ---------------------------------------------------------------------------

def _mc_html(score: int) -> str:
    """Build a minimal Metacritic page that contains a JSON-LD block with *score*."""
    return (
        "<html><body>"
        '<script type="application/ld+json">'
        '{"@type":"VideoGame","aggregateRating":{"@type":"AggregateRating",'
        f'"name":"Metascore","ratingValue":{score},"bestRating":100,"worstRating":0}}}}'
        "</script></body></html>"
    )


def _mc_resp(status_code=200, score=83):
    """Return a mock requests.Response for a Metacritic page."""
    mock = MagicMock()
    mock.status_code = status_code
    mock.text = _mc_html(score) if status_code == 200 else ""
    return mock


class TestMetacriticReviewScore:
    """Unit tests for fetch_metacritic_score."""

    def test_returns_metascore_string(self):
        with patch("modules.scrapers.review_sources.requests.get", return_value=_mc_resp(score=83)):
            result = fetch_metacritic_score("Celeste")
        assert result == "Metascore: 83"

    def test_returns_none_on_404(self):
        with patch("modules.scrapers.review_sources.requests.get", return_value=_mc_resp(status_code=404)):
            result = fetch_metacritic_score("Unknown Game XYZ")
        assert result is None

    def test_returns_none_when_no_json_ld(self):
        mock = MagicMock()
        mock.status_code = 200
        mock.text = "<html><body><p>No structured data here.</p></body></html>"
        with patch("modules.scrapers.review_sources.requests.get", return_value=mock):
            result = fetch_metacritic_score("Some Game")
        assert result is None

    def test_returns_none_when_aggregate_rating_absent(self):
        mock = MagicMock()
        mock.status_code = 200
        mock.text = (
            '<html><body><script type="application/ld+json">'
            '{"@type":"VideoGame","name":"Some Game"}'
            "</script></body></html>"
        )
        with patch("modules.scrapers.review_sources.requests.get", return_value=mock):
            result = fetch_metacritic_score("Some Game")
        assert result is None

    def test_returns_none_on_network_exception(self):
        import requests as req
        with patch(
            "modules.scrapers.review_sources.requests.get",
            side_effect=req.exceptions.ConnectionError(),
        ):
            result = fetch_metacritic_score("Celeste")
        assert result is None

    def test_full_pipeline_sets_review_scores_from_metacritic(self):
        """fetch_free_games propagates the Metascore into review_scores."""
        element = _make_element(discount_price=0, offer_slug="celeste", title="Celeste")
        api_resp = _mock_response(200, _make_api_response([element]))

        with patch("modules.scrapers.epic.fetch_metacritic_score", return_value="Metascore: 94"), \
             patch("modules.scrapers.epic.requests.get", return_value=api_resp):
            games = EpicGamesScraper().fetch_free_games()

        assert len(games) == 1
        assert "Metascore: 94" in games[0].review_scores

    def test_full_pipeline_review_scores_empty_when_metacritic_unavailable(self):
        """fetch_free_games leaves review_scores=[] when Metacritic returns nothing."""
        element = _make_element(discount_price=0, offer_slug="obscure-game", title="Obscure Game")
        api_resp = _mock_response(200, _make_api_response([element]))

        with patch("modules.scrapers.epic.fetch_metacritic_score", return_value=None), \
             patch("modules.scrapers.epic.requests.get", return_value=api_resp):
            games = EpicGamesScraper().fetch_free_games()

        assert len(games) == 1
        assert games[0].review_scores == []

    def test_full_pipeline_review_score_is_only_metascore_when_available(self):
        """fetch_free_games includes only Metacritic when it responds."""
        element = _make_element(discount_price=0, offer_slug="celeste", title="Celeste")
        api_resp = _mock_response(200, _make_api_response([element]))

        with patch("modules.scrapers.epic.fetch_metacritic_score", return_value="Metascore: 94"), \
             patch("modules.scrapers.epic.requests.get", return_value=api_resp):
            games = EpicGamesScraper().fetch_free_games()

        assert len(games) == 1
        assert games[0].review_scores == ["Metascore: 94"]


# ---------------------------------------------------------------------------
# make_metacritic_slug helper tests
# ---------------------------------------------------------------------------

class TestMakeMetacriticSlug:
    """Unit tests for the make_metacritic_slug helper."""

    def test_lowercases(self):
        assert make_metacritic_slug("Celeste") == "celeste"

    def test_replaces_spaces_with_hyphens(self):
        assert make_metacritic_slug("A Short Hike") == "a-short-hike"

    def test_strips_punctuation(self):
        assert make_metacritic_slug("Baldur's Gate 3") == "baldurs-gate-3"

    def test_handles_colon(self):
        assert make_metacritic_slug("The Witcher 3: Wild Hunt") == "the-witcher-3-wild-hunt"

    def test_strips_accents(self):
        assert make_metacritic_slug("Café Owner Simulator") == "cafe-owner-simulator"

    def test_collapses_consecutive_hyphens(self):
        # A title with multiple punctuation chars next to each other
        assert make_metacritic_slug("Game -- Title") == "game-title"
