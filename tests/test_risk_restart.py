import os
from pathlib import Path
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from risk.manager import RiskManager


class RiskRestartTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_cwd = os.getcwd()
        os.chdir(self.temp_dir.name)

    def tearDown(self):
        os.chdir(self.old_cwd)
        self.temp_dir.cleanup()

    def test_same_day_restart_preserves_baseline_and_loss_breach(self):
        first = RiskManager(initial_balance=100_000, max_daily_loss_pct=0.05)
        first.sync_day_start_balance(100_000)
        allowed, _ = first.can_trade(94_000)
        self.assertFalse(allowed)

        restarted = RiskManager(initial_balance=94_000, max_daily_loss_pct=0.05)
        restarted.sync_day_start_balance(94_000)
        self.assertEqual(restarted.get_status()["day_start_balance"], 100_000)
        self.assertTrue(restarted.get_status()["daily_loss_breached"])
        self.assertFalse(restarted.can_trade(100_000)[0])

    def test_first_start_syncs_broker_equity_as_daily_baseline(self):
        manager = RiskManager(initial_balance=100_000)
        manager.sync_day_start_balance(99_250)
        self.assertEqual(manager.get_status()["day_start_balance"], 99_250)

    def test_mid_cooldown_restart_uses_aware_clock(self):
        manager=RiskManager(initial_balance=100_000)
        manager.sync_day_start_balance(100_000)
        manager._cooldown_until=datetime.now(timezone.utc)+timedelta(minutes=5)
        manager._save_state()
        restarted=RiskManager(initial_balance=100_000)
        restarted.sync_day_start_balance(100_000)
        self.assertFalse(restarted.can_trade(100_000)[0])
        self.assertTrue(restarted.get_status()['cooldown_active'])


if __name__ == "__main__":
    unittest.main()
