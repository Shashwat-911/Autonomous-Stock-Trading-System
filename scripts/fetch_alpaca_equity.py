"""
Fetch actual daily equity from Alpaca portfolio history API
and display it, then regenerate the P&L chart.
"""
import sys, os

# Allow imports from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from datetime import datetime, timedelta
from alpaca.trading.client import TradingClient
from config import ALPACA

# ── Connect to Alpaca ──
client = TradingClient(
    ALPACA["api_key"],
    ALPACA["secret_key"],
    paper=True
)

# ── Fetch portfolio history (daily bars, Aug 9 -> today) ──
params = {
    "period": "1M",       # 1 month lookback (covers Aug 9 to today)
    "timeframe": "1D",    # daily snapshots
}

print("Fetching portfolio history from Alpaca...")
data = client.get("/account/portfolio/history", params)

# Parse the response
timestamps = data["timestamp"]
equities   = data["equity"]
pnls       = data["profit_loss"]
pnl_pcts   = data["profit_loss_pct"]

df = pd.DataFrame({
    "timestamp": pd.to_datetime(timestamps, unit="s"),
    "equity": equities,
    "profit_loss": pnls,
    "profit_loss_pct": pnl_pcts,
})

# Filter to Aug 9 onwards
df = df[df["timestamp"] >= "2026-08-09"].reset_index(drop=True)
df["date"] = df["timestamp"].dt.strftime("%Y-%m-%d (%a)")

print("\n" + "=" * 70)
print("  ALPACA PORTFOLIO HISTORY - Daily Equity Snapshots")
print("=" * 70)
print(f"{'Date':<22} {'Equity':>14} {'Daily P&L':>14} {'P&L %':>10}")
print("-" * 70)
for _, row in df.iterrows():
    print(f"  {row['date']:<20} ${row['equity']:>12,.2f} ${row['profit_loss']:>12,.2f} {row['profit_loss_pct']:>9.4f}%")
print("-" * 70)
print(f"  {'TOTAL':.<20} ${df['equity'].iloc[-1]:>12,.2f} ${df['profit_loss'].iloc[-1]:>12,.2f} {df['profit_loss_pct'].iloc[-1]:>9.4f}%")
print()

# Save for chart generation
out_csv = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "outputs", "alpaca_equity_history.csv")
df.to_csv(out_csv, index=False)
print(f"Saved to: {out_csv}")
