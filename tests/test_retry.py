from unittest.mock import MagicMock, call, patch

import pytest
import requests

from modules import notifier
from modules.retry import with_retry
from modules.scrapers.epic import EpicGamesScraper

# ---------------------------------------------------------------------------
# Tests for with_retry utility
# ---------------------------------------------------------------------------

class TestWithRetry:
    def test_returns_result_on_first_success(self):
        func = MagicMock(return_value="ok")
        result = with_retry(func, max_attempts=3, base_delay=0,
                            retryable_exceptions=(ValueError,))
        assert result == "ok"
        assert func.call_count == 1

    def test_retries_on_retryable_exception(self):
        func = MagicMock(side_effect=[ValueError("fail"), "ok"])
        with patch("modules.retry.time.sleep") as mock_sleep:
            result = with_retry(func, max_attempts=3, base_delay=1,
                                retryable_exceptions=(ValueError,))
        assert result == "ok"
        assert func.call_count == 2
        mock_sleep.assert_called_once_with(1)

    def test_uses_exponential_backoff(self):
        func = MagicMock(side_effect=[ValueError(), ValueError(), "ok"])
        with patch("modules.retry.time.sleep") as mock_sleep:
            result = with_retry(func, max_attempts=3, base_delay=1,
                                retryable_exceptions=(ValueError,))
        assert result == "ok"
        assert mock_sleep.call_args_list == [call(1), call(2)]

    def test_raises_after_all_attempts_exhausted(self):
        func = MagicMock(side_effect=ValueError("persistent"))
        with patch("modules.retry.time.sleep"):
            with pytest.raises(ValueError, match="persistent"):
                with_retry(func, max_attempts=3, base_delay=1,
                           retryable_exceptions=(ValueError,))
        assert func.call_count == 3

    def test_does_not_retry_on_non_retryable_exception(self):
        func = MagicMock(side_effect=RuntimeError("not retryable"))
        with patch("modules.retry.time.sleep") as mock_sleep:
            with pytest.raises(RuntimeError):
                with_retry(func, max_attempts=3, base_delay=1,
                           retryable_exceptions=(ValueError,))
        assert func.call_count == 1
        mock_sleep.assert_not_called()

    def test_no_sleep_after_last_attempt(self):
        func = MagicMock(side_effect=ValueError("fail"))
        with patch("modules.retry.time.sleep") as mock_sleep:
            with pytest.raises(ValueError):
                with_retry(func, max_attempts=2, base_delay=1,
                           retryable_exceptions=(ValueError,))
        # Only one sleep (before the second attempt); no sleep after the final failure
        assert mock_sleep.call_count == 1

    def test_single_attempt_does_not_sleep(self):
        func = MagicMock(side_effect=ValueError("fail"))
        with patch("modules.retry.time.sleep") as mock_sleep:
            with pytest.raises(ValueError):
                with_retry(func, max_attempts=1, base_delay=1,
                           retryable_exceptions=(ValueError,))
        mock_sleep.assert_not_called()


# ---------------------------------------------------------------------------
# Tests for retry in fetch_free_games (scrapper)
# ---------------------------------------------------------------------------

class TestFetchFreeGamesRetry:
    def _make_response(self, status_code=200, json_data=None):
        mock = MagicMock()
        mock.status_code = status_code
        mock.json.return_value = json_data or {"data": {"Catalog": {"searchStore": {"elements": []}}}}
        return mock

    def test_retries_on_timeout_and_succeeds(self):
        good_response = self._make_response(200)
        with patch("modules.scrapers.epic.requests.get") as mock_get, \
             patch("modules.retry.time.sleep"):
            mock_get.side_effect = [
                requests.exceptions.Timeout(),
                good_response,
            ]
            scraper = EpicGamesScraper()
            games = scraper.fetch_free_games()

        assert mock_get.call_count == 2
        assert games == []  # empty elements list → no games

    def test_retries_on_connection_error_and_succeeds(self):
        good_response = self._make_response(200)
        with patch("modules.scrapers.epic.requests.get") as mock_get, \
             patch("modules.retry.time.sleep"):
            mock_get.side_effect = [
                requests.exceptions.ConnectionError(),
                good_response,
            ]
            scraper = EpicGamesScraper()
            scraper.fetch_free_games()

        assert mock_get.call_count == 2

    def test_returns_empty_after_max_retries_exhausted(self):
        with patch("modules.scrapers.epic.requests.get") as mock_get, \
             patch("modules.retry.time.sleep"):
            mock_get.side_effect = requests.exceptions.Timeout()
            scraper = EpicGamesScraper()
            games = scraper.fetch_free_games()

        assert games == []
        assert mock_get.call_count == 4

    def test_max_four_attempts_for_api(self):
        with patch("modules.scrapers.epic.requests.get") as mock_get, \
             patch("modules.retry.time.sleep") as mock_sleep:
            mock_get.side_effect = requests.exceptions.ConnectionError()
            scraper = EpicGamesScraper()
            scraper.fetch_free_games()

        assert mock_get.call_count == 4
        # Delays: 1s before attempt 2, 2s before attempt 3, 4s before attempt 4
        assert mock_sleep.call_args_list == [call(1), call(2), call(4)]

    def test_no_retry_on_non_200_status(self):
        with patch("modules.scrapers.epic.requests.get") as mock_get, \
             patch("modules.retry.time.sleep") as mock_sleep:
            mock_get.return_value = self._make_response(500)
            scraper = EpicGamesScraper()
            games = scraper.fetch_free_games()

        assert games == []
        assert mock_get.call_count == 1
        mock_sleep.assert_not_called()

    def test_adds_timeout_to_api_request(self):
        good_response = self._make_response(200)
        with patch("modules.scrapers.epic.requests.get", return_value=good_response) as mock_get:
            scraper = EpicGamesScraper()
            scraper.fetch_free_games()

        _, kwargs = mock_get.call_args
        assert kwargs.get("timeout") == 10


# ---------------------------------------------------------------------------
# Tests for retry in send_discord_message (notifier)
# ---------------------------------------------------------------------------

VALID_WEBHOOK = "https://discord.com/api/webhooks/123456789/token_abc"


class TestSendDiscordMessageRetry:
    def _make_response(self, status_code=204):
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_resp.text = ""
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    def test_retries_on_timeout_and_succeeds(self, sample_games):
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier.requests.post") as mock_post, \
             patch("modules.retry.time.sleep"):
            mock_post.side_effect = [
                requests.exceptions.Timeout(),
                self._make_response(204),
            ]
            notifier.send_discord_message(sample_games)

        assert mock_post.call_count == 2

    def test_retries_on_connection_error_and_succeeds(self, sample_games):
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier.requests.post") as mock_post, \
             patch("modules.retry.time.sleep"):
            mock_post.side_effect = [
                requests.exceptions.ConnectionError(),
                self._make_response(204),
            ]
            notifier.send_discord_message(sample_games)

        assert mock_post.call_count == 2

    def test_raises_after_max_discord_retries(self, sample_games):
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier.requests.post") as mock_post, \
             patch("modules.retry.time.sleep"):
            mock_post.side_effect = requests.exceptions.Timeout()
            with pytest.raises(requests.exceptions.Timeout):
                notifier.send_discord_message(sample_games)

        assert mock_post.call_count == 2

    def test_max_two_attempts_for_discord(self, sample_games):
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier.requests.post") as mock_post, \
             patch("modules.retry.time.sleep") as mock_sleep:
            mock_post.side_effect = requests.exceptions.ConnectionError()
            with pytest.raises(requests.exceptions.ConnectionError):
                notifier.send_discord_message(sample_games)

        assert mock_post.call_count == 2
        # Only one sleep (1s before the second attempt)
        assert mock_sleep.call_args_list == [call(1)]

    def test_no_retry_on_http_error_status(self, sample_games):
        mock_resp = self._make_response(400)
        mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError("400")
        with patch("modules.notifier.DISCORD_WEBHOOK_URL", VALID_WEBHOOK), \
             patch("modules.notifier.requests.post", return_value=mock_resp) as mock_post, \
             patch("modules.retry.time.sleep") as mock_sleep:
            with pytest.raises(requests.exceptions.HTTPError):
                notifier.send_discord_message(sample_games)

        assert mock_post.call_count == 1
        mock_sleep.assert_not_called()
