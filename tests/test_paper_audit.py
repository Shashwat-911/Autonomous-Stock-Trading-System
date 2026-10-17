import json
from pathlib import Path
import tempfile
import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

from scripts.reconcile_paper_account import PaperReader, analyze, session_evidence
from test_reconciliation import fill


class PaperAuditTests(unittest.TestCase):
    def test_network_boundary_rejects_trading_and_external_paths(self):
        reader = object.__new__(PaperReader)
        for path in ("/v2/positions/AAPL", "https://api.alpaca.markets/v2/account",
                     "/v2/orders/../../account"):
            with self.assertRaises(ValueError):
                reader.get(path)

    def test_reader_uses_only_paper_get(self):
        reader = object.__new__(PaperReader)
        reader.headers = {}
        class Opener:
            def open(self, request, timeout):
                self.request = request
                import io
                return io.BytesIO(b'[]')
        reader.opener = Opener()
        self.assertEqual(reader.get("/v2/orders"), [])
        self.assertEqual(reader.opener.request.get_method(), "GET")
        self.assertEqual(reader.opener.request.full_url, "https://paper-api.alpaca.markets/v2/orders")

    def test_flat_account_equity_bridge_and_missing_log_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "logs").mkdir()
            (root / "ledger.csv").write_text("timestamp,equity\n2026-10-14,1000\n2026-10-15,1019\n")
            acts = [fill(1, "A", "buy", 2, 10), fill(2, "A", "sell", 2, 20),
                    {"id": "fund", "activity_type": "JNLC", "date": "2026-10-14", "net_amount": "1000"},
                    {"id": "fee", "activity_type": "FEE", "date": "2026-10-15", "net_amount": "-1"}]
            snapshot = {"activities": acts, "orders": [
                {"id": "order-1", "symbol": "A", "filled_qty": "2"},
                {"id": "order-2", "symbol": "A", "filled_qty": "2"}],
                "positions_now": [], "account_snapshot": {"equity": "1019"},
                "fetched_at": "2026-10-16T00:00:00Z",
                "portfolio_history": {"timestamp": [
                    datetime(2026, 10, d, 20, tzinfo=timezone.utc).timestamp() for d in (14, 15)],
                    "equity": [1000, 1019]}}
            result = analyze(snapshot, date(2026, 10, 15), date(2026, 10, 15), root,
                             root / "ledger.csv", root / "logs")
            self.assertEqual(result["broker_equity_bridge"]["residual_including_unrealized"], "0")
            self.assertEqual(result["fills_without_direct_log_id"], 2)
            self.assertEqual(result["order_activity_quantity_mismatches"], 0)
            self.assertEqual(result["gross_realized_pnl_provisional"], "20")
            self.assertEqual(result["retained_history_current_equity_bridge"]["residual"], "0")
            self.assertEqual(result["orders_without_direct_log_id"], 2)
            self.assertTrue((root / "report.md").exists())

    def test_session_equity_gap_does_not_assume_origin(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "session_2026_10_16.txt").write_text(
                "Session started. Actual broker equity: $99,616.78\n"
                "Equity: $99,612.93 | Long exposure: $0\n")
            sessions, mentions = session_evidence(path)
            self.assertEqual(sessions[date(2026, 10, 16)]["run_start_equity"], "99616.78")
            self.assertEqual(mentions, {})


if __name__ == "__main__":
    unittest.main()
