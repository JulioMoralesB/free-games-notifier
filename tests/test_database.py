from unittest.mock import MagicMock, patch

import psycopg2
import pytest

from modules.database import FreeGamesDatabase


def _make_connect_mock():
    """Build a MagicMock usable as `with psycopg2.connect(...) as conn:`."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    return mock_conn


class TestInitDb:
    def test_succeeds_on_first_try_without_retry(self):
        mock_conn = _make_connect_mock()
        with patch("modules.database.psycopg2.connect", return_value=mock_conn) as mock_connect, \
             patch("modules.retry.time.sleep") as mock_sleep:
            FreeGamesDatabase().init_db()

        assert mock_connect.call_count == 1
        mock_sleep.assert_not_called()

    def test_retries_on_operational_error_and_succeeds(self, caplog):
        mock_conn = _make_connect_mock()
        with patch(
            "modules.database.psycopg2.connect",
            side_effect=[psycopg2.OperationalError("could not translate host name \"db\"\n"), mock_conn],
        ) as mock_connect, patch("modules.retry.time.sleep") as mock_sleep, caplog.at_level("WARNING"):
            FreeGamesDatabase().init_db()

        assert mock_connect.call_count == 2
        mock_sleep.assert_called_once_with(1)
        assert "ERROR" not in [r.levelname for r in caplog.records]
        assert any(r.levelname == "WARNING" for r in caplog.records)

    def test_raises_and_logs_exactly_one_error_after_retries_exhausted(self, caplog):
        with patch(
            "modules.database.psycopg2.connect",
            side_effect=psycopg2.OperationalError("could not translate host name \"db\"\n"),
        ), patch("modules.retry.time.sleep"), caplog.at_level("WARNING"):
            with pytest.raises(psycopg2.OperationalError):
                FreeGamesDatabase().init_db()

        error_records = [r for r in caplog.records if r.levelname == "ERROR"]
        assert len(error_records) == 1

    def test_error_message_has_no_trailing_newline(self, caplog):
        with patch(
            "modules.database.psycopg2.connect",
            side_effect=psycopg2.OperationalError("could not translate host name \"db\"\n"),
        ), patch("modules.retry.time.sleep"), caplog.at_level("WARNING"):
            with pytest.raises(psycopg2.OperationalError):
                FreeGamesDatabase().init_db()

        for record in caplog.records:
            assert "\n" not in record.getMessage()

    def test_does_not_retry_non_operational_errors(self, caplog):
        with patch(
            "modules.database.psycopg2.connect",
            side_effect=ValueError("bad SQL"),
        ), patch("modules.retry.time.sleep") as mock_sleep, caplog.at_level("ERROR"):
            with pytest.raises(ValueError):
                FreeGamesDatabase().init_db()

        mock_sleep.assert_not_called()
        assert "Failed to initialize database" in caplog.text
