"""Process-wide metrics state for the REST API.

These counters are read by the ``/metrics`` endpoint and incremented from
several routes. The lock makes ``increment_metric`` thread-safe so the API
server thread and the scheduler thread can both update counters concurrently.
"""

import threading
import time

_start_time = time.time()
_metrics = {
    "games_processed": 0,
    "discord_notifications_sent": 0,
    "discord_notification_errors": 0,
    "errors": 0,
}
_metrics_lock = threading.Lock()


def increment_metric(key: str, amount: int = 1) -> None:
    """Safely increment a metric counter. Unknown keys are silently ignored."""
    with _metrics_lock:
        if key in _metrics:
            _metrics[key] += amount


def get_uptime_seconds() -> float:
    """Return the number of seconds since the API server started."""
    return time.time() - _start_time


def snapshot() -> dict:
    """Return a thread-safe copy of the current metric counters."""
    with _metrics_lock:
        return dict(_metrics)
