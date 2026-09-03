"""API key authentication dependencies for protected endpoints."""

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from config import API_KEY, DASHBOARD_API_KEY

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str = Security(_api_key_header)) -> None:
    """Validate the API key for mutating endpoints and sensitive read endpoints.

    Used by both state-changing (POST) endpoints and sensitive GET endpoints
    such as ``/config``.  When ``API_KEY`` is not set the check is skipped so
    that local / development deployments work out-of-the-box without auth.
    """
    if not API_KEY:
        return
    if api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


async def verify_dashboard_key(api_key: str = Security(_api_key_header)) -> None:
    """Validate the shared secret for GET /api/summary.

    Unlike verify_api_key, this has no "skip when unset" fallback: the
    endpoint is an external contract for another service to poll, so it must
    always require a configured secret, even when API_KEY itself is unset.
    """
    if not DASHBOARD_API_KEY or api_key != DASHBOARD_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
