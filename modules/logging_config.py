"""
Structured JSON logging configuration for Free Games Notifier.

All log entries are emitted as single-line JSON objects with consistent fields:
  - timestamp  : ISO 8601 with timezone offset (e.g. "2026-04-28T10:00:00-06:00")
  - level      : log level string (INFO, WARNING, ERROR, DEBUG)
  - logger     : logger name (e.g. "modules.notifier", "__main__")
  - message    : the log message
  - service    : always "free-games-notifier" — useful as a Loki label

Promtail pipeline_stages example:
  - json:
      expressions:
        level: level
        message: message
        service: service
  - labels:
      level:
      service:
"""

import logging
import logging.handlers
from datetime import datetime

import pytz
try:
    from pythonjsonlogger.json import JsonFormatter as _JsonFormatterBase  # v3+
except ImportError:
    from pythonjsonlogger.jsonlogger import JsonFormatter as _JsonFormatterBase  # v2

SERVICE_NAME = "free-games-notifier"


class _JsonFormatter(_JsonFormatterBase):
    """JsonFormatter that adds standard fields and a timezone-aware timestamp."""

    def __init__(self, *args, tz: str = "UTC", **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self._tz = pytz.timezone(tz)
        except pytz.exceptions.UnknownTimeZoneError:
            logging.getLogger(__name__).warning(
                "Unknown timezone %r for log formatter — falling back to UTC.", tz
            )
            self._tz = pytz.utc

    def add_fields(self, log_record: dict, record: logging.LogRecord, message_dict: dict):
        super().add_fields(log_record, record, message_dict)

        # Timezone-aware ISO 8601 timestamp
        log_record["timestamp"] = (
            datetime.fromtimestamp(record.created, tz=pytz.utc)
            .astimezone(self._tz)
            .isoformat()
        )
        log_record["level"] = record.levelname
        log_record["logger"] = record.name
        log_record["service"] = SERVICE_NAME

        # Remove redundant / noisy fields added by the base formatter
        for key in ("asctime", "name", "levelname"):
            log_record.pop(key, None)


def setup_logging(timezone: str = "UTC", log_file: str = "/mnt/logs/notifier.log") -> None:
    """
    Configure JSON structured logging for the application.

    Should be called once at startup before any loggers are used.
    Both the rotating file and stdout receive the same JSON format.

    Args:
        timezone: IANA timezone string for log timestamps (e.g. "America/Mexico_City").
        log_file: Absolute path to the rotating log file.
    """
    formatter = _JsonFormatter(fmt="%(message)s", tz=timezone)

    file_handler = logging.handlers.TimedRotatingFileHandler(
        log_file, when="W1", interval=1, backupCount=4
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # Only add handlers if none are configured yet (same behaviour as basicConfig without force).
    # This prevents overriding pytest's log capture during test runs.
    if not root.handlers:
        root.addHandler(file_handler)
        root.addHandler(console_handler)
