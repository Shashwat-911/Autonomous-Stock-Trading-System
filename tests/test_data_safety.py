from datetime import datetime, timezone
import unittest
from unittest.mock import Mock, patch
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

    def test_stale_daily_trend_is_unknown(self):
        frame=pd.DataFrame({'Close':range(100,120)},index=pd.bdate_range('2026-01-01',periods=20))
        self.assertIsNone(daily_trend(frame,'2026-11-25'))

    def test_live_daily_fetch_accepts_strict_mode_and_preserves_missing_prices(self):
        from data.fetcher import get_historical_data
        frame=pd.DataFrame({'Close':[100.,float('nan'),102.]},
                           index=pd.date_range('2026-11-23',periods=3))
        with patch('data.fetcher.yf.Ticker') as ticker:
            ticker.return_value.history.return_value=frame.copy()
            strict=get_historical_data('TEST','2026-11-01','2026-11-27','1d',strict=True)
            self.assertTrue(pd.isna(strict.Close.iloc[1]))
            normal=get_historical_data('TEST','2026-11-01','2026-11-27','1d')
            self.assertFalse(normal.Close.isna().any())

    def test_regime_excludes_forming_daily_candle_and_rejects_stale_data(self):
        from data.fetcher import get_market_regime_data
        frame=pd.DataFrame({'Close':[100]*200+[1000]},index=pd.bdate_range('2026-01-01',periods=201))
        day=frame.index[-2].date().isoformat()
        with patch('data.fetcher.yf.Ticker') as ticker:
            ticker.return_value.history.return_value=frame
            result=get_market_regime_data(completed_session=day)
            self.assertEqual(result['price'],100)
            self.assertFalse(result['is_bullish'])
            self.assertIsNone(get_market_regime_data(completed_session='2026-12-31')['is_bullish'])

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

    def test_rejected_bracket_never_falls_back_to_unprotected_market_order(self):
        b=object.__new__(AlpacaPaperBroker); b.ticker='AAPL'; b.client=Mock()
        b.client.submit_order.side_effect=RuntimeError('rejected')
        b._make_client_order_id=Mock(return_value='test-order')
        b.submit_buy=Mock()
        result=b.submit_bracket_buy(quantity=2,current_price=100,atr=2)
        self.assertEqual(result,{})
        b.submit_buy.assert_not_called()

    def test_infinite_price_never_reaches_account_or_order_queries(self):
        b=self.broker()
        self.assertEqual(b.run_tick(pd.DataFrame({'Close':[float('inf')]}))['action'],'SKIP')
        b.get_account_info.assert_not_called()
