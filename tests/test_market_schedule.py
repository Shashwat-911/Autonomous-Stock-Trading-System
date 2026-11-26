import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.market_schedule import (
    market_is_open,
    seconds_until_next_check,
    session_date_tag,
    should_keep_service_awake,
)


class MarketScheduleTests(unittest.TestCase):
    def test_unknown_clock_fails_closed(self):
        self.assertFalse(market_is_open(None))

    def test_market_status_comes_from_broker_clock(self):
        self.assertTrue(market_is_open(SimpleNamespace(is_open=True)))
        self.assertFalse(market_is_open(SimpleNamespace(is_open=False)))

    def test_opening_poll_frequency_tightens_near_next_open(self):
        now = datetime(2026, 11, 27, 14, 0, tzinfo=timezone.utc)
        clock = SimpleNamespace(next_open=now + timedelta(minutes=10))
        self.assertEqual(seconds_until_next_check(clock, now), 60)

    def test_session_date_uses_new_york_date_across_utc_midnight(self):
        now = datetime(2026, 11, 27, 2, 0, tzinfo=timezone.utc)
        self.assertEqual(session_date_tag(now), "2026_11_26")

    def test_keepalive_window_excludes_weekends_and_overnight(self):
        saturday = datetime(2026, 11, 28, 15, 0, tzinfo=timezone.utc)
        monday_overnight = datetime(2026, 11, 30, 11, 0, tzinfo=timezone.utc)
        monday_workday = datetime(2026, 11, 30, 14, 0, tzinfo=timezone.utc)
        self.assertFalse(should_keep_service_awake(saturday))
        self.assertFalse(should_keep_service_awake(monday_overnight))
        self.assertTrue(should_keep_service_awake(monday_workday))


if __name__ == "__main__":
    unittest.main()
