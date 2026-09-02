from unittest.mock import MagicMock, patch

import requests as requests_lib

from modules import healthcheck as healthcheck_module

PUSH_TOKEN = "faketesttoken-not-a-real-secret"
HEALTHCHECK_URL = f"https://uptime.example.com:443/api/push/{PUSH_TOKEN}"


def _make_response(status_code=200, ok_value=True):
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = {"ok": ok_value}
    return mock_resp


class TestSafeMonitorLocation:
    def test_extracts_host_and_port_without_path_or_token(self):
        location = healthcheck_module._safe_monitor_location(HEALTHCHECK_URL)
        assert location == "uptime.example.com:443"
        assert PUSH_TOKEN not in location

    def test_extracts_host_only_when_no_explicit_port(self):
        location = healthcheck_module._safe_monitor_location(f"https://uptime.example.com/api/push/{PUSH_TOKEN}")
        assert location == "uptime.example.com"
        assert PUSH_TOKEN not in location

    def test_returns_placeholder_for_unconfigured_url(self):
        assert healthcheck_module._safe_monitor_location(None) == "unconfigured-monitor"
        assert healthcheck_module._safe_monitor_location("") == "unconfigured-monitor"


class TestHealthcheckDisabled:
    def test_does_nothing_when_disabled(self):
        with patch("modules.healthcheck.ENABLE_HEALTHCHECK", False), \
             patch("modules.healthcheck.requests.get") as mock_get:
            healthcheck_module.healthcheck()

        mock_get.assert_not_called()


class TestHealthcheckHappyPath:
    def test_sends_get_request_to_monitor_url(self):
        with patch("modules.healthcheck.ENABLE_HEALTHCHECK", True), \
             patch("modules.healthcheck.HEALTHCHECK_URL", HEALTHCHECK_URL), \
             patch("modules.healthcheck.requests.get") as mock_get:
            mock_get.return_value = _make_response()
            healthcheck_module.healthcheck()

        args, kwargs = mock_get.call_args
        assert args[0] == HEALTHCHECK_URL
        assert kwargs["timeout"] == healthcheck_module.HEARTBEAT_TIMEOUT

    def test_logs_error_when_status_code_is_not_200(self, caplog):
        with patch("modules.healthcheck.ENABLE_HEALTHCHECK", True), \
             patch("modules.healthcheck.HEALTHCHECK_URL", HEALTHCHECK_URL), \
             patch("modules.healthcheck.requests.get") as mock_get, \
             caplog.at_level("ERROR"):
            mock_get.return_value = _make_response(status_code=500)
            healthcheck_module.healthcheck()

        assert "Unexpected response from monitor at uptime.example.com:443" in caplog.text


class TestHealthcheckFailuresAreSwallowed:
    """A failed heartbeat push must never raise: it should be logged and swallowed."""

    def test_connection_error_does_not_raise(self, caplog):
        with patch("modules.healthcheck.ENABLE_HEALTHCHECK", True), \
             patch("modules.healthcheck.HEALTHCHECK_URL", HEALTHCHECK_URL), \
             patch(
                 "modules.healthcheck.requests.get",
                 side_effect=requests_lib.exceptions.ConnectionError("monitor unreachable"),
             ), \
             caplog.at_level("ERROR"):
            healthcheck_module.healthcheck()  # must not raise

        assert "Failed to push heartbeat to uptime.example.com:443: ConnectionError" in caplog.text

    def test_timeout_does_not_raise(self, caplog):
        with patch("modules.healthcheck.ENABLE_HEALTHCHECK", True), \
             patch("modules.healthcheck.HEALTHCHECK_URL", HEALTHCHECK_URL), \
             patch(
                 "modules.healthcheck.requests.get",
                 side_effect=requests_lib.exceptions.Timeout(),
             ), \
             caplog.at_level("ERROR"):
            healthcheck_module.healthcheck()  # must not raise

        assert "Failed to push heartbeat to uptime.example.com:443: Timeout" in caplog.text

    def test_malformed_json_response_does_not_raise(self, caplog):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = ValueError("not JSON")
        with patch("modules.healthcheck.ENABLE_HEALTHCHECK", True), \
             patch("modules.healthcheck.HEALTHCHECK_URL", HEALTHCHECK_URL), \
             patch("modules.healthcheck.requests.get", return_value=mock_resp), \
             caplog.at_level("ERROR"):
            healthcheck_module.healthcheck()  # must not raise

        assert "Failed to push heartbeat to uptime.example.com:443: ValueError" in caplog.text


class TestHealthcheckNeverLeaksTheToken:
    """The push token lives in the URL path; no log line, at any level, may contain it."""

    def test_no_leak_when_exception_message_embeds_the_full_url(self, caplog):
        # This mirrors what requests/urllib3 actually do: embed the request URL
        # (token included) in the exception's own string representation.
        exc = requests_lib.exceptions.ConnectionError(
            f"HTTPSConnectionPool(host='uptime.example.com', port=443): "
            f"Max retries exceeded with url: /api/push/{PUSH_TOKEN}?status=up (Caused by ...)"
        )
        with patch("modules.healthcheck.ENABLE_HEALTHCHECK", True), \
             patch("modules.healthcheck.HEALTHCHECK_URL", HEALTHCHECK_URL), \
             patch("modules.healthcheck.requests.get", side_effect=exc), \
             caplog.at_level("DEBUG"):
            healthcheck_module.healthcheck()

        assert PUSH_TOKEN not in caplog.text

    def test_no_leak_at_debug_level_on_success(self, caplog):
        with patch("modules.healthcheck.ENABLE_HEALTHCHECK", True), \
             patch("modules.healthcheck.HEALTHCHECK_URL", HEALTHCHECK_URL), \
             patch("modules.healthcheck.requests.get", return_value=_make_response()), \
             caplog.at_level("DEBUG"):
            healthcheck_module.healthcheck()

        assert PUSH_TOKEN not in caplog.text

    def test_no_leak_on_non_200_response(self, caplog):
        with patch("modules.healthcheck.ENABLE_HEALTHCHECK", True), \
             patch("modules.healthcheck.HEALTHCHECK_URL", HEALTHCHECK_URL), \
             patch("modules.healthcheck.requests.get", return_value=_make_response(status_code=500)), \
             caplog.at_level("DEBUG"):
            healthcheck_module.healthcheck()

        assert PUSH_TOKEN not in caplog.text
