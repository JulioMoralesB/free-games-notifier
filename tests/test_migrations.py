"""Tests for the database migration runner in main.py."""

import sys
from unittest.mock import MagicMock, call, patch

import pytest

from modules.models import FreeGame


def _import_main():
    """Import (or reimport) main with the log-file handler mocked out.

    main.py creates a TimedRotatingFileHandler at module level which requires
    /mnt/logs/notifier.log to exist.  In the test environment this path is not
    available, so we mock the handler class before the module is loaded.

    alembic may also be absent in the local dev environment; setdefault inserts
    a stub only when the real package is not installed (no-op in CI).
    """
    sys.modules.setdefault("alembic", MagicMock())
    sys.modules.setdefault("alembic.config", MagicMock())
    sys.modules.setdefault("alembic.command", MagicMock())
    # Remove cached module so it is re-executed under the mock.
    sys.modules.pop("main", None)
    with patch("logging.handlers.TimedRotatingFileHandler"):
        import main as _main
    return _main


class TestRunDbMigrations:
    """Tests for main.run_db_migrations()."""

    def test_calls_alembic_upgrade_head(self):
        """_run_db_migrations should invoke alembic upgrade with 'head'."""
        main = _import_main()

        mock_upgrade = MagicMock()
        with patch("modules.db_lifecycle.alembic_command.upgrade", mock_upgrade):
            main.run_db_migrations()

        assert mock_upgrade.call_count == 1
        _, upgrade_target = mock_upgrade.call_args[0]
        assert upgrade_target == "head"

    def test_passes_alembic_config_object(self):
        """_run_db_migrations should pass an AlembicConfig instance to upgrade."""
        if isinstance(sys.modules.get("alembic"), MagicMock):
            pytest.skip("alembic not installed; skipping AlembicConfig isinstance check")
        from alembic.config import Config as AlembicConfig
        main = _import_main()

        captured_cfg = {}

        def capture_upgrade(cfg, target):
            captured_cfg["cfg"] = cfg

        with patch("modules.db_lifecycle.alembic_command.upgrade", side_effect=capture_upgrade):
            main.run_db_migrations()

        assert isinstance(captured_cfg["cfg"], AlembicConfig)

    def test_propagates_alembic_exception(self):
        """_run_db_migrations should not swallow exceptions from alembic."""
        main = _import_main()

        with patch("modules.db_lifecycle.alembic_command.upgrade", side_effect=RuntimeError("db error")):
            with pytest.raises(RuntimeError, match="db error"):
                main.run_db_migrations()


class TestVerifyRequiredTables:
    """Tests for main.verify_required_tables()."""

    def test_succeeds_when_last_notification_exists(self):
        """Verification should pass when the required table exists."""
        main = _import_main()

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = ("free_games.last_notification",)

        mock_conn = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        with patch("modules.db_lifecycle.psycopg2.connect", return_value=mock_conn):
            main.verify_required_tables()

    def test_raises_when_last_notification_is_missing(self):
        """Verification should fail fast when last_notification table is absent."""
        main = _import_main()

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (None,)

        mock_conn = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        with patch("modules.db_lifecycle.psycopg2.connect", return_value=mock_conn):
            with pytest.raises(RuntimeError, match="last_notification"):
                main.verify_required_tables()


class TestMainDbBranch:
    """Tests for the DB-enabled branch of main()."""

    def test_runs_migrations_when_db_host_is_set(self):
        """main() should call _run_db_migrations when DB_HOST is configured."""
        main = _import_main()

        mock_db = MagicMock()
        with patch("main.DB_HOST", "localhost"), \
             patch("main.FreeGamesDatabase", return_value=mock_db), \
             patch("main.run_db_migrations") as mock_migrate, \
             patch("main.verify_required_tables") as mock_verify_tables, \
             patch("main._start_api_server"), \
             patch("main.check_games"), \
             patch("main.healthcheck"), \
             patch("main.schedule"), \
             patch("main.time.sleep", side_effect=KeyboardInterrupt):
            try:
                main.main()
            except KeyboardInterrupt:
                pass

        mock_db.init_db.assert_called_once()
        mock_migrate.assert_called_once()
        mock_verify_tables.assert_called_once()

    def test_does_not_run_migrations_when_db_host_is_not_set(self):
        """main() should skip DB init and migrations when DB_HOST is not set."""
        main = _import_main()

        with patch("main.DB_HOST", None), \
             patch("main.run_db_migrations") as mock_migrate, \
             patch("main.verify_required_tables") as mock_verify_tables, \
             patch("main.FreeGamesDatabase") as mock_db_cls, \
             patch("main._start_api_server"), \
             patch("main.check_games"), \
             patch("main.healthcheck"), \
             patch("main.schedule"), \
             patch("main.time.sleep", side_effect=KeyboardInterrupt):
            try:
                main.main()
            except KeyboardInterrupt:
                pass

        mock_db_cls.assert_not_called()
        mock_migrate.assert_not_called()
        mock_verify_tables.assert_not_called()


class TestScheduling:
    """Tests for the check_games scheduling logic (interval vs daily mode)."""

    def _run_main_with_patches(self, main, extra_patches):
        """Run main.main() with common patches applied, stopping after one scheduler tick."""
        base = {
            "main.DB_HOST": None,
            "main._start_api_server": MagicMock(),
            "main.check_games": MagicMock(),
            "main.healthcheck": MagicMock(),
            "main.time.sleep": MagicMock(side_effect=KeyboardInterrupt),
        }
        base.update(extra_patches)
        patchers = [patch(k, v) for k, v in base.items()]
        mock_schedule = MagicMock()
        # schedule.every(...) returns a job mock; chain .hours/.day/.at().do() on it
        mock_schedule.every.return_value = mock_schedule
        mock_schedule.day = mock_schedule
        mock_schedule.at.return_value = mock_schedule

        with patch("main.schedule", mock_schedule):
            for p in patchers:
                p.start()
            try:
                main.main()
            except KeyboardInterrupt:
                pass
            finally:
                for p in patchers:
                    p.stop()

        return mock_schedule

    def test_interval_mode_when_check_interval_hours_is_set(self):
        """When CHECK_INTERVAL_HOURS is set, schedule.every(N).hours should be used."""
        main = _import_main()

        mock_schedule = self._run_main_with_patches(
            main, {"main.CHECK_INTERVAL_HOURS": 6.0}
        )

        # schedule.every(6.0) should have been called
        calls = [str(c) for c in mock_schedule.every.call_args_list]
        assert any("6.0" in c or "6" in c for c in calls), (
            f"Expected schedule.every(6.0) for interval mode, got: {calls}"
        )
        mock_schedule.hours.do.assert_called()

    def test_daily_mode_when_check_interval_hours_is_none(self):
        """When CHECK_INTERVAL_HOURS is None, schedule.every().day.at() should be used."""
        main = _import_main()

        mock_schedule = self._run_main_with_patches(
            main, {"main.CHECK_INTERVAL_HOURS": None, "main.SCHEDULE_TIME": "08:00"}
        )

        # schedule.every() (no args) should have been called for the daily job
        no_arg_calls = [c for c in mock_schedule.every.call_args_list if c == call()]
        assert no_arg_calls, (
            "Expected schedule.every() (no args) for daily mode."
        )
        mock_schedule.at.assert_called()

    def test_interval_mode_does_not_use_schedule_time(self):
        """In interval mode, .day.at() must NOT be called for the game-check job."""
        main = _import_main()

        mock_schedule = self._run_main_with_patches(
            main, {"main.CHECK_INTERVAL_HOURS": 3.0}
        )

        mock_schedule.at.assert_not_called()


def _make_game(title, link, description="desc", thumbnail="https://example.com/img.png", end_date="2026-04-16T15:00:00.000Z"):
    """Helper to create a FreeGame for testing."""
    return FreeGame(
        title=title,
        store="epic",
        url=link,
        image_url=thumbnail,
        original_price=None,
        end_date=end_date,
        is_permanent=False,
        description=description,
    )


class TestCheckGamesDedupe:
    """Tests for check_games new-game detection behavior."""

    def test_does_not_notify_when_only_non_identity_fields_change(self):
        """No Discord notification should be sent when only thumbnail/description changes."""
        main = _import_main()

        previous_games = [
            _make_game(
                "TOMAK: Save the Earth Regeneration",
                "https://store.epicgames.com/es-MX/p/tomak-save-the-earth-regeneration-c1207c",
                description="old description",
                thumbnail="https://cdn1.epicgames.com/old-image.png",
                end_date="2026-04-16T15:00:00.000Z",
            )
        ]
        current_games = [
            _make_game(
                "TOMAK: Save the Earth Regeneration",
                "https://store.epicgames.com/es-MX/p/tomak-save-the-earth-regeneration-c1207c",
                description="new description",
                thumbnail="https://cdn1.epicgames.com/new-image.png",
                end_date="2026-04-16T15:00:00.000Z",
            )
        ]

        with patch("main.ENABLED_STORES", ["epic"]), \
             patch("modules.scrapers.epic.EpicGamesScraper.fetch_free_games", return_value=current_games), \
             patch("main.load_previous_games", return_value=previous_games), \
             patch("main.send_discord_message") as mock_send_discord, \
             patch("main.save_last_notification") as mock_save_last_notification, \
             patch("main.save_games") as mock_save_games:
            main.check_games()

        mock_send_discord.assert_not_called()
        mock_save_last_notification.assert_not_called()
        mock_save_games.assert_called_once_with(current_games)

    def test_notifies_when_link_is_new(self):
        """Discord notification should be sent only for games with unseen links."""
        main = _import_main()

        previous_games = [
            _make_game(
                "Old Game",
                "https://store.epicgames.com/es-MX/p/old-game",
                end_date="2026-04-09T15:00:00.000Z",
            )
        ]
        current_games = [
            _make_game(
                "Old Game",
                "https://store.epicgames.com/es-MX/p/old-game",
                description="updated desc",
                end_date="2026-04-09T15:00:00.000Z",
            ),
            _make_game(
                "Brand New Game",
                "https://store.epicgames.com/es-MX/p/brand-new-game",
                end_date="2026-04-16T15:00:00.000Z",
            ),
        ]

        with patch("main.ENABLED_STORES", ["epic"]), \
             patch("modules.scrapers.epic.EpicGamesScraper.fetch_free_games", return_value=current_games), \
             patch("main.load_previous_games", return_value=previous_games), \
             patch("main.send_discord_message") as mock_send_discord, \
             patch("main.save_last_notification") as mock_save_last_notification, \
             patch("main.save_games") as mock_save_games:
            main.check_games()

        mock_send_discord.assert_called_once_with([current_games[1]])
        mock_save_last_notification.assert_called_once_with([current_games[1]])
        mock_save_games.assert_called_once_with(current_games)

    def test_notifies_again_when_previous_promo_has_expired(self):
        """A game can be notified again when its prior free period has already ended."""
        main = _import_main()

        previous_games = [
            _make_game(
                "Recurring Game",
                "https://store.epicgames.com/es-MX/p/recurring-game",
                end_date="2025-10-01T15:00:00.000Z",
            )
        ]
        current_games = [
            _make_game(
                "Recurring Game",
                "https://store.epicgames.com/es-MX/p/recurring-game",
                end_date="2026-10-01T15:00:00.000Z",
            )
        ]

        with patch("main.ENABLED_STORES", ["epic"]), \
             patch("modules.scrapers.epic.EpicGamesScraper.fetch_free_games", return_value=current_games), \
             patch("main.load_previous_games", return_value=previous_games), \
             patch("main.send_discord_message") as mock_send_discord, \
             patch("main.save_last_notification") as mock_save_last_notification, \
             patch("main.save_games") as mock_save_games:
            main.check_games()

        mock_send_discord.assert_called_once_with(current_games)
        mock_save_last_notification.assert_called_once_with(current_games)
        mock_save_games.assert_called_once_with(current_games)

    def test_does_not_notify_when_previous_promo_is_still_active(self):
        """No duplicate notification while the previously notified promo is still active."""
        main = _import_main()

        previous_games = [
            _make_game(
                "Still Free",
                "https://store.epicgames.com/es-MX/p/still-free",
                end_date="2099-10-01T15:00:00.000Z",
            )
        ]
        current_games = [
            _make_game(
                "Still Free",
                "https://store.epicgames.com/es-MX/p/still-free",
                end_date="2099-10-01T15:00:00.000Z",
            )
        ]

        with patch("main.ENABLED_STORES", ["epic"]), \
             patch("modules.scrapers.epic.EpicGamesScraper.fetch_free_games", return_value=current_games), \
             patch("main.load_previous_games", return_value=previous_games), \
             patch("main.send_discord_message") as mock_send_discord, \
             patch("main.save_last_notification") as mock_save_last_notification, \
             patch("main.save_games") as mock_save_games:
            main.check_games()

        mock_send_discord.assert_not_called()
        mock_save_last_notification.assert_not_called()
        mock_save_games.assert_called_once_with(current_games)


class TestFindNewGamesEdgeCases:
    """Tests for _find_new_games / _is_still_active edge cases."""

    def test_missing_end_date_treated_as_active(self):
        """A previous game with no end_date should be treated as still active (no re-notify)."""
        main = _import_main()

        previous_games = [
            _make_game(
                "Free Game",
                "https://store.epicgames.com/es-MX/p/free-game",
                end_date="",
            )
        ]
        current_games = [
            _make_game(
                "Free Game",
                "https://store.epicgames.com/es-MX/p/free-game",
                end_date="",
            )
        ]

        result = main.find_new_games(current_games, previous_games)

        assert result == [], "Missing end_date should be treated as active; no new games expected"

    def test_none_end_date_treated_as_active(self):
        """A previous game with end_date='' (empty) should be treated as still active."""
        main = _import_main()

        previous_games = [
            _make_game(
                "Free Game",
                "https://store.epicgames.com/es-MX/p/free-game",
                end_date="",
            )
        ]
        current_games = [
            _make_game(
                "Free Game",
                "https://store.epicgames.com/es-MX/p/free-game",
                end_date="",
            )
        ]

        result = main.find_new_games(current_games, previous_games)

        assert result == [], "empty end_date should be treated as active; no new games expected"

    def test_malformed_end_date_treated_as_active(self):
        """A previous game with a malformed end_date (non-ISO string) should be treated as still active."""
        main = _import_main()

        previous_games = [
            _make_game(
                "Free Game",
                "https://store.epicgames.com/es-MX/p/free-game",
                end_date="not-a-valid-date",
            )
        ]
        current_games = [
            _make_game(
                "Free Game",
                "https://store.epicgames.com/es-MX/p/free-game",
                end_date="2099-01-01T00:00:00.000Z",
            )
        ]

        result = main.find_new_games(current_games, previous_games)

        assert result == [], "Malformed end_date should be treated as active; no new games expected"

    def test_naive_datetime_without_tzinfo_treated_as_future(self):
        """A previous game with a naive ISO datetime (no timezone) should be assigned UTC and handled correctly."""
        main = _import_main()

        # A naive far-future date that should be treated as active.
        previous_games = [
            _make_game(
                "Free Game",
                "https://store.epicgames.com/es-MX/p/free-game",
                end_date="2099-01-01T00:00:00",  # no timezone suffix
            )
        ]
        current_games = [
            _make_game(
                "Free Game",
                "https://store.epicgames.com/es-MX/p/free-game",
                end_date="2099-01-01T00:00:00",
            )
        ]

        result = main.find_new_games(current_games, previous_games)

        assert result == [], "Naive far-future end_date should be treated as active after UTC assignment"

    def test_naive_datetime_in_past_treated_as_expired(self):
        """A previous game with a naive ISO datetime in the past should be treated as expired."""
        main = _import_main()

        previous_games = [
            _make_game(
                "Free Game",
                "https://store.epicgames.com/es-MX/p/free-game",
                end_date="2000-01-01T00:00:00",  # naive past date
            )
        ]
        current_games = [
            _make_game(
                "Free Game",
                "https://store.epicgames.com/es-MX/p/free-game",
                end_date="2099-01-01T00:00:00",
            )
        ]

        result = main.find_new_games(current_games, previous_games)

        assert result == current_games, "Naive past end_date should be treated as expired; game should appear as new"

    def test_recently_expired_with_different_end_date_not_renotified(self):
        """A game whose promo expired within the grace period must not trigger a
        re-notification even when the store returns a different end_date.

        Reproduces the SurrounDead bug: Steam returned end_date with the wrong
        year (2027 instead of 2026) minutes after the original promo ended,
        causing _find_new_games to treat it as a brand-new game.
        """
        from datetime import datetime, timedelta, timezone
        main = _import_main()

        # Simulate an end_date that expired 30 minutes ago.
        expired_recently = (
            datetime.now(timezone.utc) - timedelta(minutes=30)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

        # The store now returns the same URL but with a wrong end_date (a year later).
        wrong_end_date = (
            datetime.now(timezone.utc) + timedelta(days=365)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

        previous_games = [
            _make_game(
                "SurrounDead Poly Construction",
                "https://store.steampowered.com/app/4148570/SurrounDead_Poly_Construction/",
                end_date=expired_recently,
            )
        ]
        current_games = [
            _make_game(
                "SurrounDead Poly Construction",
                "https://store.steampowered.com/app/4148570/SurrounDead_Poly_Construction/",
                end_date=wrong_end_date,
            )
        ]

        result = main.find_new_games(current_games, previous_games)

        assert result == [], (
            "A recently-expired game returning a different end_date should not "
            "trigger a re-notification within the grace period"
        )

    def test_long_expired_game_with_new_end_date_is_renotified(self):
        """A game whose promo expired well beyond the grace period IS allowed to
        re-notify if the store shows it free again with a new end_date.
        """
        from datetime import datetime, timedelta, timezone
        main = _import_main()

        old_end_date = (
            datetime.now(timezone.utc) - timedelta(days=30)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

        new_end_date = (
            datetime.now(timezone.utc) + timedelta(days=7)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

        previous_games = [
            _make_game(
                "Recurring Game",
                "https://store.steampowered.com/app/99999/Recurring_Game/",
                end_date=old_end_date,
            )
        ]
        current_games = [
            _make_game(
                "Recurring Game",
                "https://store.steampowered.com/app/99999/Recurring_Game/",
                end_date=new_end_date,
            )
        ]

        result = main.find_new_games(current_games, previous_games)

        assert result == current_games, (
            "A game that was free long ago and is now free again should trigger "
            "a new notification"
        )
