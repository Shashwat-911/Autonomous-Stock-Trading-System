"""Offline integration checks for indicators, risk and local paper accounting."""
import logging
import tempfile
import unittest
from unittest.mock import patch, Mock
import numpy as np
import pandas as pd
from risk.manager import RiskManager
from strategy.indicators import add_all_indicators


class CoreOfflineTests(unittest.TestCase):
    def test_indicator_prefix_is_not_changed_by_future_bars(self):
        close = 100 + np.arange(120)*.1 + np.sin(np.arange(120))
        bars = pd.DataFrame({"Open":close-.1, "High":close+1, "Low":close-1,
                             "Close":close, "Volume":1000}, index=pd.date_range("2026-01-01", periods=120))
        full = add_all_indicators(bars)
        prefix = add_all_indicators(bars.iloc[:90])
        pd.testing.assert_frame_equal(full.iloc[:90], prefix)
        self.assertTrue(np.isfinite(full.iloc[-1][["RSI_14","MACD","ATR_14","ADX_14"]].to_numpy(dtype=float)).all())

    def test_risk_limits_and_local_cash_conservation(self):
        with patch.object(RiskManager, "_load_state"), patch.object(RiskManager, "_save_state"):
            risk = RiskManager(100000)
            self.assertTrue(risk.can_trade(100000)[0])
            qty = risk.get_position_size_atr(100000,100,2)
            self.assertLessEqual(qty*100, risk.max_position_dollars)
            self.assertFalse(risk.can_trade(94000)[0])
            self.assertFalse(risk.can_trade(100000)[0])
            # Avoid loading the optional model when importing the local simulator.
            with patch("ml.predictor.MetaLabelPredictor"):
                from broker.paper import LocalPaperBroker
            with tempfile.TemporaryDirectory() as tmp:
                broker = LocalPaperBroker(initial_balance=10000, ticker="AAPL",
                    risk_manager=RiskManager(10000), signal_generator=Mock(), db_path=tmp+"/trades.db")
                broker.execute_buy(100,10,"offline test")
                self.assertEqual(broker.cash,9000)
                self.assertEqual(broker.shares,10)
                broker.execute_sell(110,"ALL","offline test")
                self.assertEqual(broker.cash,10100)
                self.assertEqual(broker.shares,0)
                self.assertEqual(len(broker.get_trade_history()),2)

