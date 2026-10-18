"""Local replay contract; skipped in clones that do not contain private evidence."""
import json
from pathlib import Path
import unittest

from analytics.measurement import build_report

SNAPSHOT = Path(__file__).resolve().parents[1] / "outputs/private_reconciliation/20261017T155359282133Z/snapshot.json"


@unittest.skipUnless(SNAPSHOT.exists(), "Private verified snapshot not distributed with repository")
class VerifiedSnapshotTests(unittest.TestCase):
    def test_retained_history_matches_verified_account(self):
        source = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        report = build_report(source, "2026-08-10", "2026-10-16")
        summary = report["summary"]
        self.assertEqual(summary["issues"], [])
        self.assertEqual(summary["lifetime_bridge"], {
            "funding_net": "100000", "gross_realized": "-369.14", "nontrade_net": "99981.41",
            "fees": "-18.59", "unrealized": "0", "residual": "0.00"})
        self.assertEqual(summary["current_account_equity"], "99612.27")
        self.assertEqual(summary["total_trades"], 335)
        self.assertEqual(summary["winning_trades"], 137)
        self.assertEqual(summary["losing_trades"], 198)
        self.assertEqual(report["unfinished"], [])
        self.assertEqual(report["lots"], [])
        self.assertAlmostEqual(summary["expectancy"], -369.14/335)
        # Date-window realized P&L and episode outcomes are distinct concepts.
        window = build_report(source, "2026-10-16", "2026-10-16", since="2026-10-16T17:35:51Z")
        self.assertEqual(window["summary"]["realized_pnl_in_date_window"], "-252.44")
        self.assertEqual(window["summary"]["completed_episode_gross_pnl"], "-3.85")


if __name__ == "__main__":
    unittest.main()
