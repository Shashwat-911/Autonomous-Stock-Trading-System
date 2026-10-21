from datetime import datetime
import unittest
from scripts.session_timing import assess_session


class TimingTests(unittest.TestCase):
    def phase(self, now, day, opening="09:30", closing="16:00"):
        return assess_session(datetime.fromisoformat(now), [{"date":day,"open":opening,"close":closing}])["status"]

    def test_dst_opening_and_cutoff(self):
        self.assertEqual(self.phase("2026-10-21T13:29:00+00:00","2026-10-21"),"PREOPEN")
        self.assertEqual(self.phase("2026-10-21T13:30:00+00:00","2026-10-21"),"READY")
        self.assertEqual(self.phase("2026-10-21T18:04:00+00:00","2026-10-21"),"LATE_START")
        self.assertEqual(self.phase("2026-11-02T13:30:00+00:00","2026-11-02"),"PREOPEN")
        self.assertEqual(self.phase("2026-11-02T14:30:00+00:00","2026-11-02"),"READY")

    def test_early_close_holiday_and_naive_timestamp(self):
        self.assertEqual(self.phase("2026-11-27T18:00:00+00:00","2026-11-27",closing="13:00"),"CLOSED")
        self.assertEqual(assess_session(datetime.fromisoformat("2026-12-25T15:00:00+00:00"),[])["status"],"NON_TRADING_DAY")
        with self.assertRaises(ValueError):
            assess_session(datetime(2026,10,21),[])
