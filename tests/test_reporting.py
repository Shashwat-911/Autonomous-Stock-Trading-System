import ast
from datetime import datetime
import json
from pathlib import Path
import tempfile
from typing import Optional
import unittest
from unittest.mock import patch

import pandas as pd

from analytics.reporting import run_report, latest_report
from analytics.metrics import PerformanceEngine
from test_measurement import snapshot
from test_reconciliation import fill


def fixture():
    s = snapshot([fill(1, "A", "buy", 2, 10), fill(2, "A", "sell", 2, 20),
        {"id": "fund", "activity_type": "JNLC", "date": "2026-10-14", "net_amount": "1000"},
        {"id": "fee", "activity_type": "FEE", "date": "2026-10-15", "net_amount": "-1"}])
    s.update(account_created_at="2026-10-14T00:00:00Z", requested_end="2026-10-15")
    return s


class ReportingTests(unittest.TestCase):
    def test_staging_publication_and_failure_invalidation(self):
        with tempfile.TemporaryDirectory() as tmp:
            private, public = Path(tmp)/"private", Path(tmp)/"public"
            kwargs = dict(snapshot=fixture(), start="2026-10-14", end="2026-10-15",
                          private_root=private, public_root=public)
            result, stage = run_report(**kwargs, publish=False)
            self.assertFalse(public.exists())
            self.assertTrue((stage/"completed_position_episodes.csv").exists())
            run_report(**kwargs)
            generation = latest_report(public)
            self.assertEqual(json.loads((generation/"performance_summary.json").read_text())["total_trades"], 1)
            self.assertFalse((generation/"snapshot.json").exists())
            kwargs["snapshot"]["activities"].append(kwargs["snapshot"]["activities"][0])
            with self.assertRaises(ValueError):
                run_report(**kwargs)
            with self.assertRaises(ValueError):
                latest_report(public)

    def test_run_report_cannot_overwrite_cumulative_pointer(self):
        with tempfile.TemporaryDirectory() as tmp:
            kwargs = dict(snapshot=fixture(), start="2026-10-14", end="2026-10-15",
                          private_root=Path(tmp)/"private", public_root=Path(tmp)/"public")
            run_report(**kwargs)
            before = latest_report(kwargs["public_root"])
            r, _ = run_report(**kwargs, since="2026-10-15T15:00:00Z")
            self.assertEqual(r["summary"]["total_trades"],0)
            self.assertEqual(latest_report(kwargs["public_root"]), before)

    def test_api_failure_is_not_empty_success(self):
        class BrokenReader:
            def get(self, *args):
                raise RuntimeError("simulated network failure")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(RuntimeError):
                run_report(reader=BrokenReader(), private_root=root/"private", public_root=root/"public")
            self.assertEqual(json.loads((root/"public/report_status.json").read_text())["status"],"FAILED")

    def test_production_broker_adapter_uses_activity_episodes(self):
        # Isolate the actual method without initializing a broker, ML pickle or strategy.
        root = Path(__file__).resolve().parents[1]
        tree = ast.parse((root/"broker/alpaca.py").read_text(encoding="utf-8"))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name=="AlpacaPaperBroker")
        method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name=="_build_round_trips")
        ns = {"pd":pd,"Optional":Optional,"datetime":datetime}
        exec(compile(ast.Module(body=[method],type_ignores=[]),"broker-adapter","exec"),ns)
        build = ns["_build_round_trips"]
        cross = pd.DataFrame([fill(1,"AAPL","buy",1,100),fill(2,"MSFT","sell",1,400)])
        self.assertTrue(build(None,cross).empty)
        with self.assertRaises(ValueError):
            build(None,pd.DataFrame([{"symbol":"AAPL","filled_qty":1,"filled_avg_price":100}]))
        with self.assertRaises(ValueError):
            build(None,pd.DataFrame([{"activity_type":"SPLIT","id":"split"}]))
        trades = build(None,pd.DataFrame([fill(1,"A","buy",2,10),fill(2,"A","sell",1,20),fill(3,"A","sell",1,30)]))
        self.assertEqual(len(trades),1)
        self.assertEqual(trades.iloc[0]["pnl"],30)
        metrics = PerformanceEngine().compute_from_trades(trades, live_equity=999999)
        self.assertEqual(metrics["expectancy"],30)
        self.assertIsNone(metrics["ending_equity"])
        self.assertIsNone(metrics["avg_execution_latency_ms"])


if __name__ == "__main__":
    unittest.main()
