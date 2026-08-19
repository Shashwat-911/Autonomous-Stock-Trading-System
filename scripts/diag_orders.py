"""Diagnostic: inspect last 50 Alpaca orders for bracket vs market type."""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import QueryOrderStatus

client = TradingClient(
    config.ALPACA["api_key"],
    config.ALPACA["secret_key"],
    paper=True,
)

orders = client.get_orders(GetOrdersRequest(status=QueryOrderStatus.ALL, limit=50))

header = f"{'Symbol':<8} {'Side':<6} {'Type':<12} {'Status':<12} {'Order Class':<14} {'Filled Price'}"
print(f"Last {len(orders)} orders:")
print(header)
print("-" * len(header))

for o in orders:
    side = str(o.side.value) if hasattr(o.side, "value") else str(o.side)
    otype = str(o.order_type.value) if hasattr(o.order_type, "value") else str(o.order_type)
    status = str(o.status.value) if hasattr(o.status, "value") else str(o.status)
    oclass = str(o.order_class.value) if hasattr(o.order_class, "value") else str(o.order_class or "simple")
    price = float(o.filled_avg_price or 0)
    legs = ""
    if o.legs:
        leg_info = []
        for leg in o.legs:
            leg_type = str(leg.order_type.value) if hasattr(leg.order_type, "value") else str(leg.order_type)
            leg_side = str(leg.side.value) if hasattr(leg.side, "value") else str(leg.side)
            leg_status = str(leg.status.value) if hasattr(leg.status, "value") else str(leg.status)
            stop = leg.stop_price or ""
            limit = leg.limit_price or ""
            leg_info.append(f"{leg_side}/{leg_type}(SL={stop},TP={limit},{leg_status})")
        legs = " | LEGS: " + ", ".join(leg_info)
    print(f"{o.symbol:<8} {side:<6} {otype:<12} {status:<12} {oclass:<14} {price:.2f}{legs}")
