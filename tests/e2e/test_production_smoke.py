import os

import httpx
import pytest

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
API_KEY = os.getenv("API_KEY")
HEADERS = {"X-API-Key": API_KEY} if API_KEY else {}
DB_HOST = os.getenv("DB_HOST") or None

@pytest.mark.production
def test_health_check():
    response = httpx.get(f"{API_BASE_URL}/health", headers=HEADERS, timeout=10)
    assert response.status_code == 200
    assert response.json().get("status") == "healthy"
    assert response.json().get("epic_games_api") == "healthy"
    if DB_HOST:
        assert response.json().get("database") == "healthy"

@pytest.mark.production
def test_games_latest():
    response = httpx.get(f"{API_BASE_URL}/games/latest", headers=HEADERS, timeout=10)
    assert response.status_code == 200
    data = response.json()
    assert data.get("count", 0) >= 0
    assert isinstance(data.get("games"), list)
    if data.get("games"):
        game = data["games"][0]
        assert "title" in game
        assert "link" in game
        assert "end_date" in game
        assert "description" in game
        assert "thumbnail" in game

@pytest.mark.production
def test_games_history():
    response = httpx.get(f"{API_BASE_URL}/games/history", headers=HEADERS, timeout=10)
    assert response.status_code == 200
    data = response.json()
    assert "games" in data
    assert "total" in data
    assert "limit" in data
    assert "offset" in data
    assert isinstance(data["games"], list)
    assert isinstance(data["total"], int)
    assert isinstance(data["limit"], int)
    assert isinstance(data["offset"], int)
    assert data["total"] >= 0
    assert data["limit"] >= 0
    assert data["offset"] >= 0
    assert len(data["games"]) <= data["limit"]
    assert data["total"] >= len(data["games"])
    if data["games"]:
        game = data["games"][0]
        assert "title" in game
        assert "link" in game
        assert "end_date" in game
        assert "description" in game
        assert "thumbnail" in game

@pytest.mark.production
def test_config():
    response = httpx.get(f"{API_BASE_URL}/config", headers=HEADERS, timeout=10)
    assert response.status_code == 200
    data = response.json()
    assert "epic_games_region" in data
    assert "timezone" in data
    assert "locale" in data
    assert "schedule_time" in data
    assert "date_format" in data

@pytest.mark.production
def test_check():
    test_webhook_url = os.getenv("TEST_WEBHOOK_URL")
    if not test_webhook_url:
        pytest.skip("TEST_WEBHOOK_URL must be set for production smoke test_check to avoid using the default webhook")

    response = httpx.post(
        f"{API_BASE_URL}/check",
        headers=HEADERS,
        json={"webhook_url": test_webhook_url},
        timeout=10,
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("games_fetched", 0) > 0
    notification_status = data.get("notification_status")
    assert isinstance(notification_status, str)
    assert notification_status.startswith("sent") or notification_status.startswith("failed:")
