import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import pandas as pd
from analytics.decision_trace import record_tick, replay_tick
from analytics.private_evidence import upload, EvidenceError
from broker.alpaca import AlpacaPaperBroker
from strategy.indicators import add_all_indicators
from strategy.signals import SignalGenerator


class TraceTests(unittest.TestCase):
    def trace(self):
        b=object.__new__(AlpacaPaperBroker); b.ticker='TEST'; b.min_confidence=.7
        b._last_buy_time={}; b.client=Mock()
        b.risk_manager=Mock(); b.risk_manager.can_trade.return_value=(True,'OK')
        b.signal_generator=SignalGenerator(b.risk_manager)
        for name,result in [('get_account_info',{'portfolio_value':100000}),
                ('get_current_position',None),('get_all_positions',{}),
                ('is_market_open',True),('_has_pending_buy_order',False),
                ('_update_trailing_stop',None),('submit_buy',{}),('submit_sell',{}),('submit_bracket_buy',{})]:
            setattr(b,name,Mock(return_value=result))
        frame=pd.DataFrame({'Open':[100+i*.1 for i in range(100)],
            'High':[101+i*.1 for i in range(100)],'Low':[99+i*.1 for i in range(100)],
            'Close':[100+i*.1 for i in range(100)],'Volume':[1000]*100},
            index=pd.date_range('2026-01-01',periods=100,tz='UTC'))
        return record_tick(b,add_all_indicators(frame),{'allow_new_entries':False,'daily_trend_bullish':None,'market_regime_bullish':True})[1]

    def test_actual_signal_and_broker_path_replays_without_client(self):
        trace=self.trace()
        self.assertNotIn('error',trace)
        self.assertEqual(replay_tick(trace)['status'],'MATCH')
        next(c for c in trace['calls'] if c['method']=='broker.get_account_info')['result']['portfolio_value']=5
        self.assertEqual(replay_tick(trace)['status'],'MISMATCH')

    def test_code_drift_blocks_replay(self):
        trace=self.trace(); trace['code_sha256']={}
        self.assertEqual(replay_tick(trace)['status'],'BLOCKED_CODE_MISMATCH')

    def test_public_destination_cannot_receive_evidence(self):
        with patch.dict('os.environ',{'GIT_TOKEN':'test'}), patch('analytics.private_evidence._request',return_value={'private':False}) as request:
            with self.assertRaises(EvidenceError): upload(Path('missing'))
            self.assertEqual(request.call_count,1)

    def test_upload_conflict_requires_identical_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'20261127-test.json.gz';path.write_bytes(b'test')
            with patch.dict('os.environ',{'GIT_TOKEN':'test'}), patch('analytics.private_evidence._request',side_effect=[{'private':True},EvidenceError('github_http_422'),{'sha':'wrong'}]):
                with self.assertRaisesRegex(EvidenceError,'remote_content_conflict'): upload(path)
                self.assertFalse(path.with_suffix('.gz.uploaded').exists())
