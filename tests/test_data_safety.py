from datetime import datetime, timezone
import unittest
from unittest.mock import Mock
import pandas as pd
from broker.alpaca import AlpacaPaperBroker
from strategy.data_quality import completed_bars, daily_trend


class DataSafetyTests(unittest.TestCase):
    def bars(self):
        return pd.DataFrame({'Open':100., 'High':102., 'Low':99., 'Close':101., 'Volume':1000},
            index=pd.date_range('2026-11-27 09:30', periods=4, freq='1h', tz='America/New_York'))

    def calendar(self):
        return [{'open':'2026-11-27T09:30:00-05:00','close':'2026-11-27T13:00:00-05:00'}]

    def test_forming_and_early_close(self):
        bars, status = completed_bars(self.bars(), self.calendar(), '2026-11-27T12:10:00-05:00')
        self.assertEqual(len(bars), 2)
        self.assertEqual(status, 'FRESH')
        bars, status = completed_bars(self.bars(), self.calendar(), '2026-11-27T13:03:00-05:00')
        self.assertEqual(len(bars), 4)
        self.assertEqual(status, 'FRESH')

    def test_missing_duplicate_and_naive_bars(self):
        now='2026-11-27T13:03:00-05:00'
        self.assertEqual(completed_bars(self.bars().iloc[:-1],self.calendar(),now)[1], 'STALE')
        self.assertEqual(completed_bars(pd.concat([self.bars(), self.bars()]),self.calendar(),now)[1], 'INVALID')
        frame=self.bars(); frame.index=frame.index.tz_localize(None)
        self.assertEqual(completed_bars(frame,self.calendar(),now)[1], 'UNKNOWN')
        self.assertEqual(completed_bars(self.bars(),[],now)[1], 'UNKNOWN')

    def test_daily_missing_is_unknown_not_bullish(self):
        for frame in (None, pd.DataFrame({'Close':[100]*19}), pd.DataFrame({'Close':[100]*19+[float('nan')]})):
            self.assertIsNone(daily_trend(frame))

    def broker(self):
        b=object.__new__(AlpacaPaperBroker)
        b.ticker='AAPL'; b.client=Mock(); b.min_confidence=.5
        b.is_market_open=Mock(return_value=True)
        b.get_account_info=Mock(return_value={'portfolio_value':100000})
        b.get_current_position=Mock(return_value=None)
        b.get_all_positions=Mock(return_value={})
        b._update_trailing_stop=Mock(); b._has_pending_buy_order=Mock(return_value=False)
        b.risk_manager=Mock(); b.risk_manager.can_trade.return_value=(True,'OK')
        b.risk_manager.check_portfolio_heat.return_value=(True,'OK')
        b.risk_manager.get_position_size_atr.return_value=2
        b.signal_generator=Mock(); b.signal_generator.generate_signal.return_value={'signal':'BUY','confidence':.8,'reasons':['test']}
        b.submit_bracket_buy=Mock(return_value={}); b._last_buy_time={}
        return b

    def test_actual_tick_blocks_unknown_and_counts_only_acknowledged_orders(self):
        b=self.broker(); frame=pd.DataFrame({'Close':[100], 'ATR_14':[2]})
        b.run_tick(frame,daily_trend_bullish=None)
        b.submit_bracket_buy.assert_not_called()
        result=b.run_tick(frame)
        self.assertNotEqual(result.get('action'), 'BUY')
        self.assertEqual(b._last_buy_time,{})
        b.submit_bracket_buy.return_value={'order_id':'accepted'}
        self.assertEqual(b.run_tick(frame)['order_value'],200)

    def test_inventory_and_pending_queries_fail_closed(self):
        b=object.__new__(AlpacaPaperBroker); b.ticker='AAPL'; b.client=Mock()
        b.client.get_open_position.side_effect=TimeoutError()
        b.client.get_all_positions.side_effect=TimeoutError()
        b.client.get_orders.side_effect=TimeoutError()
        with self.assertRaises(RuntimeError): b.get_current_position()
        with self.assertRaises(RuntimeError): b.get_all_positions()
        self.assertTrue(b._has_pending_buy_order())
