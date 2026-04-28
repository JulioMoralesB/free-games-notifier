import json
import os
from unittest.mock import MagicMock, patch

import pytest

from modules import storage
from modules.database import FreeGamesDatabase
from modules.models import FreeGame

# ---------------------------------------------------------------------------
# Tests for load_previous_games
# ---------------------------------------------------------------------------

class TestLoadPreviousGames:
    def test_returns_empty_list_when_file_not_exists(self, tmp_path):
        path = str(tmp_path / "nonexistent.json")
        with patch("modules.storage.DB_HOST", None), \
             patch("modules.storage.DATA_FILE_PATH", path):
            result = storage.load_previous_games()
        assert result == []

    def test_loads_valid_json_file(self, tmp_path, sample_games):
        path = str(tmp_path / "games.json")
        with open(path, "w") as f:
            json.dump([g.to_dict() for g in sample_games], f)
        with patch("modules.storage.DB_HOST", None), \
             patch("modules.storage.DATA_FILE_PATH", path):
            result = storage.load_previous_games()
        assert result == sample_games

    def test_returns_empty_list_on_corrupted_json(self, tmp_path):
        path = str(tmp_path / "games.json")
        with open(path, "w") as f:
            f.write("this is not valid json {{{{")
        with patch("modules.storage.DB_HOST", None), \
             patch("modules.storage.DATA_FILE_PATH", path):
            result = storage.load_previous_games()
        assert result == []

    def test_returns_empty_list_when_data_is_not_a_list(self, tmp_path):
        path = str(tmp_path / "games.json")
        with open(path, "w") as f:
            json.dump({"key": "value"}, f)
        with patch("modules.storage.DB_HOST", None), \
             patch("modules.storage.DATA_FILE_PATH", path):
            result = storage.load_previous_games()
        assert result == []

    def test_returns_empty_list_when_items_are_not_dicts(self, tmp_path):
        path = str(tmp_path / "games.json")
        with open(path, "w") as f:
            json.dump(["game1", "game2"], f)
        with patch("modules.storage.DB_HOST", None), \
             patch("modules.storage.DATA_FILE_PATH", path):
            result = storage.load_previous_games()
        assert result == []

    def test_returns_empty_list_on_io_error(self, tmp_path):
        path = str(tmp_path / "games.json")
        (tmp_path / "games.json").write_text("[]")
        with patch("modules.storage.DB_HOST", None), \
             patch("modules.storage.DATA_FILE_PATH", path), \
             patch("builtins.open", side_effect=IOError("disk read error")):
            result = storage.load_previous_games()
        assert result == []

    def test_loaded_games_preserve_all_fields(self, tmp_path, sample_game):
        path = str(tmp_path / "games.json")
        with open(path, "w") as f:
            json.dump([sample_game.to_dict()], f)
        with patch("modules.storage.DB_HOST", None), \
             patch("modules.storage.DATA_FILE_PATH", path):
            result = storage.load_previous_games()
        assert result[0].title == sample_game.title
        assert result[0].url == sample_game.url
        assert result[0].end_date == sample_game.end_date
        assert result[0].description == sample_game.description
        assert result[0].image_url == sample_game.image_url


# ---------------------------------------------------------------------------
# Tests for save_games
# ---------------------------------------------------------------------------

class TestSaveGames:
    def test_saves_games_to_file(self, tmp_path, sample_games):
        path = str(tmp_path / "games.json")
        with patch("modules.storage.DB_HOST", None), \
             patch("modules.storage.DATA_FILE_PATH", path):
            storage.save_games(sample_games)
        with open(path, "r") as f:
            saved = json.load(f)
        assert saved == [g.to_dict() for g in sample_games]

    def test_does_not_write_when_games_is_empty(self, tmp_path):
        path = str(tmp_path / "games.json")
        with patch("modules.storage.DB_HOST", None), \
             patch("modules.storage.DATA_FILE_PATH", path):
            storage.save_games([])
        assert not os.path.exists(path)

    def test_creates_directory_if_missing(self, tmp_path, sample_games):
        sub_dir = tmp_path / "nested" / "dir"
        path = str(sub_dir / "games.json")
        with patch("modules.storage.DB_HOST", None), \
             patch("modules.storage.DATA_FILE_PATH", path):
            storage.save_games(sample_games)
        assert os.path.exists(path)

    def test_raises_io_error_on_permission_error(self, tmp_path, sample_games):
        path = str(tmp_path / "games.json")
        with patch("modules.storage.DB_HOST", None), \
             patch("modules.storage.DATA_FILE_PATH", path), \
             patch("builtins.open", side_effect=PermissionError("denied")):
            with pytest.raises(IOError):
                storage.save_games(sample_games)

    def test_raises_type_error_on_unserializable_data(self, tmp_path):
        from unittest.mock import patch as _patch
        path = str(tmp_path / "games.json")
        game = FreeGame(
            title="Test", store="epic", url="https://example.com", image_url="",
            original_price=None, end_date="", is_permanent=False, description="",
        )
        # Simulate to_dict returning an object() which is not JSON-serialisable
        unserializable = {"title": object()}
        with _patch.object(game, "to_dict", return_value=unserializable):
            games = [game]
            with patch("modules.storage.DB_HOST", None), \
                 patch("modules.storage.DATA_FILE_PATH", path):
                with pytest.raises(TypeError):
                    storage.save_games(games)

    def test_saved_file_is_valid_json(self, tmp_path, sample_games):
        path = str(tmp_path / "games.json")
        with patch("modules.storage.DB_HOST", None), \
             patch("modules.storage.DATA_FILE_PATH", path):
            storage.save_games(sample_games)
        with open(path, "r") as f:
            content = f.read()
        parsed = json.loads(content)
        assert isinstance(parsed, list)

    def test_save_then_load_round_trip(self, tmp_path, sample_games):
        path = str(tmp_path / "games.json")
        with patch("modules.storage.DB_HOST", None), \
             patch("modules.storage.DATA_FILE_PATH", path):
            storage.save_games(sample_games)
            loaded = storage.load_previous_games()
        assert loaded == sample_games


# ---------------------------------------------------------------------------
# Tests for PostgreSQL-backed storage
# ---------------------------------------------------------------------------

class TestDatabaseBackedLoadPreviousGames:
    def test_delegates_to_db_when_db_host_is_set(self, sample_games):
        mock_db = MagicMock()
        mock_db.get_games.return_value = sample_games
        with patch("modules.storage.DB_HOST", "localhost"), \
             patch("modules.database.FreeGamesDatabase", return_value=mock_db):
            result = storage.load_previous_games()
        assert result == sample_games
        mock_db.get_games.assert_called_once()

    def test_returns_empty_list_when_db_raises(self):
        mock_db = MagicMock()
        mock_db.get_games.side_effect = Exception("connection refused")
        with patch("modules.storage.DB_HOST", "localhost"), \
             patch("modules.database.FreeGamesDatabase", return_value=mock_db):
            result = storage.load_previous_games()
        assert result == []

    def test_uses_file_backend_when_db_host_not_set(self, tmp_path, sample_games):
        path = str(tmp_path / "games.json")
        with open(path, "w") as f:
            json.dump([g.to_dict() for g in sample_games], f)
        with patch("modules.storage.DB_HOST", None), \
             patch("modules.storage.DATA_FILE_PATH", path):
            result = storage.load_previous_games()
        assert result == sample_games


class TestDatabaseBackedSaveGames:
    def test_delegates_to_db_when_db_host_is_set(self, sample_games):
        mock_db = MagicMock()
        with patch("modules.storage.DB_HOST", "localhost"), \
             patch("modules.database.FreeGamesDatabase", return_value=mock_db):
            storage.save_games(sample_games)
        mock_db.save_games.assert_called_once_with(sample_games)

    def test_raises_io_error_when_db_save_fails(self, sample_games):
        mock_db = MagicMock()
        mock_db.save_games.side_effect = Exception("db write error")
        with patch("modules.storage.DB_HOST", "localhost"), \
             patch("modules.database.FreeGamesDatabase", return_value=mock_db):
            with pytest.raises(IOError):
                storage.save_games(sample_games)

    def test_does_not_call_db_save_for_empty_list(self):
        mock_db = MagicMock()
        with patch("modules.storage.DB_HOST", "localhost"), \
             patch("modules.database.FreeGamesDatabase", return_value=mock_db):
            storage.save_games([])
        mock_db.save_games.assert_not_called()

    def test_uses_file_backend_when_db_host_not_set(self, tmp_path, sample_games):
        path = str(tmp_path / "games.json")
        with patch("modules.storage.DB_HOST", None), \
             patch("modules.storage.DATA_FILE_PATH", path):
            storage.save_games(sample_games)
        with open(path, "r") as f:
            saved = json.load(f)
        assert saved == [g.to_dict() for g in sample_games]


# ---------------------------------------------------------------------------
# Tests for save_last_notification and load_last_notification
# ---------------------------------------------------------------------------

class TestSaveLastNotification:
    def test_saves_games_to_file_when_db_not_configured(self, tmp_path, sample_games):
        path = str(tmp_path / "last_notification.json")
        with patch("modules.storage.DB_HOST", None), \
             patch("modules.storage.LAST_NOTIFICATION_FILE_PATH", path):
            storage.save_last_notification(sample_games)
        with open(path, "r") as f:
            saved = json.load(f)
        assert saved == [g.to_dict() for g in sample_games]

    def test_does_not_write_when_games_is_empty(self, tmp_path):
        path = str(tmp_path / "last_notification.json")
        with patch("modules.storage.DB_HOST", None), \
             patch("modules.storage.LAST_NOTIFICATION_FILE_PATH", path):
            storage.save_last_notification([])
        assert not os.path.exists(path)

    def test_creates_directory_if_missing(self, tmp_path, sample_games):
        sub_dir = tmp_path / "nested" / "dir"
        path = str(sub_dir / "last_notification.json")
        with patch("modules.storage.DB_HOST", None), \
             patch("modules.storage.LAST_NOTIFICATION_FILE_PATH", path):
            storage.save_last_notification(sample_games)
        assert os.path.exists(path)

    def test_raises_io_error_on_file_failure(self, tmp_path, sample_games):
        path = str(tmp_path / "last_notification.json")
        with patch("modules.storage.DB_HOST", None), \
             patch("modules.storage.LAST_NOTIFICATION_FILE_PATH", path), \
             patch("builtins.open", side_effect=PermissionError("denied")):
            with pytest.raises(IOError):
                storage.save_last_notification(sample_games)

    def test_saved_file_is_valid_json(self, tmp_path, sample_games):
        path = str(tmp_path / "last_notification.json")
        with patch("modules.storage.DB_HOST", None), \
             patch("modules.storage.LAST_NOTIFICATION_FILE_PATH", path):
            storage.save_last_notification(sample_games)
        with open(path, "r") as f:
            parsed = json.loads(f.read())
        assert isinstance(parsed, list)

    def test_delegates_to_db_when_db_configured(self, sample_games):
        mock_db = MagicMock()
        with patch("modules.storage.DB_HOST", "localhost"), \
             patch("modules.database.FreeGamesDatabase", return_value=mock_db):
            storage.save_last_notification(sample_games)
        mock_db.save_last_notification.assert_called_once_with(sample_games)

    def test_raises_io_error_when_db_save_fails(self, sample_games):
        mock_db = MagicMock()
        mock_db.save_last_notification.side_effect = Exception("db write error")
        with patch("modules.storage.DB_HOST", "localhost"), \
             patch("modules.database.FreeGamesDatabase", return_value=mock_db):
            with pytest.raises(IOError):
                storage.save_last_notification(sample_games)


class TestLoadLastNotification:
    def test_returns_empty_list_when_file_not_exists(self, tmp_path):
        path = str(tmp_path / "nonexistent.json")
        with patch("modules.storage.DB_HOST", None), \
             patch("modules.storage.LAST_NOTIFICATION_FILE_PATH", path):
            result = storage.load_last_notification()
        assert result == []

    def test_loads_valid_json_file(self, tmp_path, sample_games):
        path = str(tmp_path / "last_notification.json")
        with open(path, "w") as f:
            json.dump([g.to_dict() for g in sample_games], f)
        with patch("modules.storage.DB_HOST", None), \
             patch("modules.storage.LAST_NOTIFICATION_FILE_PATH", path):
            result = storage.load_last_notification()
        assert result == sample_games

    def test_returns_empty_list_on_corrupted_json(self, tmp_path):
        path = str(tmp_path / "last_notification.json")
        with open(path, "w") as f:
            f.write("not valid json {{")
        with patch("modules.storage.DB_HOST", None), \
             patch("modules.storage.LAST_NOTIFICATION_FILE_PATH", path):
            result = storage.load_last_notification()
        assert result == []

    def test_returns_empty_list_when_data_is_not_a_list(self, tmp_path):
        path = str(tmp_path / "last_notification.json")
        with open(path, "w") as f:
            json.dump({"key": "value"}, f)
        with patch("modules.storage.DB_HOST", None), \
             patch("modules.storage.LAST_NOTIFICATION_FILE_PATH", path):
            result = storage.load_last_notification()
        assert result == []

    def test_returns_empty_list_when_items_are_not_dicts(self, tmp_path):
        path = str(tmp_path / "last_notification.json")
        with open(path, "w") as f:
            json.dump(["game1", "game2"], f)
        with patch("modules.storage.DB_HOST", None), \
             patch("modules.storage.LAST_NOTIFICATION_FILE_PATH", path):
            result = storage.load_last_notification()
        assert result == []

    def test_save_then_load_round_trip(self, tmp_path, sample_games):
        path = str(tmp_path / "last_notification.json")
        with patch("modules.storage.DB_HOST", None), \
             patch("modules.storage.LAST_NOTIFICATION_FILE_PATH", path):
            storage.save_last_notification(sample_games)
            result = storage.load_last_notification()
        assert result == sample_games

    def test_delegates_to_db_when_db_configured(self, sample_games):
        mock_db = MagicMock()
        mock_db.get_last_notification.return_value = sample_games
        with patch("modules.storage.DB_HOST", "localhost"), \
             patch("modules.database.FreeGamesDatabase", return_value=mock_db):
            result = storage.load_last_notification()
        assert result == sample_games
        mock_db.get_last_notification.assert_called_once()

    def test_returns_empty_list_when_db_raises(self):
        mock_db = MagicMock()
        mock_db.get_last_notification.side_effect = Exception("connection refused")
        with patch("modules.storage.DB_HOST", "localhost"), \
             patch("modules.database.FreeGamesDatabase", return_value=mock_db):
            result = storage.load_last_notification()
        assert result == []


# ---------------------------------------------------------------------------
# Tests for FreeGamesDatabase.get_last_notification validation
# ---------------------------------------------------------------------------

class TestFreeGamesDatabaseGetLastNotification:
    """Unit-test the validation logic inside FreeGamesDatabase.get_last_notification()."""

    def _make_db(self):
        from modules.database import FreeGamesDatabase
        db = FreeGamesDatabase.__new__(FreeGamesDatabase)
        db.conn_params = {}
        return db

    def _mock_conn(self, row):
        """Return a context-manager chain for psycopg2.connect that yields *row*."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = row
        mock_cursor.__enter__ = lambda s: s
        mock_cursor.__exit__ = MagicMock(return_value=False)

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = lambda s: s
        mock_conn.__exit__ = MagicMock(return_value=False)

        return mock_conn

    def test_returns_empty_list_when_no_row(self):
        db = self._make_db()
        mock_conn = self._mock_conn(None)
        with patch("modules.database.psycopg2.connect", return_value=mock_conn):
            result = db.get_last_notification()
        assert result == []

    def test_returns_games_for_valid_list(self, sample_games):
        db = self._make_db()
        mock_conn = self._mock_conn((json.dumps([g.to_dict() for g in sample_games]),))
        with patch("modules.database.psycopg2.connect", return_value=mock_conn):
            result = db.get_last_notification()
        assert result == sample_games

    def test_returns_empty_list_when_data_is_not_a_list(self):
        db = self._make_db()
        mock_conn = self._mock_conn((json.dumps({"key": "value"}),))
        with patch("modules.database.psycopg2.connect", return_value=mock_conn):
            result = db.get_last_notification()
        assert result == []

    def test_returns_empty_list_when_items_are_not_dicts(self):
        db = self._make_db()
        mock_conn = self._mock_conn((json.dumps(["game1", "game2"]),))
        with patch("modules.database.psycopg2.connect", return_value=mock_conn):
            result = db.get_last_notification()
        assert result == []


# ---------------------------------------------------------------------------
# Tests for FreeGamesDatabase._make_game_id
# ---------------------------------------------------------------------------

class TestMakeGameId:
    def test_normal_case(self):
        result = FreeGamesDatabase._make_game_id("epic", "https://store.epicgames.com/p/game")
        assert result == "epic:https://store.epicgames.com/p/game"

    def test_steam_prefix(self):
        result = FreeGamesDatabase._make_game_id("steam", "https://store.steampowered.com/app/1")
        assert result == "steam:https://store.steampowered.com/app/1"

    def test_raises_on_empty_url(self):
        with pytest.raises(ValueError):
            FreeGamesDatabase._make_game_id("epic", "")

    def test_raises_on_empty_store(self):
        with pytest.raises(ValueError):
            FreeGamesDatabase._make_game_id("", "https://example.com")

    def test_raises_on_both_empty(self):
        with pytest.raises(ValueError):
            FreeGamesDatabase._make_game_id("", "")


# ---------------------------------------------------------------------------
# Tests for FreeGamesDatabase.game_exists
# ---------------------------------------------------------------------------

class TestGameExists:
    def _make_db(self):
        from modules.database import FreeGamesDatabase
        db = FreeGamesDatabase.__new__(FreeGamesDatabase)
        db.conn_params = {}
        return db

    def _mock_conn(self, exists: bool):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1,) if exists else None
        mock_cursor.__enter__ = lambda s: s
        mock_cursor.__exit__ = MagicMock(return_value=False)

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = lambda s: s
        mock_conn.__exit__ = MagicMock(return_value=False)
        return mock_conn, mock_cursor

    def _get_lookup_id(self, mock_cursor):
        """Extract the game_id parameter from the SELECT execute call."""
        select_call = next(
            c for c in reversed(mock_cursor.execute.call_args_list)
            if "SELECT" in c[0][0]
        )
        return select_call[0][1][0]

    def test_plain_url_with_store_builds_prefixed_lookup(self):
        db = self._make_db()
        mock_conn, mock_cursor = self._mock_conn(True)
        with patch("modules.database.psycopg2.connect", return_value=mock_conn):
            result = db.game_exists("https://store.epicgames.com/p/game", store="epic")
        assert result is True
        assert self._get_lookup_id(mock_cursor) == "epic:https://store.epicgames.com/p/game"

    def test_already_prefixed_id_is_not_double_prefixed(self):
        db = self._make_db()
        mock_conn, mock_cursor = self._mock_conn(False)
        prefixed = "epic:https://store.epicgames.com/p/game"
        with patch("modules.database.psycopg2.connect", return_value=mock_conn):
            result = db.game_exists(prefixed, store="epic")
        assert result is False
        assert self._get_lookup_id(mock_cursor) == prefixed

    def test_no_store_passes_game_id_verbatim(self):
        db = self._make_db()
        mock_conn, mock_cursor = self._mock_conn(True)
        raw_id = "epic:https://store.epicgames.com/p/game"
        with patch("modules.database.psycopg2.connect", return_value=mock_conn):
            result = db.game_exists(raw_id)
        assert result is True
        assert self._get_lookup_id(mock_cursor) == raw_id

    def test_steam_url_with_store_builds_steam_prefix(self):
        db = self._make_db()
        mock_conn, mock_cursor = self._mock_conn(True)
        with patch("modules.database.psycopg2.connect", return_value=mock_conn):
            db.game_exists("https://store.steampowered.com/app/730", store="steam")
        assert self._get_lookup_id(mock_cursor) == "steam:https://store.steampowered.com/app/730"

    def test_returns_false_when_game_not_found(self):
        db = self._make_db()
        mock_conn, _ = self._mock_conn(False)
        with patch("modules.database.psycopg2.connect", return_value=mock_conn):
            result = db.game_exists("epic:https://example.com")
        assert result is False
