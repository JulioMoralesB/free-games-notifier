from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api import _metrics, app, increment_metric


@pytest.fixture(autouse=True)
def _reset_metrics():
    """Reset metrics counters before each test."""
    original = dict(_metrics)
    for key in _metrics:
        _metrics[key] = 0
    yield
    _metrics.update(original)


@pytest.fixture
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    def test_returns_healthy_when_api_reachable(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("api.routes.system.requests.get", return_value=mock_resp), \
             patch("api.routes.system.DB_HOST", None):
            resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["epic_games_api"] == "healthy"
        assert data["database"] == "not_configured"
        assert data["status"] == "healthy"

    def test_returns_unhealthy_when_api_unreachable(self, client):
        with patch("api.routes.system.requests.get", side_effect=Exception("timeout")), \
             patch("api.routes.system.DB_HOST", None):
            resp = client.get("/health")
        data = resp.json()
        assert data["epic_games_api"] == "unhealthy"
        assert data["status"] == "unhealthy"

    def test_returns_unhealthy_on_non_200_status(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        with patch("api.routes.system.requests.get", return_value=mock_resp), \
             patch("api.routes.system.DB_HOST", None):
            resp = client.get("/health")
        data = resp.json()
        assert data["epic_games_api"] == "unhealthy"

    def test_checks_database_when_configured(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_conn = MagicMock()
        with patch("api.routes.system.requests.get", return_value=mock_resp), \
             patch("api.routes.system.DB_HOST", "localhost"), \
             patch("api.routes.system.DB_PORT", 5432), \
             patch("api.routes.system.DB_NAME", "test"), \
             patch("api.routes.system.DB_USER", "user"), \
             patch("psycopg2.connect", return_value=mock_conn):
            resp = client.get("/health")
        data = resp.json()
        assert data["database"] == "healthy"
        mock_conn.close.assert_called_once()

    def test_database_unhealthy_on_connection_error(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("api.routes.system.requests.get", return_value=mock_resp), \
             patch("api.routes.system.DB_HOST", "localhost"), \
             patch("api.routes.system.DB_PORT", 5432), \
             patch("api.routes.system.DB_NAME", "test"), \
             patch("api.routes.system.DB_USER", "user"), \
             patch("psycopg2.connect", side_effect=Exception("connection refused")):
            resp = client.get("/health")
        data = resp.json()
        assert data["database"] == "unhealthy"
        assert data["status"] == "unhealthy"


# ---------------------------------------------------------------------------
# GET /games/latest
# ---------------------------------------------------------------------------

class TestGamesLatestEndpoint:
    def test_returns_games(self, client, sample_games):
        with patch("api.routes.games.load_previous_games", return_value=sample_games):
            resp = client.get("/games/latest")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["games"][0]["title"] == "Test Free Game"

    def test_returns_empty_list_when_no_games(self, client):
        with patch("api.routes.games.load_previous_games", return_value=[]):
            resp = client.get("/games/latest")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0
        assert data["games"] == []

    def test_returns_500_on_error(self, client):
        with patch("api.routes.games.load_previous_games", side_effect=Exception("disk error")):
            resp = client.get("/games/latest")
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /games/history
# ---------------------------------------------------------------------------

class TestGamesHistoryEndpoint:
    def test_returns_paginated_results(self, client, sample_game):
        import dataclasses
        games = [dataclasses.replace(sample_game, title=f"Game {i}") for i in range(5)]
        with patch("api.routes.games.load_previous_games", return_value=games):
            resp = client.get("/games/history?limit=2&offset=1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert data["limit"] == 2
        assert data["offset"] == 1
        assert len(data["games"]) == 2
        assert data["games"][0]["title"] == "Game 1"

    def test_default_pagination(self, client, sample_games):
        with patch("api.routes.games.load_previous_games", return_value=sample_games):
            resp = client.get("/games/history")
        data = resp.json()
        assert data["limit"] == 20
        assert data["offset"] == 0

    def test_rejects_invalid_limit(self, client):
        resp = client.get("/games/history?limit=0")
        assert resp.status_code == 422

    def test_rejects_negative_offset(self, client):
        resp = client.get("/games/history?offset=-1")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /notify/discord/resend
# ---------------------------------------------------------------------------

class TestNotifyDiscordResendEndpoint:
    def test_resends_notification_successfully(self, client, sample_games):
        with patch("api.routes.notifications.load_last_notification", return_value=sample_games), \
             patch("api.routes.notifications.send_discord_message") as mock_send:
            resp = client.post("/notify/discord/resend")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["games_sent"] == 1
        mock_send.assert_called_once_with(sample_games, webhook_url=None)

    def test_returns_404_when_no_games(self, client):
        with patch("api.routes.notifications.load_last_notification", return_value=[]):
            resp = client.post("/notify/discord/resend")
        assert resp.status_code == 404

    def test_returns_500_on_discord_error(self, client, sample_games):
        with patch("api.routes.notifications.load_last_notification", return_value=sample_games), \
             patch("api.routes.notifications.send_discord_message", side_effect=Exception("webhook error")):
            resp = client.post("/notify/discord/resend")
        assert resp.status_code == 500

    def test_rejects_invalid_api_key(self, client, sample_games):
        with patch("api.auth.API_KEY", "valid-key"):
            resp = client.post("/notify/discord/resend", headers={"X-API-Key": "wrong-key"})
        assert resp.status_code == 401

    def test_accepts_valid_api_key(self, client, sample_games):
        with patch("api.auth.API_KEY", "valid-key"), \
             patch("api.routes.notifications.load_last_notification", return_value=sample_games), \
             patch("api.routes.notifications.send_discord_message"):
            resp = client.post("/notify/discord/resend", headers={"X-API-Key": "valid-key"})
        assert resp.status_code == 200

    def test_uses_custom_webhook_url_when_provided(self, client, sample_games):
        custom_url = "https://discord.com/api/webhooks/9999/custom-token"
        with patch("api.routes.notifications.load_last_notification", return_value=sample_games), \
             patch("api.routes.notifications.send_discord_message") as mock_send:
            resp = client.post("/notify/discord/resend", json={"webhook_url": custom_url})
        assert resp.status_code == 200
        mock_send.assert_called_once_with(sample_games, webhook_url=custom_url)

    def test_rejects_invalid_webhook_url(self, client, sample_games):
        with patch("api.routes.notifications.load_last_notification", return_value=sample_games):
            resp = client.post("/notify/discord/resend", json={"webhook_url": "https://evil.com/hook"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /metrics
# ---------------------------------------------------------------------------

class TestMetricsEndpoint:
    def test_returns_metrics(self, client):
        resp = client.get("/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert "uptime_seconds" in data
        assert "games_processed" in data
        assert "discord_notifications_sent" in data
        assert "errors" in data

    def test_uptime_is_positive(self, client):
        resp = client.get("/metrics")
        data = resp.json()
        assert data["uptime_seconds"] >= 0


# ---------------------------------------------------------------------------
# GET /config
# ---------------------------------------------------------------------------

class TestConfigEndpoint:
    def test_returns_config(self, client):
        with patch("api.auth.API_KEY", None):
            resp = client.get("/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "epic_games_api_url" in data
        assert "timezone" in data
        assert "schedule_time" in data

    def test_does_not_expose_secrets(self, client):
        with patch("api.auth.API_KEY", None):
            resp = client.get("/config")
        data = resp.json()
        data_str = str(data)
        assert "DB_PASSWORD" not in data_str
        assert "DISCORD_WEBHOOK_URL" not in data_str
        assert "API_KEY" not in data_str
        # Ensure the actual secret values are not keys
        assert "password" not in data
        assert "webhook" not in data
        assert "api_key" not in data

    def test_requires_api_key_when_set(self, client):
        with patch("api.auth.API_KEY", "secret-key"):
            resp = client.get("/config")
        assert resp.status_code == 401

    def test_accepts_valid_api_key(self, client):
        with patch("api.auth.API_KEY", "secret-key"):
            resp = client.get("/config", headers={"X-API-Key": "secret-key"})
        assert resp.status_code == 200

    def test_rejects_invalid_api_key(self, client):
        with patch("api.auth.API_KEY", "secret-key"):
            resp = client.get("/config", headers={"X-API-Key": "wrong-key"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /check (E2E test endpoint)
# ---------------------------------------------------------------------------

class TestCheckE2EEndpoint:
    @pytest.fixture(autouse=True)
    def epic_only_stores(self):
        with patch("api.routes.checks.ENABLED_STORES", ["epic"]):
            yield

    def test_full_flow_new_games(self, client, sample_games):
        with patch("modules.scrapers.epic.EpicGamesScraper.fetch_free_games", return_value=sample_games), \
             patch("api.routes.checks.load_previous_games", return_value=[]), \
             patch("api.routes.checks.send_discord_message"):
            resp = client.post("/check")
        assert resp.status_code == 200
        data = resp.json()
        assert data["games_fetched"] == 1
        assert data["notification_status"] == "sent"
        assert len(data["new_games"]) == 1
        assert len(data["already_in_storage"]) == 0

    def test_full_flow_games_already_saved(self, client, sample_games):
        with patch("modules.scrapers.epic.EpicGamesScraper.fetch_free_games", return_value=sample_games), \
             patch("api.routes.checks.load_previous_games", return_value=sample_games), \
             patch("api.routes.checks.send_discord_message"):
            resp = client.post("/check")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["already_in_storage"]) == 1
        assert len(data["new_games"]) == 0
        assert data["notification_status"] == "sent"

    def test_returns_404_when_no_free_games(self, client):
        with patch("modules.scrapers.epic.EpicGamesScraper.fetch_free_games", return_value=[]):
            resp = client.post("/check")
        assert resp.status_code == 404

    def test_handles_discord_failure(self, client, sample_games):
        with patch("modules.scrapers.epic.EpicGamesScraper.fetch_free_games", return_value=sample_games), \
             patch("api.routes.checks.load_previous_games", return_value=[]), \
             patch("api.routes.checks.send_discord_message", side_effect=Exception("webhook error")):
            resp = client.post("/check")
        assert resp.status_code == 200
        data = resp.json()
        assert "failed" in data["notification_status"]

    def test_returns_500_on_scraper_error(self, client):
        with patch("modules.scrapers.epic.EpicGamesScraper.fetch_free_games", side_effect=Exception("API error")):
            resp = client.post("/check")
        assert resp.status_code == 500

    def test_rejects_invalid_api_key(self, client):
        with patch("api.auth.API_KEY", "valid-key"):
            resp = client.post("/check", headers={"X-API-Key": "wrong-key"})
        assert resp.status_code == 401

    def test_uses_custom_webhook_url_when_provided(self, client, sample_games):
        custom_url = "https://discord.com/api/webhooks/9999/custom-token"
        with patch("modules.scrapers.epic.EpicGamesScraper.fetch_free_games", return_value=sample_games), \
             patch("api.routes.checks.load_previous_games", return_value=[]), \
             patch("api.routes.checks.send_discord_message") as mock_send:
            resp = client.post("/check", json={"webhook_url": custom_url})
        assert resp.status_code == 200
        mock_send.assert_called_once_with(sample_games, webhook_url=custom_url)

    def test_rejects_invalid_webhook_url(self, client, sample_games):
        with patch("modules.scrapers.epic.EpicGamesScraper.fetch_free_games", return_value=sample_games):
            resp = client.post("/check", json={"webhook_url": "https://evil.com/hook"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# API Key authentication
# ---------------------------------------------------------------------------

class TestAPIKeyAuth:
    def test_no_auth_required_when_api_key_not_set(self, client, sample_games):
        with patch("api.auth.API_KEY", None), \
             patch("api.routes.notifications.load_last_notification", return_value=sample_games), \
             patch("api.routes.notifications.send_discord_message"):
            resp = client.post("/notify/discord/resend")
        assert resp.status_code == 200

    def test_auth_required_when_api_key_set(self, client):
        with patch("api.auth.API_KEY", "secret-key"):
            resp = client.post("/notify/discord/resend")
        assert resp.status_code == 401

    def test_valid_key_allows_access(self, client, sample_games):
        with patch("api.auth.API_KEY", "secret-key"), \
             patch("api.routes.notifications.load_last_notification", return_value=sample_games), \
             patch("api.routes.notifications.send_discord_message"):
            resp = client.post(
                "/notify/discord/resend",
                headers={"X-API-Key": "secret-key"},
            )
        assert resp.status_code == 200

    def test_read_endpoints_do_not_require_auth(self, client):
        with patch("api.auth.API_KEY", "secret-key"):
            # GET endpoints without auth protection should work without API key
            with patch("api.routes.games.load_previous_games", return_value=[]):
                assert client.get("/games/latest").status_code == 200
            assert client.get("/metrics").status_code == 200


# ---------------------------------------------------------------------------
# increment_metric helper
# ---------------------------------------------------------------------------

class TestIncrementMetric:
    def test_increments_existing_key(self):
        _metrics["errors"] = 0
        increment_metric("errors")
        assert _metrics["errors"] == 1

    def test_ignores_unknown_key(self):
        increment_metric("nonexistent_key")
        # Should not raise

    def test_increments_by_custom_amount(self):
        _metrics["games_processed"] = 0
        increment_metric("games_processed", 5)
        assert _metrics["games_processed"] == 5
