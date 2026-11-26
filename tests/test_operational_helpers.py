import io
import json
from pathlib import Path
import sys
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.check_trading_day import is_trading_day
from scripts.fetch_render_session_log import SessionLogParser
from scripts.report_schedule import resolve_report_window


class OperationalHelperTests(unittest.TestCase):
    def test_calendar_lookup_uses_only_paper_host_and_parses_session(self):
        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                self.close()

        with patch("config.ALPACA", {
            "api_key": "test-key",
            "secret_key": "test-secret",
            "base_url": "https://paper-api.alpaca.markets/v2",
        }), patch(
            "urllib.request.urlopen",
            return_value=Response(json.dumps([{"date": "2026-11-27"}]).encode()),
        ) as urlopen:
            self.assertTrue(is_trading_day("2026-11-27"))
            self.assertIn("/v2/calendar?", urlopen.call_args.args[0].full_url)

        with patch("config.ALPACA", {
            "api_key": "test-key",
            "secret_key": "test-secret",
            "base_url": "https://paper-api.alpaca.markets.attacker.invalid/v2",
        }), self.assertRaises(RuntimeError):
            is_trading_day("2026-11-27")

    def test_log_parser_extracts_unescaped_session_text(self):
        parser = SessionLogParser()
        parser.feed('<div class="log-content">LIVE PAPER TRADING &amp; logs</div>')
        self.assertEqual("".join(parser.parts), "LIVE PAPER TRADING & logs")

    def test_report_cron_selects_one_seventeen_hundred_slot_across_dst(self):
        summer_slot = datetime(2026, 7, 1, 21, 35, tzinfo=timezone.utc)
        summer_other_slot = datetime(2026, 7, 1, 22, 35, tzinfo=timezone.utc)
        winter_other_slot = datetime(2026, 12, 2, 21, 35, tzinfo=timezone.utc)
        winter_slot = datetime(2026, 12, 2, 22, 35, tzinfo=timezone.utc)
        self.assertTrue(resolve_report_window(summer_slot, "schedule", "30 21 * * 1-5")[1])
        self.assertFalse(resolve_report_window(summer_other_slot, "schedule", "30 22 * * 1-5")[1])
        self.assertFalse(resolve_report_window(winter_other_slot, "schedule", "30 21 * * 1-5")[1])
        self.assertTrue(resolve_report_window(winter_slot, "schedule", "30 22 * * 1-5")[1])


if __name__ == "__main__":
    unittest.main()
