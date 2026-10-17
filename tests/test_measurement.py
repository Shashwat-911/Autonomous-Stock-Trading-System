import copy
from datetime import datetime, timezone
import unittest

from analytics.measurement import position_episodes, episode_metrics, build_report, equity_observations
from test_reconciliation import fill


def snapshot(acts, equity="1019", positions=None):
    return {"activities": acts,
            "orders": [{"id": a["order_id"], "filled_qty": a["qty"]} for a in acts if a.get("activity_type") == "FILL"],
            "positions_now": positions or [], "account_snapshot": {"equity": equity},
            "fetched_at": "2026-10-16T12:00:00Z",
            "portfolio_history": {"timestamp": [datetime(2026, 10, d, 20, tzinfo=timezone.utc).timestamp() for d in (14, 15)],
                                  "equity": [1000, 1019]}}


class MeasurementTests(unittest.TestCase):
    def test_fragments_are_one_episode_and_partial_inventory_retained(self):
        f = [fill(1,"A","buy",2,10), fill(2,"A","buy",3,20), fill(3,"A","sell",3,30)]
        done, opened = position_episodes(f)
        self.assertEqual(done, [])
        self.assertEqual(opened[0]["signed_qty"], "2")
        done, opened = position_episodes(f + [fill(4,"A","sell",2,40)])
        self.assertEqual(len(done), 1)
        self.assertEqual(done[0]["pnl"], "90")
        self.assertEqual(opened, [])

    def test_cross_symbol_and_short_reversal(self):
        done, opened = position_episodes([fill(1,"AAPL","buy",1,100),fill(2,"MSFT","sell",1,400)])
        self.assertEqual(done, [])
        done, opened = position_episodes([fill(1,"A","buy",2,10),fill(2,"A","sell",3,20),fill(3,"A","buy",1,15)])
        self.assertEqual([d["pnl"] for d in done], ["20", "5"])
        self.assertEqual([d["direction"] for d in done], ["long", "short"])

    def test_duplicate_and_nan_fills_fail(self):
        f = fill(1,"A","buy",1,10)
        with self.assertRaises(ValueError):
            position_episodes([f,f])
        f["price"] = "NaN"
        with self.assertRaises(ValueError):
            position_episodes([f])

    def test_expectancy_includes_breakeven_without_counting_as_loss(self):
        m = episode_metrics([{"pnl":"10"},{"pnl":"-4"},{"pnl":"0"}])
        self.assertEqual(m["expectancy"], 2)
        self.assertEqual(m["breakeven_trades"], 1)
        self.assertEqual(m["win_rate"], 1/3)
        self.assertIsNone(episode_metrics([{"pnl":"10"}])["profit_factor"])
        self.assertIsNone(episode_metrics([])["expectancy"])

    def test_opening_inventory_precedes_date_filter(self):
        a = fill(1,"A","buy",2,10)
        a["transaction_time"] = "2026-10-14T14:00:01Z"
        b = fill(2,"A","sell",2,20)
        acts = [a,b,{"id":"cash","activity_type":"JNLC","date":"2026-10-14","net_amount":"1000"},
                {"id":"fee","activity_type":"FEE","date":"2026-10-15","net_amount":"-1"}]
        r = build_report(snapshot(acts),"2026-10-15","2026-10-15")
        self.assertEqual(r["summary"]["total_trades"],1)
        self.assertTrue(r["episodes"][0]["entry_before_reporting_boundary"])
        self.assertEqual(r["summary"]["lifetime_bridge"]["residual"],"0")
        self.assertEqual(r["summary"]["fees_in_date_window"],"-1")
        self.assertEqual(build_report(snapshot(acts),"2026-10-15","2026-10-15",since="2026-10-15T15:00:00Z")["summary"]["total_trades"],0)

    def test_unknown_corporate_action_and_missing_funding_flagged(self):
        r = build_report(snapshot([{"id":"split","activity_type":"SPLIT","date":"2026-10-15"}]),"2026-10-14","2026-10-15")
        self.assertEqual(r["summary"]["status"],"REQUIRES_REVIEW")
        self.assertTrue(any("Unsupported" in i for i in r["summary"]["issues"]))
        self.assertTrue(any("funding" in i for i in r["summary"]["issues"]))

    def test_current_equity_never_overwrites_historical_marks(self):
        s = snapshot([], equity="5000")
        rows = equity_observations(s)
        self.assertEqual(rows[-1]["equity"],"1019")
        self.assertEqual(rows[-1]["valuation_timestamp"],"2026-10-15T20:00:00+00:00")
        s["portfolio_history"]["equity"].pop()
        with self.assertRaises(ValueError):
            equity_observations(s)

    def test_same_day_incomplete_bar_excluded_and_no_fabricated_baseline(self):
        s = snapshot([])
        s["fetched_at"] = "2026-10-15T18:00:00Z"
        self.assertEqual(len(equity_observations(s)),1)
        s["calendar"] = [{"date":"2026-10-15","close":"16:00"}]
        s["fetched_at"] = "2026-10-15T21:00:00Z"
        self.assertEqual(len(equity_observations(s)),2)
        r = build_report(s,"2026-10-14","2026-10-15")
        self.assertIsNone(r["daily"][0]["equity_change_since_prior_observation"])


if __name__ == "__main__":
    unittest.main()
