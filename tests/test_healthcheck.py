from unittest.mock import MagicMock, patch

import requests as requests_lib

from modules import healthcheck as healthcheck_module

HEALTHCHECK_URL = "https://uptime.example.com/api/push/abc123"


def _make_response(status_code=200, ok_value=True):
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = {"ok": ok_value}
    return mock_resp


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

        assert "Failed to get response from monitor" in caplog.text


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

        assert "Failed to push heartbeat to monitor" in caplog.text

    def test_timeout_does_not_raise(self, caplog):
        with patch("modules.healthcheck.ENABLE_HEALTHCHECK", True), \
             patch("modules.healthcheck.HEALTHCHECK_URL", HEALTHCHECK_URL), \
             patch(
                 "modules.healthcheck.requests.get",
                 side_effect=requests_lib.exceptions.Timeout(),
             ), \
             caplog.at_level("ERROR"):
            healthcheck_module.healthcheck()  # must not raise

        assert "Failed to push heartbeat to monitor" in caplog.text

    def test_malformed_json_response_does_not_raise(self, caplog):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = ValueError("not JSON")
        with patch("modules.healthcheck.ENABLE_HEALTHCHECK", True), \
             patch("modules.healthcheck.HEALTHCHECK_URL", HEALTHCHECK_URL), \
             patch("modules.healthcheck.requests.get", return_value=mock_resp), \
             caplog.at_level("ERROR"):
            healthcheck_module.healthcheck()  # must not raise

        assert "Failed to push heartbeat to monitor" in caplog.text
