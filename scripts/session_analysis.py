"""
session_analysis.py -- Diagnostic performance report across all trading sessions.

Reads outputs/trade_history.csv and produces:
  1. Per-session performance table
  2. Best / worst day identification
  3. ASCII equity curve
  4. Trend assessment (improving vs. degrading)
"""

import sys
import os
import math

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TRADE_HISTORY = os.path.join(PROJECT_ROOT, "outputs", "trade_history.csv")

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
if not os.path.exists(TRADE_HISTORY):
    print(f"  [ERROR] {TRADE_HISTORY} not found.")
    sys.exit(1)

df = pd.read_csv(TRADE_HISTORY)

# Drop empty trailing rows
df = df.dropna(subset=["session_timestamp"])

# Parse timestamp and derive day label
df["timestamp"] = pd.to_datetime(df["session_timestamp"])
df = df.sort_values("timestamp").reset_index(drop=True)

# Compute daily return (change between consecutive ending equities)
df["daily_return_pct"] = df["ending_equity"].pct_change() * 100
df.loc[0, "daily_return_pct"] = (
    (df.loc[0, "ending_equity"] - df.loc[0, "starting_equity"])
    / df.loc[0, "starting_equity"]
    * 100
)

# Avg trade = expectancy (already in the CSV)
# Label sessions as Day 1, Day 2, ...
df["day_label"] = [f"Day {i+1}" for i in range(len(df))]

# ---------------------------------------------------------------------------
# 1. Performance Table
# ---------------------------------------------------------------------------
print("\n" + "=" * 80)
print("  SESSION-BY-SESSION PERFORMANCE REPORT")
print("=" * 80)

header = (
    f"  {'Day':<7} | {'Date':<12} | {'Equity':>10} | {'Daily Ret':>10} | "
    f"{'Win Rate':>9} | {'PF':>6} | {'Avg Trade':>10}"
)
print(header)
print("  " + "-" * 76)

for _, row in df.iterrows():
    date_str = row["timestamp"].strftime("%Y-%m-%d")
    equity = row["ending_equity"]
    daily_ret = row["daily_return_pct"]
    win_rate = row["win_rate"] * 100
    pf = row["profit_factor"]
    avg_trade = row["expectancy"]

    ret_arrow = "+" if daily_ret > 0 else ("-" if daily_ret < 0 else "=")

    print(
        f"  {row['day_label']:<7} | {date_str:<12} | "
        f"${equity:>9,.2f} | {ret_arrow} {daily_ret:>+7.3f}% | "
        f"{win_rate:>7.1f}% | {pf:>5.2f} | ${avg_trade:>9.2f}"
    )

# ---------------------------------------------------------------------------
# 2. Best and Worst Day
# ---------------------------------------------------------------------------
best_idx = df["daily_return_pct"].idxmax()
worst_idx = df["daily_return_pct"].idxmin()

print("\n" + "-" * 80)
print(f"  [BEST]  {df.loc[best_idx, 'day_label']} "
      f"({df.loc[best_idx, 'timestamp'].strftime('%Y-%m-%d')}) "
      f"-> {df.loc[best_idx, 'daily_return_pct']:+.3f}%  "
      f"Equity: ${df.loc[best_idx, 'ending_equity']:,.2f}  "
      f"Win Rate: {df.loc[best_idx, 'win_rate']*100:.1f}%")
print(f"  [WORST] {df.loc[worst_idx, 'day_label']} "
      f"({df.loc[worst_idx, 'timestamp'].strftime('%Y-%m-%d')}) "
      f"-> {df.loc[worst_idx, 'daily_return_pct']:+.3f}%  "
      f"Equity: ${df.loc[worst_idx, 'ending_equity']:,.2f}  "
      f"Win Rate: {df.loc[worst_idx, 'win_rate']*100:.1f}%")

# ---------------------------------------------------------------------------
# 3. ASCII Equity Curve
# ---------------------------------------------------------------------------
print("\n" + "=" * 80)
print("  EQUITY CURVE")
print("=" * 80)

equities = [df.loc[0, "starting_equity"]] + df["ending_equity"].tolist()
labels = ["Start"] + df["day_label"].tolist()

eq_min = min(equities)
eq_max = max(equities)

CHART_WIDTH = 50
# Avoid division by zero
eq_range = eq_max - eq_min if eq_max != eq_min else 1.0

for label, eq in zip(labels, equities):
    bar_len = int((eq - eq_min) / eq_range * CHART_WIDTH)
    bar = "#" * max(bar_len, 1)
    marker = " <<" if eq == equities[-1] else ""
    print(f"  {label:<7} ${eq:>10,.2f} |{bar}{marker}")

# ---------------------------------------------------------------------------
# 4. Trend Assessment
# ---------------------------------------------------------------------------
print("\n" + "=" * 80)
print("  STRATEGY TREND ASSESSMENT")
print("=" * 80)

# Metrics to track
equities_only = df["ending_equity"].tolist()
win_rates = df["win_rate"].tolist()
profit_factors = df["profit_factor"].tolist()
expectancies = df["expectancy"].tolist()

def trend_direction(values):
    """Simple linear slope direction."""
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n
    num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    den = sum((i - x_mean) ** 2 for i in range(n))
    return num / den if den != 0 else 0.0

eq_slope = trend_direction(equities_only)
wr_slope = trend_direction(win_rates)
pf_slope = trend_direction(profit_factors)
exp_slope = trend_direction(expectancies)

print(f"\n  Equity trend:        {'DECLINING [-]' if eq_slope < 0 else 'IMPROVING [+]' if eq_slope > 0 else 'FLAT [=]'}  (slope: {eq_slope:+.2f}/day)")
print(f"  Win rate trend:      {'DECLINING [-]' if wr_slope < 0 else 'IMPROVING [+]' if wr_slope > 0 else 'FLAT [=]'}  (slope: {wr_slope:+.4f}/day)")
print(f"  Profit factor trend: {'DECLINING [-]' if pf_slope < 0 else 'IMPROVING [+]' if pf_slope > 0 else 'FLAT [=]'}  (slope: {pf_slope:+.4f}/day)")
print(f"  Expectancy trend:    {'DECLINING [-]' if exp_slope < 0 else 'IMPROVING [+]' if exp_slope > 0 else 'FLAT [=]'}  (slope: ${exp_slope:+.2f}/day)")

# Overall verdict
declining_count = sum(1 for s in [eq_slope, wr_slope, pf_slope, exp_slope] if s < 0)
improving_count = sum(1 for s in [eq_slope, wr_slope, pf_slope, exp_slope] if s > 0)

print()
if declining_count >= 3:
    print("  +--------------------------------------------------------------+")
    print("  |  VERDICT: STRATEGY IS GETTING WORSE                          |")
    print("  |  Multiple metrics are trending downward. Changes needed.     |")
    print("  +--------------------------------------------------------------+")
elif improving_count >= 3:
    print("  +--------------------------------------------------------------+")
    print("  |  VERDICT: STRATEGY IS IMPROVING                              |")
    print("  |  Most metrics are trending upward. Stay the course.          |")
    print("  +--------------------------------------------------------------+")
else:
    print("  +--------------------------------------------------------------+")
    print("  |  VERDICT: STRATEGY IS MIXED / FLAT                           |")
    print("  |  Some metrics improving, some declining. Investigation       |")
    print("  |  needed to isolate specific issues.                          |")
    print("  +--------------------------------------------------------------+")

# ---------------------------------------------------------------------------
# 5. Key Observations
# ---------------------------------------------------------------------------
print("\n" + "=" * 80)
print("  KEY OBSERVATIONS")
print("=" * 80)

total_loss = df.loc[0, "starting_equity"] - df.iloc[-1]["ending_equity"]
print(f"\n  * Total P&L from start: -${total_loss:,.2f} ({-total_loss/df.loc[0,'starting_equity']*100:+.3f}%)")
print(f"  * Current win rate: {df.iloc[-1]['win_rate']*100:.1f}% (started at {df.iloc[0]['win_rate']*100:.1f}%)")
print(f"  * Current profit factor: {df.iloc[-1]['profit_factor']:.2f} (started at {df.iloc[0]['profit_factor']:.2f})")
print(f"  * Avg slippage: {df.iloc[-1]['avg_slippage_pct']:.1f}%  <-- NOTE: this is abnormally high")
print(f"  * Total trades across all sessions: {int(df.iloc[-1]['total_trades'])}")

# Check if loss per trade is growing
if abs(df.iloc[-1]["avg_loss"]) > abs(df.iloc[0]["avg_loss"]):
    print(f"  * [!] Avg loss per trade GROWING: ${df.iloc[0]['avg_loss']:.2f} -> ${df.iloc[-1]['avg_loss']:.2f}")
else:
    print(f"  * Avg loss per trade stable: ${df.iloc[0]['avg_loss']:.2f} -> ${df.iloc[-1]['avg_loss']:.2f}")

if df.iloc[-1]["avg_gain"] > df.iloc[0]["avg_gain"]:
    print(f"  * Avg gain per trade improving: ${df.iloc[0]['avg_gain']:.2f} -> ${df.iloc[-1]['avg_gain']:.2f}")
else:
    print(f"  * [!] Avg gain per trade DECLINING: ${df.iloc[0]['avg_gain']:.2f} -> ${df.iloc[-1]['avg_gain']:.2f}")

print()
