from unittest.mock import MagicMock, patch

import pytest
import requests as requests_lib

from modules import notifier
from modules.models import FreeGame

VALID_WEBHOOK = "https://discord.com/api/webhooks/123456789/token_abc"


# ---------------------------------------------------------------------------
# Tests for _get_safe_webhook_identifier
# ---------------------------------------------------------------------------

class TestGetLang:
    def test_returns_en_for_english_locale(self):
        assert notifier._get_lang("en_US.UTF-8") == "en"

    def test_returns_es_for_spanish_locale(self):
        assert notifier._get_lang("es_MX.UTF-8") == "es"

    def test_returns_es_for_spain_locale(self):
        assert notifier._get_lang("es_ES.UTF-8") == "es"

    def test_falls_back_to_en_for_unsupported_locale(self):
        assert notifier._get_lang("de_DE.UTF-8") == "en"

    def test_falls_back_to_en_for_empty_string(self):
        assert notifier._get_lang("") == "en"


class TestGetSafeWebhookIdentifier:
    def test_redacts_token_from_discord_url(self):
        result = notifier._get_safe_webhook_identifier(VALID_WEBHOOK)
        assert "token_abc" not in result
        assert "123456789" in result
        assert result == "discord.com/api/webhooks/123456789"

    def test_returns_unknown_for_empty_string(self):
        result = notifier._get_safe_webhook_identifier("")
        assert result == "unknown-webhook"

    def test_returns_unknown_for_none(self):
        result = notifier._get_safe_webhook_identifier(None)
        assert result == "unknown-webhook"

    def test_returns_host_for_non_discord_url(self):
        result = notifier._get_safe_webhook_identifier("https://example.com/hook")
        assert result == "example.com"

    def test_handles_url_without_standard_webhook_path(self):
        result = notifier._get_safe_webhook_identifier("https://myservice.com/api/notify")
        assert result == "myservice.com"


# ---------------------------------------------------------------------------
# Tests for send_discord_message
# ---------------------------------------------------------------------------

class TestSendDiscordMessage:
    def _make_response(self, status_code=204):
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_resp.text = ""
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    def test_raises_when_webhook_url_not_configured(self, sample_games):
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", None):
            with pytest.raises(ValueError, match="webhook URL not configured"):
                notifier.send_discord_message(sample_games)

    def test_sends_post_request_to_webhook(self, sample_games):
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier.requests.post") as mock_post:
            mock_post.return_value = self._make_response(204)
            notifier.send_discord_message(sample_games)

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == VALID_WEBHOOK
        assert "json" in kwargs

    def test_embed_contains_game_title(self, sample_games):
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier.requests.post") as mock_post:
            mock_post.return_value = self._make_response(204)
            notifier.send_discord_message(sample_games)

        _, kwargs = mock_post.call_args
        payload = kwargs["json"]
        assert payload["embeds"][0]["title"] == "Test Free Game"

    def test_embed_contains_game_link(self, sample_games):
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier.requests.post") as mock_post:
            mock_post.return_value = self._make_response(204)
            notifier.send_discord_message(sample_games)

        _, kwargs = mock_post.call_args
        payload = kwargs["json"]
        assert payload["embeds"][0]["url"] == sample_games[0].url

    def test_embed_contains_thumbnail(self, sample_games):
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier.requests.post") as mock_post:
            mock_post.return_value = self._make_response(204)
            notifier.send_discord_message(sample_games)

        _, kwargs = mock_post.call_args
        payload = kwargs["json"]
        assert payload["embeds"][0]["image"]["url"] == sample_games[0].image_url

    def test_embed_footer_contains_end_date_prefix(self, sample_games):
        en_t = notifier._TRANSLATIONS["en"]
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier._T", en_t), \
             patch("modules.notifier.requests.post") as mock_post:
            mock_post.return_value = self._make_response(204)
            notifier.send_discord_message(sample_games)

        _, kwargs = mock_post.call_args
        payload = kwargs["json"]
        assert payload["embeds"][0]["footer"]["text"].startswith("Ends on ")

    def test_embed_author_is_epic_games_store(self, sample_games):
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier.requests.post") as mock_post:
            mock_post.return_value = self._make_response(204)
            notifier.send_discord_message(sample_games)

        _, kwargs = mock_post.call_args
        payload = kwargs["json"]
        assert payload["embeds"][0]["author"]["name"] == "Epic Games Store"

    def test_embed_author_has_epic_store_icon(self, sample_games):
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier.requests.post") as mock_post:
            mock_post.return_value = self._make_response(204)
            notifier.send_discord_message(sample_games)

        _, kwargs = mock_post.call_args
        payload = kwargs["json"]
        assert "icon_url" in payload["embeds"][0]["author"]
        assert "icon-icons.com" in payload["embeds"][0]["author"]["icon_url"]
        assert "epic_games_icon" in payload["embeds"][0]["author"]["icon_url"]

    def test_embed_author_has_steam_store_icon(self):
        game = FreeGame(
            title="Steam Game",
            store="steam",
            url="https://store.steampowered.com/app/123/",
            image_url="https://example.com/img.jpg",
            original_price="$9.99",
            end_date="2024-01-31T15:00:00.000Z",
            is_permanent=False,
            description="",
        )
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier.requests.post") as mock_post:
            mock_post.return_value = self._make_response(204)
            notifier.send_discord_message([game])

        _, kwargs = mock_post.call_args
        payload = kwargs["json"]
        assert "icon_url" in payload["embeds"][0]["author"]
        assert "wikimedia.org" in payload["embeds"][0]["author"]["icon_url"]
        assert "Steam_icon_logo" in payload["embeds"][0]["author"]["icon_url"]

    def test_embed_includes_steam_user_review(self):
        game = FreeGame(
            title="Steam Game",
            store="steam",
            url="https://store.steampowered.com/app/123/",
            image_url="https://example.com/img.jpg",
            original_price="$9.99",
            end_date="2024-01-31T15:00:00.000Z",
            is_permanent=False,
            description="",
            review_scores=["Very Positive"],
        )
        en_t = notifier._TRANSLATIONS["en"]
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier._T", en_t), \
             patch("modules.notifier.requests.post") as mock_post:
            mock_post.return_value = self._make_response(204)
            notifier.send_discord_message([game])

        _, kwargs = mock_post.call_args
        description = kwargs["json"]["embeds"][0]["description"]
        assert "💬 Steam Reviews:" in description
        assert "Very Positive" in description
        assert "⭐" in description

    def test_review_label_is_translated_when_locale_is_spanish(self):
        game = FreeGame(
            title="Steam Game",
            store="steam",
            url="https://store.steampowered.com/app/123/",
            image_url="https://example.com/img.jpg",
            original_price="$9.99",
            end_date="2024-01-31T15:00:00.000Z",
            is_permanent=False,
            description="",
            review_scores=["Very Positive"],
        )
        es_t = notifier._TRANSLATIONS["es"]
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier._T", es_t), \
             patch("modules.notifier.requests.post") as mock_post:
            mock_post.return_value = self._make_response(204)
            notifier.send_discord_message([game])

        _, kwargs = mock_post.call_args
        description = kwargs["json"]["embeds"][0]["description"]
        assert "💬 Reseñas en Steam:" in description
        assert "Muy Positivo" in description
        assert "⭐" in description

    def test_embed_shows_metascore_with_metacritic_label(self):
        game = FreeGame(
            title="Epic Game",
            store="epic",
            url="https://store.epicgames.com/p/epic-game",
            image_url="https://example.com/img.jpg",
            original_price="$19.99",
            end_date="2024-01-31T15:00:00.000Z",
            is_permanent=False,
            description="",
            review_scores=["Metascore: 83"],
        )
        en_t = notifier._TRANSLATIONS["en"]
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier._T", en_t), \
             patch("modules.notifier.requests.post") as mock_post:
            mock_post.return_value = self._make_response(204)
            notifier.send_discord_message([game])

        _, kwargs = mock_post.call_args
        description = kwargs["json"]["embeds"][0]["description"]
        assert "📊 Metacritic:" in description
        assert "Metascore: 83" in description
        assert "⭐" in description
        assert "Steam Reviews" not in description

    def test_embed_shows_both_steam_and_metacritic_scores(self):
        """A Steam game with both sources renders both lines."""
        game = FreeGame(
            title="Steam Game",
            store="steam",
            url="https://store.steampowered.com/app/123/",
            image_url="https://example.com/img.jpg",
            original_price="$9.99",
            end_date="2024-01-31T15:00:00.000Z",
            is_permanent=False,
            description="",
            review_scores=["Very Positive", "Metascore: 83"],
        )
        en_t = notifier._TRANSLATIONS["en"]
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier._T", en_t), \
             patch("modules.notifier.requests.post") as mock_post:
            mock_post.return_value = self._make_response(204)
            notifier.send_discord_message([game])

        _, kwargs = mock_post.call_args
        description = kwargs["json"]["embeds"][0]["description"]
        assert "💬 Steam Reviews:" in description
        assert "Very Positive" in description
        assert "📊 Metacritic:" in description
        assert "Metascore: 83" in description

    def test_embed_no_review_section_when_review_scores_empty(self):
        """When review_scores is [], no review section is appended."""
        game = FreeGame(
            title="Steam Game",
            store="steam",
            url="https://store.steampowered.com/app/123/",
            image_url="https://example.com/img.jpg",
            original_price="$9.99",
            end_date="2024-01-31T15:00:00.000Z",
            is_permanent=False,
            description="A game.",
            review_scores=[],
        )
        en_t = notifier._TRANSLATIONS["en"]
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier._T", en_t), \
             patch("modules.notifier.requests.post") as mock_post:
            mock_post.return_value = self._make_response(204)
            notifier.send_discord_message([game])

        _, kwargs = mock_post.call_args
        description = kwargs["json"]["embeds"][0]["description"]
        assert "Steam Reviews" not in description
        assert "Metacritic" not in description
        assert "OpenCritic" not in description

    def test_footer_is_translated_when_locale_is_spanish(self, sample_games):
        es_t = notifier._TRANSLATIONS["es"]
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier._T", es_t), \
             patch("modules.notifier.requests.post") as mock_post:
            mock_post.return_value = self._make_response(204)
            notifier.send_discord_message(sample_games)

        _, kwargs = mock_post.call_args
        footer = kwargs["json"]["embeds"][0]["footer"]["text"]
        assert footer.startswith("Finaliza el ")

    def test_content_message_is_translated_when_locale_is_spanish(self, sample_games):
        es_t = notifier._TRANSLATIONS["es"]
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier._T", es_t), \
             patch("modules.notifier.requests.post") as mock_post:
            mock_post.return_value = self._make_response(204)
            notifier.send_discord_message(sample_games)

        _, kwargs = mock_post.call_args
        assert "¡Nuevo Juego Gratis" in kwargs["json"]["content"]

    def test_embed_includes_original_price_field_when_present(self):
        game = FreeGame(
            title="Epic Game",
            store="epic",
            url="https://store.epicgames.com/p/epic-game",
            image_url="https://example.com/img.jpg",
            original_price="$19.99",
            end_date="2024-01-31T15:00:00.000Z",
            is_permanent=False,
            description="",
        )
        en_t = notifier._TRANSLATIONS["en"]
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier._T", en_t), \
             patch("modules.notifier.requests.post") as mock_post:
            mock_post.return_value = self._make_response(204)
            notifier.send_discord_message([game])

        _, kwargs = mock_post.call_args
        fields = kwargs["json"]["embeds"][0].get("fields", [])
        assert any(f["name"] == "💰 Original Price" and f["value"] == "$19.99" for f in fields)

    def test_embed_original_price_field_translated_to_spanish(self):
        game = FreeGame(
            title="Epic Game",
            store="epic",
            url="https://store.epicgames.com/p/epic-game",
            image_url="https://example.com/img.jpg",
            original_price="$19.99",
            end_date="2024-01-31T15:00:00.000Z",
            is_permanent=False,
            description="",
        )
        es_t = notifier._TRANSLATIONS["es"]
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier._T", es_t), \
             patch("modules.notifier.requests.post") as mock_post:
            mock_post.return_value = self._make_response(204)
            notifier.send_discord_message([game])

        _, kwargs = mock_post.call_args
        fields = kwargs["json"]["embeds"][0].get("fields", [])
        assert any(f["name"] == "💰 Precio original" and f["value"] == "$19.99" for f in fields)

    def test_embed_no_original_price_field_when_absent(self, sample_games):
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier.requests.post") as mock_post:
            mock_post.return_value = self._make_response(204)
            notifier.send_discord_message(sample_games)

        _, kwargs = mock_post.call_args
        fields = kwargs["json"]["embeds"][0].get("fields", [])
        assert not any("Original Price" in f.get("name", "") for f in fields)

    def test_embed_no_review_score_when_absent(self, sample_games):
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier.requests.post") as mock_post:
            mock_post.return_value = self._make_response(204)
            notifier.send_discord_message(sample_games)

        _, kwargs = mock_post.call_args
        description = kwargs["json"]["embeds"][0]["description"]
        assert "Steam Reviews" not in description

    def test_content_message_uses_epic_store_name(self, sample_games):
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier.requests.post") as mock_post:
            mock_post.return_value = self._make_response(204)
            notifier.send_discord_message(sample_games)

        _, kwargs = mock_post.call_args
        assert "Epic Games Store" in kwargs["json"]["content"]

    def test_content_message_uses_steam_store_name(self):
        game = FreeGame(
            title="Steam Game",
            store="steam",
            url="https://store.steampowered.com/app/123/",
            image_url="https://example.com/img.jpg",
            original_price="$9.99",
            end_date="2024-01-31T15:00:00.000Z",
            is_permanent=False,
            description="",
        )
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier.requests.post") as mock_post:
            mock_post.return_value = self._make_response(204)
            notifier.send_discord_message([game])

        _, kwargs = mock_post.call_args
        assert "Steam" in kwargs["json"]["content"]

    def test_content_message_is_generic_for_multi_store_batch(self, sample_game):
        import dataclasses
        steam_game = dataclasses.replace(sample_game, store="steam", title="Steam Game")
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier.requests.post") as mock_post:
            mock_post.return_value = self._make_response(204)
            notifier.send_discord_message([sample_game, steam_game])

        _, kwargs = mock_post.call_args
        content = kwargs["json"]["content"]
        assert "Epic Games Store" not in content
        assert "Steam" not in content

    def test_embed_author_url_uses_epic_games_region(self, sample_games):
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier.EPIC_GAMES_REGION", "de-DE"), \
             patch("modules.notifier.requests.post") as mock_post:
            mock_post.return_value = self._make_response(204)
            notifier.send_discord_message(sample_games)

        _, kwargs = mock_post.call_args
        payload = kwargs["json"]
        assert payload["embeds"][0]["author"]["url"] == "https://store.epicgames.com/de-DE/free-games"

    def test_unknown_timezone_falls_back_to_utc(self, sample_games):
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier.TIMEZONE", "Invalid/Timezone"), \
             patch("modules.notifier.requests.post") as mock_post:
            mock_post.return_value = self._make_response(204)
            # Should not raise; falls back to UTC silently
            notifier.send_discord_message(sample_games)

        _, kwargs = mock_post.call_args
        payload = kwargs["json"]
        # Footer should still contain "UTC" when the timezone falls back
        assert "UTC" in payload["embeds"][0]["footer"]["text"]

    def test_embed_footer_contains_configured_timezone(self, sample_games):
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier.TIMEZONE", "Europe/London"), \
             patch("modules.notifier.requests.post") as mock_post:
            mock_post.return_value = self._make_response(204)
            notifier.send_discord_message(sample_games)

        _, kwargs = mock_post.call_args
        payload = kwargs["json"]
        assert "(Europe/London)" in payload["embeds"][0]["footer"]["text"]

    def test_embed_footer_respects_date_format(self, sample_games):
        custom_format = "%Y/%m/%d"
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier.DATE_FORMAT", custom_format), \
             patch("modules.notifier.requests.post") as mock_post:
            mock_post.return_value = self._make_response(204)
            notifier.send_discord_message(sample_games)

        _, kwargs = mock_post.call_args
        payload = kwargs["json"]
        footer_text = payload["embeds"][0]["footer"]["text"]
        # end_date is "2024-01-31T15:00:00.000Z"; with custom format the date portion is "2024/01/31"
        assert "2024/01/31" in footer_text

    def test_raises_on_http_error_status(self, sample_games):
        mock_resp = self._make_response(400)
        mock_resp.raise_for_status.side_effect = requests_lib.exceptions.HTTPError(
            "400 Bad Request"
        )
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier.requests.post", return_value=mock_resp):
            with pytest.raises(requests_lib.exceptions.HTTPError):
                notifier.send_discord_message(sample_games)

    def test_raises_on_timeout(self, sample_games):
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch(
                 "modules.notifier.requests.post",
                 side_effect=requests_lib.exceptions.Timeout(),
             ):
            with pytest.raises(requests_lib.exceptions.Timeout):
                notifier.send_discord_message(sample_games)

    def test_raises_on_connection_error(self, sample_games):
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch(
                 "modules.notifier.requests.post",
                 side_effect=requests_lib.exceptions.ConnectionError(),
             ):
            with pytest.raises(requests_lib.exceptions.ConnectionError):
                notifier.send_discord_message(sample_games)

    def test_sends_multiple_game_embeds(self, sample_game):
        import dataclasses
        game2 = dataclasses.replace(sample_game, title="Second Free Game")
        games = [sample_game, game2]

        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier.requests.post") as mock_post:
            mock_post.return_value = self._make_response(204)
            notifier.send_discord_message(games)

        _, kwargs = mock_post.call_args
        assert len(kwargs["json"]["embeds"]) == 2

    def test_raises_on_invalid_end_date(self):
        from modules.models import FreeGame
        bad_game = FreeGame(
            title="Incomplete Game",
            store="epic",
            url="https://store.epicgames.com/p/incomplete",
            image_url="",
            original_price=None,
            end_date="not-a-valid-date",
            is_permanent=False,
            description="",
        )
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK):
            with pytest.raises(ValueError):
                notifier.send_discord_message([bad_game])

    def test_embed_footer_unknown_end_date_when_empty_and_not_permanent(self):
        """Games with no end_date and is_permanent=False show a 'not available' message."""
        # dataclasses.replace with no replacements is a no-op; use FreeGame() directly.
        game = FreeGame(
            title="Steam Game",
            store="steam",
            url="https://store.steampowered.com/app/123/",
            image_url="https://example.com/img.jpg",
            original_price="$9.99",
            end_date="",
            is_permanent=False,
            description="",
        )
        es_t = notifier._TRANSLATIONS["es"]
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier._T", es_t), \
             patch("modules.notifier.requests.post") as mock_post:
            mock_post.return_value = self._make_response(204)
            notifier.send_discord_message([game])

        _, kwargs = mock_post.call_args
        footer = kwargs["json"]["embeds"][0]["footer"]["text"]
        assert footer == "Fecha de fin no disponible"

    def test_embed_footer_permanent_game(self):
        """Games with is_permanent=True show the permanent promotion message."""
        game = FreeGame(
            title="Free Forever Game",
            store="epic",
            url="https://store.epicgames.com/p/free-forever",
            image_url="https://example.com/img.jpg",
            original_price=None,
            end_date="",
            is_permanent=True,
            description="",
        )
        es_t = notifier._TRANSLATIONS["es"]
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier._T", es_t), \
             patch("modules.notifier.requests.post") as mock_post:
            mock_post.return_value = self._make_response(204)
            notifier.send_discord_message([game])

        _, kwargs = mock_post.call_args
        footer = kwargs["json"]["embeds"][0]["footer"]["text"]
        assert footer == "Gratis de forma permanente"


    def test_embed_shows_original_price_when_present(self):
        """When original_price is set, the embed includes a field with its value."""
        game = FreeGame(
            title="Priced Game",
            store="steam",
            url="https://store.steampowered.com/app/123/",
            image_url="https://example.com/img.jpg",
            original_price="$19.99",
            end_date="2024-01-31T15:00:00.000Z",
            is_permanent=False,
            description="A great game.",
        )
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier.requests.post") as mock_post:
            mock_post.return_value = self._make_response(204)
            notifier.send_discord_message([game])

        _, kwargs = mock_post.call_args
        fields = kwargs["json"]["embeds"][0].get("fields", [])
        assert any(f["value"] == "$19.99" for f in fields)
        assert any("Price" in f["name"] or "Precio" in f["name"] for f in fields)

    def test_embed_omits_original_price_when_none(self):
        """When original_price is None, no price field appears in the embed."""
        game = FreeGame(
            title="Free Forever",
            store="epic",
            url="https://store.epicgames.com/p/free",
            image_url="https://example.com/img.jpg",
            original_price=None,
            end_date="",
            is_permanent=True,
            description="",
        )
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier.requests.post") as mock_post:
            mock_post.return_value = self._make_response(204)
            notifier.send_discord_message([game])

        _, kwargs = mock_post.call_args
        fields = kwargs["json"]["embeds"][0].get("fields", [])
        assert not any("price" in f["name"].lower() or "precio" in f["name"].lower() for f in fields)

    def test_embed_shows_original_price_label_in_spanish(self):
        """When the locale is Spanish, the price field uses the Spanish label."""
        game = FreeGame(
            title="Juego con precio",
            store="epic",
            url="https://store.epicgames.com/p/juego",
            image_url="https://example.com/img.jpg",
            original_price="$14.99",
            end_date="2024-01-31T15:00:00.000Z",
            is_permanent=False,
            description="",
        )
        es_t = notifier._TRANSLATIONS["es"]
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier._T", es_t), \
             patch("modules.notifier.requests.post") as mock_post:
            mock_post.return_value = self._make_response(204)
            notifier.send_discord_message([game])

        _, kwargs = mock_post.call_args
        fields = kwargs["json"]["embeds"][0].get("fields", [])
        assert any(f["name"] == "💰 Precio original" for f in fields)


class TestSendDiscordMessageWebhookOverride:
    """Tests for the optional webhook_url override in send_discord_message."""

    def _make_response(self, status_code=204):
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_resp.text = ""
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    def test_override_url_is_used_instead_of_env_var(self, sample_games):
        """When webhook_url is provided, requests.post() uses it, not DISCORD_WEBHOOK_URL."""
        override_url = "https://discord.com/api/webhooks/9999/override-token"
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier.requests.post") as mock_post:
            mock_post.return_value = self._make_response(204)
            notifier.send_discord_message(sample_games, webhook_url=override_url)

        args, _ = mock_post.call_args
        assert args[0] == override_url
        assert args[0] != VALID_WEBHOOK

    def test_env_var_used_when_no_override(self, sample_games):
        """When webhook_url is not provided, requests.post() uses DISCORD_WEBHOOK_URL."""
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier.requests.post") as mock_post:
            mock_post.return_value = self._make_response(204)
            notifier.send_discord_message(sample_games)

        args, _ = mock_post.call_args
        assert args[0] == VALID_WEBHOOK

    def test_raises_on_non_discord_override_url(self, sample_games):
        """User-supplied webhook URLs pointing to non-Discord hosts are rejected."""
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK):
            with pytest.raises(ValueError, match="discord.com"):
                notifier.send_discord_message(
                    sample_games,
                    webhook_url="https://evil.com/api/webhooks/123/token",
                )

    def test_raises_on_non_https_override_url(self, sample_games):
        """User-supplied webhook URLs not using HTTPS are rejected."""
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK):
            with pytest.raises(ValueError, match="HTTPS"):
                notifier.send_discord_message(
                    sample_games,
                    webhook_url="http://discord.com/api/webhooks/123/token",
                )

    def test_raises_on_override_url_with_wrong_path(self, sample_games):
        """User-supplied webhook URLs without /api/webhooks/ path are rejected."""
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK):
            with pytest.raises(ValueError, match="/api/webhooks/"):
                notifier.send_discord_message(
                    sample_games,
                    webhook_url="https://discord.com/not/a/webhook",
                )

    def test_discordapp_com_host_is_allowed(self, sample_games):
        """discord.com and discordapp.com are both valid webhook hosts."""
        alt_host_url = "https://discordapp.com/api/webhooks/123/token"
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier.requests.post") as mock_post:
            mock_post.return_value = self._make_response(204)
            notifier.send_discord_message(sample_games, webhook_url=alt_host_url)

        args, _ = mock_post.call_args
        assert args[0] == alt_host_url


# ---------------------------------------------------------------------------
# DLC embed / content tests
# ---------------------------------------------------------------------------

class TestDlcEmbed:
    """Tests that DLC games produce the correct embed fields and content header."""

    def _make_response(self, status_code=204):
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_resp.text = ""
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    def _make_dlc_game(self, store="steam"):
        return FreeGame(
            title="Test DLC",
            store=store,
            url="https://store.steampowered.com/app/123/",
            image_url="https://example.com/img.jpg",
            original_price="$4.99",
            end_date="2024-01-31T15:00:00.000Z",
            is_permanent=False,
            description="A DLC for the base game.",
            game_type="dlc",
        )

    def test_embed_includes_dlc_badge_field_for_dlc_game(self):
        """A DLC game's embed must contain a field whose name matches the dlc_badge translation."""
        game = self._make_dlc_game()
        en_t = notifier._TRANSLATIONS["en"]
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier._T", en_t), \
             patch("modules.notifier.requests.post") as mock_post:
            mock_post.return_value = self._make_response(204)
            notifier.send_discord_message([game])

        _, kwargs = mock_post.call_args
        fields = kwargs["json"]["embeds"][0].get("fields", [])
        assert any(f["name"] == en_t["dlc_badge"] for f in fields)

    def test_embed_dlc_badge_field_absent_for_regular_game(self, sample_games):
        """A regular game's embed must NOT contain the DLC badge field."""
        en_t = notifier._TRANSLATIONS["en"]
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier._T", en_t), \
             patch("modules.notifier.requests.post") as mock_post:
            mock_post.return_value = self._make_response(204)
            notifier.send_discord_message(sample_games)

        _, kwargs = mock_post.call_args
        fields = kwargs["json"]["embeds"][0].get("fields", [])
        assert not any(f["name"] == en_t["dlc_badge"] for f in fields)

    def test_content_uses_new_free_dlc_when_all_dlcs(self):
        """When all games in the batch are DLCs, content uses the new_free_dlc template."""
        game = self._make_dlc_game(store="steam")
        en_t = notifier._TRANSLATIONS["en"]
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier._T", en_t), \
             patch("modules.notifier.requests.post") as mock_post:
            mock_post.return_value = self._make_response(204)
            notifier.send_discord_message([game])

        _, kwargs = mock_post.call_args
        content = kwargs["json"]["content"]
        assert "DLC" in content
        assert "Steam" in content

    def test_content_uses_new_free_game_when_mixed_with_games(self, sample_game):
        """When the batch mixes DLCs and games, the standard game header is used."""
        import dataclasses
        dlc_game = dataclasses.replace(sample_game, game_type="dlc", title="Some DLC")
        en_t = notifier._TRANSLATIONS["en"]
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier._T", en_t), \
             patch("modules.notifier.requests.post") as mock_post:
            mock_post.return_value = self._make_response(204)
            notifier.send_discord_message([sample_game, dlc_game])

        _, kwargs = mock_post.call_args
        content = kwargs["json"]["content"]
        # Generic multi-store header — no store name, no DLC label
        assert "DLC" not in content

    def test_content_dlc_header_translated_to_spanish(self):
        """When the locale is Spanish and all items are DLCs, the Spanish DLC template is used."""
        game = self._make_dlc_game(store="steam")
        es_t = notifier._TRANSLATIONS["es"]
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier._T", es_t), \
             patch("modules.notifier.requests.post") as mock_post:
            mock_post.return_value = self._make_response(204)
            notifier.send_discord_message([game])

        _, kwargs = mock_post.call_args
        content = kwargs["json"]["content"]
        assert "DLC" in content
        assert "Steam" in content
        assert "Gratis" in content
