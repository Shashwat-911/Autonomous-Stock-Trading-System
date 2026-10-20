"""Exercise actual broker methods offline, without loading models or credentials."""
import ast
from datetime import datetime
import logging
import math
from pathlib import Path
from types import SimpleNamespace
from typing import Dict
import unittest
from unittest.mock import Mock
import pandas as pd
from alpaca.common.exceptions import APIError
from alpaca.trading.enums import QueryOrderStatus
from alpaca.trading.requests import GetOrdersRequest
from requests import Response, HTTPError


def broker_class():
    tree = ast.parse((Path(__file__).resolve().parents[1]/"broker/alpaca.py").read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    names = {"run_tick", "get_current_position", "get_all_positions", "_has_pending_buy_order"}
    cls.body = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in names]
    ns = dict(globals(), logger=logging.getLogger("safety-test"))
    exec(compile(ast.Module(body=[cls], type_ignores=[]), "actual-broker-methods", "exec"), ns)
    return ns[cls.name]


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
