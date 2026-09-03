"""In-memory scheduler state shared between main.py and the REST API.

Process-wide and non-persistent (resets on restart), same as api/metrics.py's
counters. Lives in modules/ rather than api/ so main.py's scheduler doesn't
have to depend on the API package to record its own state.
"""

import threading
import time
from typing import Optional

_lock = threading.Lock()
_last_check_completed_at: Optional[float] = None


def record_check_completed() -> None:
    """Mark that a scheduled check just finished running to completion."""
    global _last_check_completed_at
    with _lock:
        _last_check_completed_at = time.time()


def get_last_check_completed_at() -> Optional[float]:
    """Return the Unix timestamp of the last completed check, or None if none has run yet."""
    with _lock:
        return _last_check_completed_at
