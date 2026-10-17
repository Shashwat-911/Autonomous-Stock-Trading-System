import unittest
from datetime import datetime, timezone
from scripts.reconciliation import match_fills, flatten_orders, activity_pages, order_pages


def fill(i, symbol, side, qty, price):
    return dict(id=str(i), activity_type="FILL", symbol=symbol, side=side,
                qty=str(qty), price=str(price), order_id=f"order-{i}",
                transaction_time=f"2026-10-15T14:00:{i:02d}Z")


class ReconciliationTests(unittest.TestCase):
    def test_symbols_never_cross_match(self):
        matches, lots = match_fills([fill(1, "AAPL", "buy", 10, 100),
                                    fill(2, "MSFT", "sell", 10, 400)])
        self.assertEqual(matches, [])
        self.assertEqual(len(lots), 2)

    def test_partial_fifo_and_fractional_residual(self):
        matches, lots = match_fills([fill(1, "A", "buy", 2, 10),
                                    fill(2, "A", "buy", 3, 20),
                                    fill(3, "A", "sell", "3.5", 30)])
        self.assertEqual([m["gross_pnl"] for m in matches], ["40", "15.0"])
        self.assertEqual(lots[0]["signed_qty"], "1.5")

    def test_short_cover(self):
        matches, lots = match_fills([fill(1, "A", "sell_short", 2, 30),
                                    fill(2, "A", "buy", 3, 20)])
        self.assertEqual(matches[0]["gross_pnl"], "20")
        self.assertEqual(lots[0]["signed_qty"], "1")

    def test_duplicate_fill_is_not_double_counted(self):
        f = fill(1, "A", "buy", 1, 1)
        with self.assertRaises(ValueError):
            match_fills([f, f])

    def test_bracket_leg_deduplication(self):
        child = {"id": "child"}
        rows = flatten_orders([{"id": "parent", "legs": [child]}, child])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["parent_order_id"], "parent")

    def test_activity_pagination(self):
        calls = []
        def get(path, params):
            calls.append(dict(params))
            return ([{"id": str(i)} for i in range(100)] if len(calls) == 1
                    else [{"id": "100"}])
        self.assertEqual(len(activity_pages(get)), 101)
        self.assertEqual(calls[1]["page_token"], "99")

    def test_repeated_activity_page_fails(self):
        with self.assertRaises(ValueError):
            activity_pages(lambda *args: [{"id": str(i)} for i in range(100)])

    def test_saturated_orders_are_split_and_deduplicated(self):
        calls = []
        def get(path, params):
            calls.append(params)
            self.assertEqual(params["nested"], "false")
            if len(calls) == 1:
                return [{"id": str(i)} for i in range(500)]
            return [{"id": "boundary"}, {"id": str(len(calls))}]
        rows = order_pages(get, datetime(2026, 1, 1, tzinfo=timezone.utc),
                           datetime(2026, 2, 1, tzinfo=timezone.utc))
        self.assertEqual(len(rows), 3)
        self.assertEqual(len(calls), 3)


if __name__ == "__main__":
    unittest.main()
