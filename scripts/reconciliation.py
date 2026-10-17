"""Pure, offline reconciliation primitives. No broker or strategy imports."""
from collections import defaultdict, deque
from datetime import datetime, timezone
from decimal import Decimal


def amount(value):
    return Decimal(str(value or 0))


def timestamp(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Execution/valuation timestamp requires an explicit timezone")
    return parsed.astimezone(timezone.utc)


def match_fills(activities):
    """Symbol-aware FIFO, including partial fills and short covers.

    Consume account-lifetime FILL activities, not cumulative order quantities.
    Residual lots are retained. Unknown sides fail rather than inventing P&L.
    Corporate actions require separate basis handling and are not modeled here.
    """
    lots = defaultdict(deque)
    matches = []
    seen = set()
    fills = sorted((a for a in activities if a.get("activity_type") == "FILL"),
                   key=lambda a: (timestamp(a["transaction_time"]), a["id"]))
    for fill in fills:
        if fill["id"] in seen:
            raise ValueError("Duplicate fill activity ID")
        seen.add(fill["id"])
        side = fill["side"].lower()
        if side not in ("buy", "sell", "sell_short", "buy_to_cover"):
            raise ValueError("Unsupported fill side")
        sign = 1 if side in ("buy", "buy_to_cover") else -1
        qty, price = amount(fill["qty"]), amount(fill["price"])
        if not qty.is_finite() or not price.is_finite() or qty <= 0 or price <= 0 or not fill.get("symbol"):
            raise ValueError("Invalid fill quantity, price or symbol")
        queue = lots[fill["symbol"]]
        while qty and queue and queue[0]["sign"] != sign:
            entry = queue[0]
            matched = min(qty, entry["qty"])
            matches.append({
                "symbol": fill["symbol"], "qty": str(matched),
                "entry_time": entry["time"], "exit_time": fill["transaction_time"],
                "entry_order_id": entry["order_id"], "exit_order_id": fill["order_id"],
                "entry_price": str(entry["price"]), "exit_price": str(price),
                "direction": "long" if entry["sign"] == 1 else "short",
                "gross_pnl": str((price - entry["price"]) * matched * entry["sign"]),
            })
            qty -= matched
            entry["qty"] -= matched
            if not entry["qty"]:
                queue.popleft()
        if qty:
            queue.append({"qty": qty, "price": price, "sign": sign,
                          "time": fill["transaction_time"], "order_id": fill["order_id"]})
    residual = []
    for symbol, queue in sorted(lots.items()):
        for lot in queue:
            residual.append({"symbol": symbol, "signed_qty": str(lot["qty"] * lot["sign"]),
                             "entry_price": str(lot["price"]), "entry_time": lot["time"],
                             "order_id": lot["order_id"]})
    return matches, residual


def flatten_orders(orders):
    """Flatten bracket legs; an order ID represents one order, never one fill."""
    result = {}
    def visit(order, parent=None):
        row = {k: v for k, v in order.items() if k != "legs"}
        row["parent_order_id"] = parent
        prior = result.get(row["id"])
        if prior and prior.get("parent_order_id") and not parent:
            row["parent_order_id"] = prior["parent_order_id"]
        result[row["id"]] = row
        for leg in order.get("legs") or []:
            visit(leg, row["id"])
    for order in orders:
        visit(order)
    return list(result.values())


def activity_pages(get):
    """Read all retained activities, including pre-window inventory and late fees."""
    result, ids, tokens = [], set(), set()
    params = {"direction": "asc", "page_size": 100}
    while True:
        page = get("/v2/account/activities", params)
        if not isinstance(page, list):
            raise ValueError("Invalid activities response")
        if not page:
            break
        for row in page:
            if row["id"] in ids:
                raise ValueError("Activity pagination repeated an ID; completeness unknown")
            ids.add(row["id"])
            result.append(row)
        token = page[-1]["id"]
        if token in tokens:
            raise ValueError("Activity pagination did not advance")
        tokens.add(token)
        params["page_token"] = token
        if len(page) < 100:
            break
    return result


def order_pages(get, lower, upper):
    """Split saturated time windows with overlap to avoid losing timestamp ties.

    Abort if a one-microsecond interval is saturated. Never silently truncate.
    Activities remain the source of executions, including partial/cancelled fills.
    """
    from datetime import timedelta
    def collect(lo, hi):
        # Nested responses collapse legs into parents AFTER applying the limit:
        # a page shorter than 500 can therefore still be truncated. Flat orders
        # preserve the pagination count and include bracket children independently.
        rows = get("/v2/orders", {"status": "all", "limit": 500, "nested": "false",
                                 "direction": "asc", "after": lo.isoformat(),
                                 "until": hi.isoformat()})
        if not isinstance(rows, list):
            raise ValueError("Invalid orders response")
        if len(rows) < 500:
            return rows
        if (hi - lo).total_seconds() <= 0.000004:
            raise ValueError("Saturated order timestamp; cannot guarantee completeness")
        mid = lo + (hi - lo) / 2
        return collect(lo, mid + timedelta(microseconds=1)) + collect(mid, hi)
    return flatten_orders(collect(lower, upper))
