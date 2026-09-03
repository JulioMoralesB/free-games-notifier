from unittest.mock import patch

from modules import scheduler_state


class TestSchedulerState:
    def test_returns_none_before_any_check_completes(self):
        with patch("modules.scheduler_state._last_check_completed_at", None):
            assert scheduler_state.get_last_check_completed_at() is None

    def test_record_check_completed_sets_a_timestamp(self):
        with patch("modules.scheduler_state._last_check_completed_at", None), \
             patch("modules.scheduler_state.time.time", return_value=1893456000.0):
            scheduler_state.record_check_completed()
            assert scheduler_state.get_last_check_completed_at() == 1893456000.0

    def test_record_check_completed_overwrites_the_previous_value(self):
        with patch("modules.scheduler_state._last_check_completed_at", None):
            with patch("modules.scheduler_state.time.time", return_value=100.0):
                scheduler_state.record_check_completed()
            with patch("modules.scheduler_state.time.time", return_value=200.0):
                scheduler_state.record_check_completed()
            assert scheduler_state.get_last_check_completed_at() == 200.0
