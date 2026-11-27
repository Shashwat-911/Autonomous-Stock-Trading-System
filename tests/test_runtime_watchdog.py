from datetime import datetime,timezone,timedelta
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from scripts.check_runtime import validate
from broker.alpaca import AlpacaPaperBroker


class WatchdogTests(unittest.TestCase):
    def test_healthy_http_is_insufficient_without_recent_clock_and_worker(self):
        now=datetime.now(timezone.utc)
        status={'execution_owner':'render','market_clock':'open',
                'market_clock_checked_at':now.isoformat(),'runner_state':'trading_session_running'}
        self.assertTrue(validate(status,now))
        with self.assertRaises(ValueError): validate({**status,'runner_state':'session_exited'},now)
        with self.assertRaises(ValueError): validate(status,now+timedelta(minutes=4))
        self.assertTrue(validate({**status,'market_clock':'closed','runner_state':'waiting_for_market'},now))
        with self.assertRaisesRegex(ValueError,'credential'):
            validate({**status,'private_evidence':{'configured':False}},now)
        with self.assertRaisesRegex(ValueError,'delivery'):
            validate({**status,'private_evidence':{'configured':True,'oldest_pending_seconds':901}},now)

    def test_eod_exit_acknowledgement_is_not_flat_confirmation(self):
        b=object.__new__(AlpacaPaperBroker);b.ticker='TEST';b.client=Mock()
        b.get_current_position=Mock(return_value={'shares':2})
        b.client.get_orders.return_value=[];b.client.close_position.return_value=SimpleNamespace(id='close')
        result=b.eod_liquidate_all()
        self.assertTrue(result['pending']);self.assertFalse(result['position_closed'])
        b.client.get_order_by_id.return_value=SimpleNamespace(status='accepted')
        self.assertTrue(b.eod_liquidate_all()['pending'])
        b.client.close_position.assert_called_once()
        b.client.get_order_by_id.return_value=SimpleNamespace(status='filled')
        b.get_current_position.return_value=None
        self.assertTrue(b.eod_liquidate_all()['position_closed'])

    def test_restarted_eod_runner_does_not_duplicate_pending_market_exit(self):
        b=object.__new__(AlpacaPaperBroker);b.ticker='TEST';b.client=Mock()
        b.get_current_position=Mock(return_value={'shares':2})
        b.client.get_orders.return_value=[SimpleNamespace(id='exit',side='sell',order_type='market')]
        self.assertTrue(b.eod_liquidate_all()['pending'])
        b.client.close_position.assert_not_called();b.client.cancel_order_by_id.assert_not_called()
