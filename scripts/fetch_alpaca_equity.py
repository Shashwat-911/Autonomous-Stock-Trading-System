"""
fetch_alpaca_equity.py
======================
Fetches the full portfolio equity history from Alpaca's Portfolio History API
and writes / updates outputs/alpaca_equity_history.csv.

Usage:
  python scripts/fetch_alpaca_equity.py            # fetch full history
  python scripts/fetch_alpaca_equity.py --today    # fetch today's snapshot only (post-session use)

Design:
  - Dates are fully dynamic — no hardcoded start/end.
  - PROJECT_START_DATE is the only constant to set (first day of paper trading).
  - Safe to run multiple times: deduplicates rows by date before writing.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config
import pandas as pd
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetPortfolioHistoryRequest
from datetime import datetime, timezone, timedelta

# ── Constants ──────────────────────────────────────────────────────────────────
PROJECT_START_DATE = "2026-08-09"   # First day of paper trading — update if you ever reset
OUTPUT_PATH        = "outputs/alpaca_equity_history.csv"

# ── Parse args ─────────────────────────────────────────────────────────────────
today_only = "--today" in sys.argv

# ── Date range ─────────────────────────────────────────────────────────────────
now_utc   = datetime.now(timezone.utc)
today_str = now_utc.strftime("%Y-%m-%d")

# When --today: fetch just the last 3 days (catches today even if market closed late)
start_str = (now_utc - timedelta(days=3)).strftime("%Y-%m-%d") if today_only else PROJECT_START_DATE
end_str   = today_str

print(f"Fetching Alpaca equity history: {start_str} → {end_str}")

# ── Alpaca client ──────────────────────────────────────────────────────────────
client = TradingClient(
    config.ALPACA["api_key"],
    config.ALPACA["secret_key"],
    paper=True
)

history = client.get_portfolio_history(
    GetPortfolioHistoryRequest(
        timeframe="1D",
        start=start_str,
        end=end_str,
        extended_hours=False
    )
)

# ── Parse API response ─────────────────────────────────────────────────────────
new_rows = []
for ts, eq, pl, plp in zip(
    history.timestamp, history.equity,
    history.profit_loss, history.profit_loss_pct
):
    if eq is None or eq == 0:
        continue
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    if dt.weekday() >= 5:          # skip weekends
        continue
    new_rows.append({
        "timestamp":    dt.strftime("%Y-%m-%d"),
        "equity":       round(float(eq), 2),
        "daily_pnl":    round(float(pl), 2),
        "daily_pnl_pct": round(float(plp) * 100, 4),
    })

new_df = pd.DataFrame(new_rows)

# ── Merge with existing CSV (deduplicate by date) ─────────────────────────────
os.makedirs("outputs", exist_ok=True)

if os.path.exists(OUTPUT_PATH) and not new_df.empty:
    existing_df = pd.read_csv(OUTPUT_PATH)
    # Combine, keep latest values for any duplicate dates (API is source of truth)
    merged = pd.concat([existing_df, new_df], ignore_index=True)
    merged = merged.drop_duplicates(subset=["timestamp"], keep="last")
    merged = merged.sort_values("timestamp").reset_index(drop=True)
    merged.to_csv(OUTPUT_PATH, index=False)
    df = merged
else:
    new_df.to_csv(OUTPUT_PATH, index=False)
    df = new_df

# ── Summary ───────────────────────────────────────────────────────────────────
print("\nEquity history saved to:", OUTPUT_PATH)
print(df.to_string(index=False))
print(f"\nTotal P&L:  ${df['daily_pnl'].sum():.2f}")
print(f"Win days:   {(df['daily_pnl'] > 0).sum()}")
print(f"Loss days:  {(df['daily_pnl'] < 0).sum()}")
print(f"Flat days:  {(df['daily_pnl'] == 0).sum()}")
print(f"Sessions:   {len(df)}")
print(f"Current equity: ${df['equity'].iloc[-1]:,.2f}")
