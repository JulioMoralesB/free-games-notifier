"""API key authentication dependency for protected endpoints."""

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from config import API_KEY

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
