"""
Generate a professional daily P&L chart from trade_history.csv
for the GitHub README.
"""

import csv
import os
from datetime import datetime

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

# ---------- paths ----------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRADE_CSV = os.path.join(BASE_DIR, "outputs", "trade_history.csv")
OUT_PATH  = os.path.join(BASE_DIR, "outputs", "daily_pnl_chart.png")

# ---------- read data ----------
raw_rows = []
with open(TRADE_CSV, newline="") as f:
    reader = csv.DictReader(f)
    for r in reader:
        if not r["session_timestamp"].strip():
            continue
        ts   = datetime.fromisoformat(r["session_timestamp"])
        date = ts.strftime("%b %d")           # e.g. "Aug 12"
        end_eq   = float(r["ending_equity"])
        raw_rows.append({
            "date": date,
            "date_full": ts.strftime("%Y-%m-%d"),
            "end_eq": end_eq,
            "total_return_pct": float(r["total_return_pct"]),
            "win_rate": float(r["win_rate"]) * 100,
            "total_trades": int(r["total_trades"]),
            "winning_trades": int(r["winning_trades"]),
            "losing_trades": int(r["losing_trades"]),
        })

# Compute day-over-day P&L (starting_equity is always 100000 in CSV,
# so ending_equity already represents cumulative equity snapshot)
INITIAL_CAPITAL = 100_000.0
rows = []
for i, r in enumerate(raw_rows):
    prev_eq = INITIAL_CAPITAL if i == 0 else raw_rows[i-1]["end_eq"]
    daily_pnl = r["end_eq"] - prev_eq
    rows.append({**r, "daily_pnl": daily_pnl})

# Label sessions as Day 1, Day 2, ...
session_labels = [f"Day {i+1}\n({r['date']})" for i, r in enumerate(rows)]
daily_pnls     = [r["daily_pnl"] for r in rows]
cumulative     = list(np.cumsum(daily_pnls))
colors         = ["#00e676" if p >= 0 else "#ff5252" for p in daily_pnls]

# ---------- style ----------
plt.style.use("dark_background")
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 9), gridspec_kw={"height_ratios": [2, 1]},
                                sharex=True)
fig.patch.set_facecolor("#0d1117")

# ── TOP: Cumulative equity curve ──
ax1.set_facecolor("#0d1117")
ax1.fill_between(range(len(cumulative)), cumulative, alpha=0.15, color="#58a6ff")
ax1.plot(range(len(cumulative)), cumulative, color="#58a6ff", linewidth=2.5,
         marker="o", markersize=8, markerfacecolor="#58a6ff", markeredgecolor="white",
         markeredgewidth=1.5, zorder=5)

# Annotate each point with dollar value
for i, (val, label) in enumerate(zip(cumulative, session_labels)):
    offset = 12 if val >= 0 else -18
    ax1.annotate(f"${val:+,.0f}", (i, val), textcoords="offset points",
                 xytext=(0, offset), ha="center", fontsize=9, fontweight="bold",
                 color="white", 
                 bbox=dict(boxstyle="round,pad=0.3", facecolor="#21262d", edgecolor="#30363d",
                           alpha=0.9))

ax1.axhline(y=0, color="#484f58", linewidth=1, linestyle="--", alpha=0.6)
ax1.set_ylabel("Cumulative P&L ($)", fontsize=13, fontweight="bold", color="white", labelpad=10)
ax1.set_title("Autonomous Trading Agent  --  Daily Performance", fontsize=18,
              fontweight="bold", color="white", pad=20)
ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:+,.0f}"))
ax1.tick_params(colors="#8b949e", labelsize=10)
ax1.spines["top"].set_visible(False)
ax1.spines["right"].set_visible(False)
ax1.spines["left"].set_color("#30363d")
ax1.spines["bottom"].set_color("#30363d")
ax1.grid(axis="y", color="#21262d", linewidth=0.8, alpha=0.5)

# ── BOTTOM: Daily P&L bar chart ──
ax2.set_facecolor("#0d1117")
bars = ax2.bar(range(len(daily_pnls)), daily_pnls, color=colors, width=0.55,
               edgecolor="none", alpha=0.9, zorder=3)

# Add glow effect for bars
for bar, color in zip(bars, colors):
    ax2.bar(bar.get_x() + bar.get_width()/2, bar.get_height(), width=0.7,
            color=color, alpha=0.08, zorder=2)

# Annotate bars
for i, val in enumerate(daily_pnls):
    offset = 8 if val >= 0 else -14
    ax2.annotate(f"${val:+,.0f}", (i, val), textcoords="offset points",
                 xytext=(0, offset), ha="center", fontsize=9, fontweight="bold",
                 color=colors[i])

ax2.axhline(y=0, color="#484f58", linewidth=1, linestyle="--", alpha=0.6)
ax2.set_ylabel("Daily P&L ($)", fontsize=13, fontweight="bold", color="white", labelpad=10)
ax2.set_xticks(range(len(session_labels)))
ax2.set_xticklabels(session_labels, fontsize=10, color="#c9d1d9")
ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:+,.0f}"))
ax2.tick_params(colors="#8b949e", labelsize=10)
ax2.spines["top"].set_visible(False)
ax2.spines["right"].set_visible(False)
ax2.spines["left"].set_color("#30363d")
ax2.spines["bottom"].set_color("#30363d")
ax2.grid(axis="y", color="#21262d", linewidth=0.8, alpha=0.5)

# ── Summary stats box ──
last = rows[-1]
total_pnl = cumulative[-1]
avg_pnl   = np.mean(daily_pnls)
best_day  = max(daily_pnls)
worst_day = min(daily_pnls)
win_days  = sum(1 for p in daily_pnls if p >= 0)
loss_days = sum(1 for p in daily_pnls if p < 0)

stats_text = (
    f"Starting Capital: $100,000\n"
    f"Current Equity: ${last['end_eq']:,.2f}\n"
    f"Total P&L: ${total_pnl:+,.2f}\n"
    f"Avg Daily P&L: ${avg_pnl:+,.2f}\n"
    f"Best Day: ${best_day:+,.2f}\n"
    f"Worst Day: ${worst_day:+,.2f}\n"
    f"Win Days: {win_days} | Loss Days: {loss_days}\n"
    f"Sessions: {len(rows)}"
)

props = dict(boxstyle="round,pad=0.8", facecolor="#161b22", edgecolor="#30363d", alpha=0.95)
ax1.text(0.98, 0.95, stats_text, transform=ax1.transAxes, fontsize=9,
         verticalalignment="top", horizontalalignment="right",
         bbox=props, color="#c9d1d9", fontfamily="monospace",
         linespacing=1.6)

# ── Footer ──
fig.text(0.5, 0.01,
         f"Paper Trading on Alpaca  •  Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}  •  github.com/Shashwat-911/Autonomous-Stock-Trading-System",
         ha="center", fontsize=9, color="#484f58", fontstyle="italic")

plt.tight_layout(rect=[0, 0.03, 1, 1])
plt.savefig(OUT_PATH, dpi=200, bbox_inches="tight", facecolor="#0d1117", edgecolor="none")
print(f"Chart saved to: {OUT_PATH}")
plt.close()
