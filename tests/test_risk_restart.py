import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
from risk.manager import RiskManager
from risk.startup import initialize_live_risk

class RestartTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.patch=patch.object(RiskManager,'_state_filepath',return_value=self.temp.name+'/risk.json')
        self.patch.start(); self.addCleanup(self.patch.stop)
        self.now=datetime(2026,11,2,15,tzinfo=timezone.utc)
    def start(self,manager,now=None):
        clock=SimpleNamespace(timestamp=now or self.now)
        initialize_live_risk(manager,SimpleNamespace(get_clock=lambda:clock),{'last_equity':100000})
    def ready(self):
        manager=RiskManager(100000)
        self.start(manager,self.now-timedelta(days=1))
        self.start(manager)
        return manager
    def test_real_startup_preserves_breach_and_baseline(self):
        manager=self.ready()
        self.assertFalse(manager.can_trade(94000,as_of=self.now)[0])
        restored=RiskManager(94000); self.start(restored)
        self.assertEqual(restored._day_start_balance,100000)
        self.assertFalse(restored.can_trade(99000,as_of=self.now)[0])
    def test_mid_cooldown_restart(self):
        manager=self.ready()
        manager.check_stop_loss(100,90,as_of=self.now)
        restored=RiskManager(100000); self.start(restored)
        self.assertFalse(restored.can_trade(100000,as_of=self.now+timedelta(minutes=1))[0])
    def test_missing_and_corrupt_state_block_entries(self):
        for content in (None,'broken'):
            if content:
                with open(self.temp.name+'/risk.json','w') as f: f.write(content)
            manager=RiskManager(100000); self.start(manager)
            self.assertFalse(manager.entries_ready)
    def test_next_ny_date_resets_only_once(self):
        manager=self.ready()
        manager.can_trade(94000,as_of=self.now)
        self.start(manager,self.now+timedelta(days=1))
        self.assertTrue(manager.entries_ready)
        self.assertFalse(manager._daily_loss_breached)
    def test_write_failure_blocks_entries(self):
        manager=self.ready()
        with patch('risk.manager.os.replace',side_effect=OSError): manager._save_state()
        self.assertFalse(manager.entries_ready)

class DailyEvidenceTests(unittest.TestCase):
    def test_unknown_and_valid_trends(self):
        import pandas as pd
        from strategy.data_quality import daily_trend
        self.assertIsNone(daily_trend(None))
        self.assertIsNone(daily_trend(pd.DataFrame({'Close':[100]*19})))
        self.assertIsNone(daily_trend(pd.DataFrame({'Close':[100]*19+[float('nan')]})))
        self.assertTrue(daily_trend(pd.DataFrame({'Close':range(1,21)})))
        self.assertFalse(daily_trend(pd.DataFrame({'Close':range(20,0,-1)})))
