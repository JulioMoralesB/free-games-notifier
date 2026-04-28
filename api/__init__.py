"""Free Games Notifier REST API package.

This package replaces the previous monolithic ``api.py`` module. The public
surface is preserved so existing callers (``main.py``, tests) keep working:

    from api import app, _metrics, increment_metric

Internally, code is split by concern:

    api.app          — FastAPI() instance + dashboard mount
    api.auth         — API key dependency
    api.schemas      — Pydantic request/response models
    api.serializers  — FreeGame ↔ DTO conversion helpers
    api.metrics      — Process-wide counter state
    api.routes.*     — One module per logical endpoint group
"""

from api.app import app
from api.metrics import _metrics, increment_metric

__all__ = ["app", "_metrics", "increment_metric"]
