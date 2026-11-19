"""Tests for the fire-and-forget summary mirror push (modules/summary.py).

The push must never be able to fail a check, the heartbeat, or the process:
the heartbeat push once crashed the whole service for exactly this reason.
"""

import logging
import sys
from unittest.mock import MagicMock, patch

import pytest
import requests

from modules import summary
from modules.models import FreeGame

MIRROR_URL = "https://mirror.example.com/api/summary/snapshot?sig=path-secret"
MIRROR_TOKEN = "faketesttoken-not-a-real-secret"
FUTURE = "2099-01-01T00:00:00.000Z"


def _game(title, end_date=FUTURE, store="epic"):
    return FreeGame(
        title=title,
        store=store,
        url=f"https://store.epicgames.com/p/{title.lower()}",
        image_url="https://example.com/thumb.jpg",
        original_price=None,
        end_date=end_date,
        is_permanent=False,
        description="",
    )


@pytest.fixture
def configured():
    """Enable the mirror with fake values and a stubbed storage read."""
    with patch.object(summary, "SUMMARY_MIRROR_URL", MIRROR_URL), \
         patch.object(summary, "SUMMARY_MIRROR_TOKEN", MIRROR_TOKEN), \
         patch.object(summary, "SUMMARY_MIRROR_TIMEOUT", 5.0), \
         patch("modules.storage.load_previous_games", return_value=[_game("Celeste")]), \
         patch.object(summary, "get_last_check_completed_at", return_value=1893456000.0):
        yield


def _assert_no_secrets_logged(caplog):
    text = caplog.text
    assert MIRROR_TOKEN not in text
    assert "path-secret" not in text
    assert "/api/summary/snapshot" not in text


class TestDisabled:
    @pytest.mark.parametrize("url,token", [(None, MIRROR_TOKEN), (MIRROR_URL, None), (None, None)])
    def test_no_request_unless_url_and_token_are_both_set(self, url, token):
        with patch.object(summary, "SUMMARY_MIRROR_URL", url), \
             patch.object(summary, "SUMMARY_MIRROR_TOKEN", token), \
             patch("modules.summary.requests.post") as mock_post:
            summary.push_summary_snapshot()
        mock_post.assert_not_called()


class TestPush:
    def test_posts_the_summary_body_with_bearer_token_and_timeout(self, configured):
        with patch("modules.summary.requests.post") as mock_post:
            mock_post.return_value.status_code = 204
            summary.push_summary_snapshot()

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == MIRROR_URL
        assert kwargs["headers"] == {"Authorization": f"Bearer {MIRROR_TOKEN}"}
        assert kwargs["timeout"] == 5.0
        assert kwargs["json"] == {
            "service": "free-games-notifier",
            "active_promotions": [{
                "title": "Celeste",
                "link": "https://store.epicgames.com/p/celeste",
                "store": "epic",
                "end_date": FUTURE,
            }],
            "last_check_at": "2030-01-01T00:00:00+00:00",
        }

    def test_payload_matches_the_local_api_summary_response(self, configured):
        """The mirror must serve exactly what the local endpoint would."""
        from fastapi.testclient import TestClient

        from api import app

        games = [_game("Later", "2099-06-01T00:00:00.000Z"), _game("Sooner"), _game("NoDate", "")]
        with patch("modules.storage.load_previous_games", return_value=games), \
             patch("modules.summary.requests.post") as mock_post:
            mock_post.return_value.status_code = 204
            summary.push_summary_snapshot()
        pushed = mock_post.call_args.kwargs["json"]

        with patch("api.auth.DASHBOARD_API_KEY", "secret"), \
             patch("api.routes.summary.load_previous_games", return_value=games), \
             patch("api.routes.summary.get_last_check_completed_at", return_value=1893456000.0):
            served = TestClient(app).get("/api/summary", headers={"X-API-Key": "secret"}).json()

        assert pushed == served


class TestFireAndForget:
    """Every failure mode is swallowed, logged at WARNING, and tried exactly once."""

    @pytest.mark.parametrize("exc", [
        requests.exceptions.ConnectionError(f"Max retries exceeded with url: {MIRROR_URL}"),
        requests.exceptions.Timeout(f"Read timed out: {MIRROR_URL}"),
        RuntimeError(f"something unexpected with {MIRROR_URL}"),
    ])
    def test_endpoint_down_never_raises(self, configured, caplog, exc):
        with patch("modules.summary.requests.post", side_effect=exc) as mock_post, \
             caplog.at_level(logging.WARNING, logger="modules.summary"):
            summary.push_summary_snapshot()  # must not raise

        mock_post.assert_called_once()  # no retries
        assert any(r.levelno == logging.WARNING for r in caplog.records)
        assert not any(r.levelno >= logging.ERROR for r in caplog.records)
        assert "mirror.example.com" in caplog.text
        _assert_no_secrets_logged(caplog)

    @pytest.mark.parametrize("status", [401, 413, 500, 503])
    def test_non_2xx_response_is_a_warning_not_an_error(self, configured, caplog, status):
        with patch("modules.summary.requests.post") as mock_post, \
             caplog.at_level(logging.WARNING, logger="modules.summary"):
            mock_post.return_value.status_code = status
            summary.push_summary_snapshot()

        mock_post.assert_called_once()
        assert str(status) in caplog.text
        _assert_no_secrets_logged(caplog)

    def test_storage_failure_skips_push_instead_of_sending_an_empty_list(self, configured, caplog):
        with patch("modules.storage.load_previous_games", side_effect=RuntimeError("db down")), \
             patch("modules.summary.requests.post") as mock_post, \
             caplog.at_level(logging.WARNING, logger="modules.summary"):
            summary.push_summary_snapshot()

        mock_post.assert_not_called()
        assert "RuntimeError" in caplog.text


def _import_main():
    sys.modules.setdefault("alembic", MagicMock())
    sys.modules.setdefault("alembic.config", MagicMock())
    sys.modules.setdefault("alembic.command", MagicMock())
    sys.modules.pop("main", None)
    with patch("logging.handlers.TimedRotatingFileHandler"):
        import main as _main
    return _main


class TestCheckGamesIntegration:
    def _run_check(self, main, scraped):
        with patch("main.ENABLED_STORES", ["epic"]), \
             patch("modules.scrapers.epic.EpicGamesScraper.fetch_free_games", return_value=scraped), \
             patch("main.load_previous_games", return_value=[]), \
             patch("main.send_discord_message"), \
             patch("main.save_last_notification"), \
             patch("main.save_games") as mock_save, \
             patch("main.record_check_completed") as mock_record:
            main.check_games()
        return mock_save, mock_record

    def test_check_completes_even_when_the_mirror_is_down(self, configured):
        main = _import_main()
        with patch("modules.summary.requests.post",
                   side_effect=requests.exceptions.ConnectionError("down")) as mock_post:
            mock_save, mock_record = self._run_check(main, [_game("Celeste")])

        mock_save.assert_called_once()
        mock_record.assert_called_once()
        mock_post.assert_called_once()

    def test_no_push_when_the_check_did_not_complete(self, configured):
        """An early return (nothing scraped) must not refresh the mirror's last_check_at."""
        main = _import_main()
        with patch("main.push_summary_snapshot") as mock_push:
            self._run_check(main, [])
        mock_push.assert_not_called()
