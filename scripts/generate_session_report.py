import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config
import pandas as pd
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import QueryOrderStatus
from analytics.metrics import PerformanceEngine

def main():
    api_key = config.ALPACA["api_key"]
    secret_key = config.ALPACA["secret_key"]
    client = TradingClient(api_key, secret_key, paper=True)

    print("Fetching filled order history from Alpaca Paper Account...")
    orders = client.get_orders(GetOrdersRequest(status=QueryOrderStatus.ALL))
    print(f"Total orders retrieved: {len(orders)}")

    data = []
    for o in orders:
        data.append({
            "order_id": str(o.id),
            "submitted_at": str(o.submitted_at),
            "filled_at": str(o.filled_at),
            "symbol": o.symbol,
            "side": str(o.side.value).upper() if hasattr(o.side, "value") else str(o.side),
            "qty": float(o.qty or 0),
            "filled_qty": float(o.filled_qty or 0),
            "price": float(o.limit_price or o.stop_price or 0),
            "filled_avg_price": float(o.filled_avg_price or 0),
            "type": str(o.order_type.value) if hasattr(o.order_type, "value") else str(o.order_type),
            "status": str(o.status.value) if hasattr(o.status, "value") else str(o.status),
        })

    df = pd.DataFrame(data)
    os.makedirs("outputs", exist_ok=True)
    df.to_csv("outputs/session_all_orders.csv", index=False)

    account = client.get_account()
    real_equity = float(account.equity)
    cash = float(account.cash)
    lmv = float(account.long_market_value)

    pe = PerformanceEngine()
    metrics = pe.compute_from_trades(
        df,
        starting_equity=config.TRADING["initial_balance"],
        live_equity=real_equity,
    )
    pe.save_summary("outputs/performance_summary.json")
    pe.append_session_stats("outputs/trade_history.csv")

    print("\n" + "=" * 60)
    print("  FINAL SESSION SUMMARY (1:30 AM IST SESSION CLOSE)")
    print("=" * 60)
    print(f"  Final Account Equity:    ${real_equity:,.2f}")
    print(f"  Cash Available:          ${cash:,.2f}")
    print(f"  Long Market Value:       ${lmv:,.2f}")
    print(f"  Portfolio Heat:          {(lmv/real_equity*100):.1f}% (Limit: 60.0%)")
    print("-" * 60)
    print(pe.get_summary_string())

if __name__ == "__main__":
    main()
