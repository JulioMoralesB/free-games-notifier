import logging
import logging.handlers
from unittest.mock import patch

from modules.logging_config import setup_logging


class TestSetupLoggingFileOptIn:
    """File logging duplicates data already collected from stdout, so it must
    stay off unless explicitly requested (see issue #190)."""

    def test_file_logging_disabled_by_default(self, tmp_path):
        log_file = tmp_path / "notifier.log"
        fresh_root = logging.Logger("test-root-default")
        with patch("modules.logging_config.logging.getLogger", return_value=fresh_root):
            setup_logging(log_file=str(log_file))

        assert len(fresh_root.handlers) == 1
        assert isinstance(fresh_root.handlers[0], logging.StreamHandler)
        assert not log_file.exists()

        for handler in fresh_root.handlers:
            handler.close()

    def test_file_logging_enabled_when_requested(self, tmp_path):
        log_file = tmp_path / "notifier.log"
        fresh_root = logging.Logger("test-root-enabled")
        with patch("modules.logging_config.logging.getLogger", return_value=fresh_root):
            setup_logging(log_file=str(log_file), log_to_file=True)

        assert len(fresh_root.handlers) == 2
        assert log_file.exists()

        for handler in fresh_root.handlers:
            handler.close()

    def test_stdout_handler_unaffected_by_file_toggle(self, tmp_path):
        """Both modes get the same console handler, at the same level."""
        fresh_root_off = logging.Logger("test-root-stdout-off")
        fresh_root_on = logging.Logger("test-root-stdout-on")
        with patch("modules.logging_config.logging.getLogger", return_value=fresh_root_off):
            setup_logging(log_file=str(tmp_path / "a.log"), log_to_file=False)
        with patch("modules.logging_config.logging.getLogger", return_value=fresh_root_on):
            setup_logging(log_file=str(tmp_path / "b.log"), log_to_file=True)

        console_off = fresh_root_off.handlers[0]
        console_on = next(h for h in fresh_root_on.handlers if isinstance(h, logging.StreamHandler)
                           and not isinstance(h, logging.handlers.TimedRotatingFileHandler))
        assert console_off.level == console_on.level == logging.INFO

        for handler in [*fresh_root_off.handlers, *fresh_root_on.handlers]:
            handler.close()

    def test_does_not_add_handlers_when_already_configured(self, tmp_path):
        """Existing handlers (e.g. pytest's own capture) must not be duplicated."""
        fresh_root = logging.Logger("test-root-preconfigured")
        fresh_root.addHandler(logging.NullHandler())
        with patch("modules.logging_config.logging.getLogger", return_value=fresh_root):
            setup_logging(log_file=str(tmp_path / "notifier.log"), log_to_file=True)

        assert len(fresh_root.handlers) == 1
