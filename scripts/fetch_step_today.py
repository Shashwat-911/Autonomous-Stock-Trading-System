import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetPortfolioHistoryRequest
from datetime import datetime, timezone
import pandas as pd

client = TradingClient(
    config.ALPACA["api_key"],
    config.ALPACA["secret_key"],
    paper=True
)

history = client.get_portfolio_history(
    GetPortfolioHistoryRequest(
        timeframe="1D",
        start="2026-08-09",
        end="2026-08-29",
        extended_hours=False
    )
)

rows = []
for ts, eq, pl, plp in zip(
    history.timestamp, history.equity,
    history.profit_loss, history.profit_loss_pct
):
    if eq is None or eq == 0:
        continue
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    if dt.weekday() >= 5:
        continue
    rows.append({
        "timestamp": dt.strftime("%Y-%m-%d"),
        "equity": round(float(eq), 2),
        "daily_pnl": round(float(pl), 2),
        "daily_pnl_pct": round(float(plp) * 100, 4),
    })

df = pd.DataFrame(rows)
print("All sessions from Alpaca:")
print(df.to_string(index=False))
print(f"Aug 27 present: {'2026-08-27' in df['timestamp'].values}")
print(f"Aug 28 present: {'2026-08-28' in df['timestamp'].values}")
print(f"Total P&L: ${df['daily_pnl'].sum():.2f}")
print(f"Sessions: {len(df)}")
