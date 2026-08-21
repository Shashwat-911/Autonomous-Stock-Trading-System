import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import pandas as pd
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetPortfolioHistoryRequest
from datetime import datetime, timezone

client = TradingClient(
    config.ALPACA["api_key"],
    config.ALPACA["secret_key"],
    paper=True
)

history = client.get_portfolio_history(
    GetPortfolioHistoryRequest(
        timeframe="1D",
        start="2026-08-07",
        end="2026-08-22",
        extended_hours=False
    )
)

rows = []
seen_dates = set()
for ts, eq, pl, plp in zip(
    history.timestamp, history.equity,
    history.profit_loss, history.profit_loss_pct
):
    if eq is None or eq == 0:
        continue
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    date_str = dt.strftime("%Y-%m-%d")
    # Skip Sunday and redundant non-trading weekend days
    if dt.weekday() == 6 or date_str in seen_dates:
        continue
    # Exclude Aug 8 if identical to Aug 7 baseline
    if date_str == "2026-08-08":
        continue
    seen_dates.add(date_str)
    rows.append({
        "timestamp": date_str,
        "equity": round(float(eq), 2),
        "daily_pnl": round(float(pl), 2),
        "daily_pnl_pct": round(float(plp) * 100, 4),
    })

df = pd.DataFrame(rows)
os.makedirs("outputs", exist_ok=True)
df.to_csv("outputs/alpaca_equity_history.csv", index=False)

print("Real equity data from Alpaca:")
print(df.to_string(index=False))
print(f"\nTotal P&L: ${df['daily_pnl'].sum():.2f}")
print(f"Win days:  {(df['daily_pnl'] > 0).sum()}")
print(f"Loss days: {(df['daily_pnl'] < 0).sum()}")
print(f"Sessions:  {len(df)}")
