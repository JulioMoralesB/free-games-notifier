"""Tests for the fire-and-forget push to the Cloudflare mirror (modules/mirror.py).

The push must never be able to fail a check, the heartbeat, or the process:
the heartbeat push once crashed the whole service for exactly this reason.
"""

import logging
import sys
from unittest.mock import MagicMock, patch

import pytest
import requests

from api.serializers import to_game_item_dict
from modules import mirror
from modules.models import FreeGame

MIRROR_URL = "https://mirror.example.com/base-path-secret"
MIRROR_TOKEN = "faketesttoken-not-a-real-secret"
FUTURE = "2099-01-01T00:00:00.000Z"
SUMMARY_URL = f"{MIRROR_URL}/api/mirror/summary"
GAMES_URL = f"{MIRROR_URL}/api/mirror/games"


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


def _ok(status=200, body=None):
    response = MagicMock(status_code=status)
    response.json.return_value = body if body is not None else {"stored": 0, "skipped": 0}
    return response


@pytest.fixture
def stored_games():
    return [_game("Celeste")]


@pytest.fixture
def configured(stored_games):
    """Enable the mirror with fake values and a stubbed storage read."""
    with patch.object(mirror, "MIRROR_URL", MIRROR_URL), \
         patch.object(mirror, "MIRROR_TOKEN", MIRROR_TOKEN), \
         patch.object(mirror, "MIRROR_TIMEOUT", 5.0), \
         patch("modules.storage.load_previous_games", return_value=stored_games), \
         patch("modules.summary.get_last_check_completed_at", return_value=1893456000.0):
        yield


def _urls(mock_post):
    return [c.args[0] for c in mock_post.call_args_list]


def _assert_no_secrets_logged(caplog):
    assert MIRROR_TOKEN not in caplog.text
    assert "base-path-secret" not in caplog.text
    assert "/api/mirror" not in caplog.text


class TestDisabled:
    @pytest.mark.parametrize("url,token", [(None, MIRROR_TOKEN), (MIRROR_URL, None), (None, None)])
    def test_no_request_unless_url_and_token_are_both_set(self, url, token):
        with patch.object(mirror, "MIRROR_URL", url), \
             patch.object(mirror, "MIRROR_TOKEN", token), \
             patch("modules.mirror.requests.post") as mock_post:
            mirror.push_to_mirror()
        mock_post.assert_not_called()


class TestPush:
    def test_posts_summary_then_history_with_bearer_token_and_timeout(self, configured):
        with patch("modules.mirror.requests.post", return_value=_ok()) as mock_post:
            mirror.push_to_mirror()

        assert _urls(mock_post) == [SUMMARY_URL, GAMES_URL]
        for call in mock_post.call_args_list:
            assert call.kwargs["headers"] == {"Authorization": f"Bearer {MIRROR_TOKEN}"}
            assert call.kwargs["timeout"] == 5.0
        assert mock_post.call_args_list[0].kwargs["json"] == {
            "service": "free-games-notifier",
            "active_promotions": [{
                "title": "Celeste",
                "link": "https://store.epicgames.com/p/celeste",
                "store": "epic",
                "end_date": FUTURE,
            }],
            "last_check_at": "2030-01-01T00:00:00+00:00",
        }

    def test_summary_payload_matches_the_local_api_summary_response(self, configured):
        """The mirror must serve exactly what the local endpoint would."""
        from fastapi.testclient import TestClient

        from api import app

        games = [_game("Later", "2099-06-01T00:00:00.000Z"), _game("Sooner"), _game("NoDate", "")]
        with patch("modules.storage.load_previous_games", return_value=games), \
             patch("modules.mirror.requests.post", return_value=_ok()) as mock_post:
            mirror.push_to_mirror()
        pushed = mock_post.call_args_list[0].kwargs["json"]

        with patch("api.auth.DASHBOARD_API_KEY", "secret"), \
             patch("api.routes.summary.load_previous_games", return_value=games), \
             patch("api.routes.summary.get_last_check_completed_at", return_value=1893456000.0):
            served = TestClient(app).get("/api/summary", headers={"X-API-Key": "secret"}).json()

        assert pushed == served

    def test_history_is_sent_in_chunks_of_one_sync_with_final_only_on_the_last(self, configured):
        games = [_game(f"Game{i}") for i in range(250)]
        with patch("modules.storage.load_previous_games", return_value=games), \
             patch("modules.mirror.requests.post", return_value=_ok()) as mock_post:
            mirror.push_to_mirror()

        chunks = [c.kwargs["json"] for c in mock_post.call_args_list[1:]]
        assert _urls(mock_post)[1:] == [GAMES_URL] * 3
        assert [len(c["games"]) for c in chunks] == [100, 100, 50]
        assert [c["final"] for c in chunks] == [False, False, True]
        assert len({c["sync_id"] for c in chunks}) == 1
        assert [g for c in chunks for g in c["games"]] == [to_game_item_dict(g) for g in games]

    def test_empty_history_still_sends_one_final_chunk(self, configured):
        with patch("modules.storage.load_previous_games", return_value=[]), \
             patch("modules.mirror.requests.post", return_value=_ok()) as mock_post:
            mirror.push_to_mirror()

        assert mock_post.call_args_list[1].kwargs["json"]["games"] == []
        assert mock_post.call_args_list[1].kwargs["json"]["final"] is True

    def test_skipped_records_reported_by_the_mirror_are_logged(self, configured, caplog):
        with patch("modules.mirror.requests.post", return_value=_ok(body={"stored": 0, "skipped": 2})), \
             caplog.at_level(logging.WARNING, logger="modules.mirror"):
            mirror.push_to_mirror()
        assert "skipped 2 invalid game record(s)" in caplog.text


class TestFireAndForget:
    """Every failure mode is swallowed, logged at WARNING, and stops the push."""

    @pytest.mark.parametrize("exc", [
        requests.exceptions.ConnectionError(f"Max retries exceeded with url: {SUMMARY_URL}"),
        requests.exceptions.Timeout(f"Read timed out: {SUMMARY_URL}"),
        RuntimeError(f"something unexpected with {SUMMARY_URL}"),
    ])
    def test_mirror_down_never_raises_and_costs_one_attempt(self, configured, caplog, exc):
        with patch("modules.mirror.requests.post", side_effect=exc) as mock_post, \
             caplog.at_level(logging.WARNING, logger="modules.mirror"):
            mirror.push_to_mirror()  # must not raise

        mock_post.assert_called_once()  # no retries, and no history push after it
        assert any(r.levelno == logging.WARNING for r in caplog.records)
        assert not any(r.levelno >= logging.ERROR for r in caplog.records)
        assert "mirror.example.com" in caplog.text
        _assert_no_secrets_logged(caplog)

    @pytest.mark.parametrize("status", [401, 413, 500, 503])
    def test_rejected_summary_skips_the_history_push(self, configured, caplog, status):
        with patch("modules.mirror.requests.post", return_value=_ok(status)) as mock_post, \
             caplog.at_level(logging.WARNING, logger="modules.mirror"):
            mirror.push_to_mirror()

        mock_post.assert_called_once()
        assert str(status) in caplog.text
        _assert_no_secrets_logged(caplog)

    def test_failed_history_chunk_stops_the_sync_before_the_final_chunk(self, configured):
        games = [_game(f"Game{i}") for i in range(250)]
        responses = [_ok(), _ok(), requests.exceptions.ConnectionError("down"), _ok()]
        with patch("modules.storage.load_previous_games", return_value=games), \
             patch("modules.mirror.requests.post", side_effect=responses) as mock_post:
            mirror.push_to_mirror()

        sent = [c.kwargs["json"] for c in mock_post.call_args_list[1:]]
        assert len(sent) == 2  # chunk 1 ok, chunk 2 failed, chunk 3 (final) never sent
        assert not any(c["final"] for c in sent)

    def test_storage_failure_sends_nothing(self, configured, caplog):
        """Never push an empty summary — or an empty history the mirror would sync-delete."""
        with patch("modules.storage.load_previous_games", side_effect=RuntimeError("db down")), \
             patch("modules.mirror.requests.post") as mock_post, \
             caplog.at_level(logging.WARNING, logger="modules.mirror"):
            mirror.push_to_mirror()

        mock_post.assert_not_called()
        assert "RuntimeError" in caplog.text

    def test_unreadable_mirror_response_body_is_tolerated(self, configured):
        bad = _ok()
        bad.json.side_effect = ValueError("not json")
        with patch("modules.mirror.requests.post", return_value=bad) as mock_post:
            mirror.push_to_mirror()
        assert mock_post.call_count == 2


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
        with patch("modules.mirror.requests.post",
                   side_effect=requests.exceptions.ConnectionError("down")) as mock_post:
            mock_save, mock_record = self._run_check(main, [_game("Celeste")])

        mock_save.assert_called_once()
        mock_record.assert_called_once()
        mock_post.assert_called_once()

    def test_no_push_when_the_check_did_not_complete(self, configured):
        """An early return (nothing scraped) must not refresh the mirror's last_check_at."""
        main = _import_main()
        with patch("main.push_to_mirror") as mock_push:
            self._run_check(main, [])
        mock_push.assert_not_called()
