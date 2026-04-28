"""Integration tests for the API running in Docker container.

These tests verify that the config endpoint returns values matching the environment
by running a Python one-liner (`python -c`) inside the container via `docker compose exec`.
This works regardless of whether ports are exposed and mirrors how services inside a cluster communicate.

Both sources are independent:
  - Expected: values from the .env file (loaded on the host by the test)
  - Actual: values returned by the container's /config endpoint

To run:
    docker compose up -d
    pytest tests/test_api_integration.py -v
"""

import json
import os
import subprocess

import pytest
from dotenv import load_dotenv

_COMPOSE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Load environment variables from .env file (same as what compose.yaml uses)
load_dotenv(dotenv_path=os.path.join(_COMPOSE_DIR, ".env"))

CONTAINER_NAME = "free-games-notifier"


def get_json(path):
    """Fetch an API endpoint by running a Python one-liner inside the container."""
    port = int(os.getenv("API_PORT", 8000))
    script = (
        "import urllib.request, json, os; "
        f"req = urllib.request.Request('http://localhost:{port}{path}'); "
        "api_key = os.getenv('API_KEY', ''); "
        "api_key and req.add_header('X-API-Key', api_key); "
        "res = urllib.request.urlopen(req); "
        "print(json.dumps(json.loads(res.read())))"
    )
    try:
        result = subprocess.run(
            [
                "docker", "compose", "exec", "-T",
                CONTAINER_NAME,
                "python", "-c", script,
            ],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=_COMPOSE_DIR,
        )
    except FileNotFoundError as exc:
        pytest.skip(
            f"'docker' command not found: {exc}. "
            "Skipping integration tests that require Docker/Compose."
        )

    if result.returncode != 0:
        pytest.fail(
            "Failed to reach API inside container. "
            "Ensure Docker Compose services are up and the API is running.\n"
            f"stderr: {result.stderr.strip() or '<empty>'}\n"
            f"stdout: {result.stdout.strip() or '<empty>'}"
        )
    return json.loads(result.stdout)


@pytest.mark.integration
class TestHealthEndpoint:
    """Verify /health endpoint returns healthy status."""

    def test_health_endpoint(self):
        """Verify /health returns healthy status."""
        resp_json = get_json("/health")

        assert resp_json["status"] == "healthy", f"Expected status 'healthy' but got '{resp_json['status']}'"
        # Do not require the external Epic Games API to be healthy to avoid flaky tests.
        # Instead, verify that the field exists and has a string status.
        assert "epic_games_api" in resp_json, "Expected 'epic_games_api' field in health response"
        assert isinstance(resp_json["epic_games_api"], str), \
            f"Expected epic_games_api to be a string but got {type(resp_json['epic_games_api'])!r}"
        db_host = os.getenv("DB_HOST")
        if db_host:
            assert resp_json["database"] == "healthy", f"Expected database 'healthy' but got '{resp_json['database']}'"


@pytest.mark.integration
class TestConfigEndpointMatchesEnv:
    """Verify /config endpoint returns values matching environment variables."""

    def test_date_format_matches_env(self):
        """Verify DATE_FORMAT in /config matches the env variable."""
        expected_date_format = os.getenv("DATE_FORMAT", "%B %d, %Y at %I:%M %p")

        config = get_json("/config")

        assert config["date_format"] == expected_date_format, \
            f"Expected DATE_FORMAT '{expected_date_format}' but got '{config['date_format']}'"

    def test_timezone_matches_env(self):
        """Verify TIMEZONE in /config matches the resolved config value.

        TIMEZONE may be derived from REGION rather than set explicitly, so we
        compare against the already-resolved config.TIMEZONE instead of a raw
        os.getenv() call.
        """
        from config import TIMEZONE as expected_timezone

        config = get_json("/config")

        assert config["timezone"] == expected_timezone, \
            f"Expected TIMEZONE '{expected_timezone}' but got '{config['timezone']}'"

    def test_locale_matches_env(self):
        """Verify LOCALE in /config matches the resolved config value."""
        from config import LOCALE as expected_locale

        config = get_json("/config")

        assert config["locale"] == expected_locale, \
            f"Expected LOCALE '{expected_locale}' but got '{config['locale']}'"

    def test_schedule_time_matches_env(self):
        """Verify SCHEDULE_TIME in /config matches the env variable."""
        expected_schedule = os.getenv("SCHEDULE_TIME", "12:00")

        config = get_json("/config")

        assert config["schedule_time"] == expected_schedule, \
            f"Expected SCHEDULE_TIME '{expected_schedule}' but got '{config['schedule_time']}'"

    def test_epic_games_region_matches_env(self):
        """Verify EPIC_GAMES_REGION in /config matches the resolved config value."""
        from config import EPIC_GAMES_REGION as expected_region

        config = get_json("/config")

        assert config["epic_games_region"] == expected_region, \
            f"Expected EPIC_GAMES_REGION '{expected_region}' but got '{config['epic_games_region']}'"
