"""Exercise actual broker methods offline, without loading models or credentials."""
import ast
from datetime import datetime
import logging
import math
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, Optional, get_type_hints
import unittest
from unittest.mock import Mock, patch
import pandas as pd
from alpaca.common.exceptions import APIError
from alpaca.trading.enums import QueryOrderStatus
from alpaca.trading.requests import GetOrdersRequest
from requests import Response, HTTPError


def broker_class():
    tree = ast.parse((Path(__file__).resolve().parents[1]/"broker/alpaca.py").read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    names = {"run_tick", "get_current_position", "get_all_positions", "_has_pending_buy_order", "_make_client_order_id"}
    cls.body = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in names]
    ns = dict(globals(), logger=logging.getLogger("safety-test"))
    exec(compile(ast.Module(body=[cls], type_ignores=[]), "actual-broker-methods", "exec"), ns)
    broker = ns[cls.name]
    # Python 3.14 defers annotations; resolve explicitly so missing names also
    # fail locally instead of surfacing only on the Python 3.11 CI runner.
    for name in names:
        get_type_hints(getattr(broker, name), globalns=ns)
    return broker


class BrokerSafetyTests(unittest.TestCase):
    def setUp(self):
        self.b = broker_class()()
        self.b.ticker = "AAPL"
        self.b.client = Mock()

    def test_only_404_is_an_absent_position(self):
        response = Response()
        response.status_code = 404
        self.b.client.get_open_position.side_effect = APIError('{"message":"absent"}', HTTPError(response=response))
        self.assertIsNone(self.b.get_current_position())
        response.status_code = 403
        with self.assertRaises(APIError):
            self.b.get_current_position()
        self.b.client.get_open_position.side_effect = TimeoutError()
        with self.assertRaises(TimeoutError):
            self.b.get_current_position()

    def test_inventory_and_pending_failures_do_not_mean_flat(self):
        self.b.client.get_all_positions.side_effect = TimeoutError()
        with self.assertRaises(TimeoutError):
            self.b.get_all_positions()
        self.b.client.get_orders.side_effect = TimeoutError()
        with self.assertRaises(RuntimeError):
            self.b._has_pending_buy_order()

    def test_failed_account_or_invalid_price_never_submits(self):
        self.b.is_market_open = Mock(return_value=True)
        self.b.get_account_info = Mock(side_effect=TimeoutError())
        self.b.submit_buy = Mock()
        self.b.submit_bracket_buy = Mock()
        for price in (100, float("inf"), float("nan"), -1):
            result = self.b.run_tick(pd.DataFrame({"Close": [price]}))
            self.assertEqual(result["action"], "SKIP")
        self.b.submit_buy.assert_not_called()
        self.b.submit_bracket_buy.assert_not_called()

    def test_only_acknowledged_buys_update_pending_exposure(self):
        b = self.b
        b.min_confidence = .5
        b.is_market_open = Mock(return_value=True)
        b.get_account_info = Mock(return_value={"portfolio_value": 100000})
        b.get_current_position = Mock(return_value=None)
        b.get_all_positions = Mock(return_value={})
        b._update_trailing_stop = Mock()
        b._has_pending_buy_order = Mock(return_value=False)
        b.risk_manager = Mock()
        b.risk_manager.can_trade.return_value = (True, "OK")
        b.risk_manager.check_portfolio_heat.return_value = (True, "OK")
        b.risk_manager.get_position_size_atr.return_value = 2
        b.signal_generator = Mock()
        b.signal_generator.generate_signal.return_value = {"signal":"BUY", "confidence":.8, "reasons":["test"]}
        b._last_buy_time = {}
        b.submit_bracket_buy = Mock(return_value={})
        data = pd.DataFrame({"Close":[100], "ATR_14":[2]})
        failed = b.run_tick(data)
        self.assertEqual(failed["action"], "SKIP")
        self.assertEqual(failed["order_value"], 0)
        self.assertEqual(b._last_buy_time, {})
        blocked = b.run_tick(data, allow_new_entries=False)
        self.assertEqual(blocked["price"], 100)
        self.assertEqual(blocked["signal"], "BUY")
        self.assertFalse(blocked["can_trade"])
        b.submit_bracket_buy.return_value = {"order_id":"accepted"}
        accepted = b.run_tick(data)
        self.assertEqual(accepted["action"], "BUY")
        self.assertEqual(accepted["order_value"], 200)
        self.assertIn("AAPL", b._last_buy_time)

    def test_order_ids_identify_runner_and_remain_unique(self):
        with patch.dict(os.environ, {"TRADING_EXECUTION_SOURCE":"github-actions"}):
            a = self.b._make_client_order_id("same signal")
            b = self.b._make_client_order_id("same signal")
        self.assertTrue(a.startswith("gh-AAPL-"))
        self.assertNotEqual(a,b)
        self.assertLessEqual(len(a),48)
