from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from main import _has_sufficient_trading_time, _should_allow_new_entries


class LiveClockGateTests(unittest.TestCase):
    def clock(self, *, is_open=True, minutes_to_close=120):
        return SimpleNamespace(
            is_open=is_open,
            next_close=datetime.now(timezone.utc) + timedelta(minutes=minutes_to_close),
        )

    def test_session_start_gate_uses_broker_close_and_open_state(self):
        self.assertTrue(_has_sufficient_trading_time(0.25, self.clock(minutes_to_close=30)))
        self.assertFalse(_has_sufficient_trading_time(0.25, self.clock(minutes_to_close=10)))
        self.assertFalse(_has_sufficient_trading_time(0.25, self.clock(is_open=False)))
        self.assertFalse(_has_sufficient_trading_time(0.25, None))

    def test_entry_gate_uses_broker_close_time_and_fails_closed(self):
        self.assertTrue(_should_allow_new_entries(1.5, self.clock(minutes_to_close=120)))
        self.assertFalse(_should_allow_new_entries(1.5, self.clock(minutes_to_close=60)))
        self.assertFalse(_should_allow_new_entries(1.5, self.clock(is_open=False)))
        self.assertFalse(_should_allow_new_entries(1.5, None))


if __name__ == "__main__":
    unittest.main()
