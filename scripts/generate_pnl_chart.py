import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.patches as mpatches
import numpy as np
from datetime import datetime

# ── Load data ──
df = pd.read_csv("outputs/alpaca_equity_history.csv")
df["date"] = pd.to_datetime(df["timestamp"])
df = df.sort_values("date").reset_index(drop=True)

df["day_label"] = [
    f"Day {i+1}\n{d.strftime('%b %d')}"
    for i, d in enumerate(df["date"])
]

session_notes = {
    "2026-08-11": "First Trade\nNVDA Bought",
    "2026-08-12": "100-Ticker\nChaos",
    "2026-08-13": "Rebuilt\nClean",
    "2026-08-14": "5-Ticker\nStable",
    "2026-08-17": "Multi-ticker\nSession",
    "2026-08-18": "Bracket\nTuning",
    "2026-08-19": "RSI\nExperiment",
    "2026-08-20": "Simple\nReset",
    "2026-08-21": "Disciplined\nHOLD",
    "2026-08-24": "Post-cleanup\nFresh Start",
    "2026-08-25": "Pre-earnings\nWatch",
    "2026-08-26": "NVDA\nEarnings Day",
    "2026-08-27": "Momentum\nStrategy Live",
    "2026-08-28": "Whipsaw\nLearning Day",
    "2026-08-31": "Sideways\nMarket HOLD",
    "2026-09-01": "RSI Raised\n40→45 Live",
    "2026-09-02": "RSI Raised\n45 Live",
    "2026-09-03": "Active\nSession",
    "2026-09-04": "Bullish Trend\nBest Day (+$178)",
}
df["note"] = df["timestamp"].map(
    lambda x: session_notes.get(x, ""))

# ── Computed metrics ──
starting = 100000.0
equity = df["equity"].tolist()
pnl = df["daily_pnl"].tolist()
x = list(range(len(df)))

total_pnl = sum(pnl)
win_days = sum(1 for p in pnl if p > 0)
loss_days = sum(1 for p in pnl if p < 0)
flat_days = sum(1 for p in pnl if p == 0)
best = max(pnl)
worst = min(pnl)
avg_pnl = total_pnl / len(pnl)
current_eq = equity[-1]
total_return_pct = ((current_eq - starting) / starting) * 100
win_rate = (win_days / len(pnl)) * 100

# Max drawdown
peak = starting
max_dd = 0
for e in equity:
    if e > peak:
        peak = e
    dd = ((peak - e) / peak) * 100
    if dd > max_dd:
        max_dd = dd

# Cumulative P&L line
cum_pnl = np.cumsum(pnl).tolist()

# ── Figure with 3 panels ──
fig = plt.figure(figsize=(15, 10), facecolor="#0d1117")
gs = gridspec.GridSpec(
    3, 1,
    height_ratios=[2.5, 1, 0.8],
    hspace=0.08,
    figure=fig
)
ax1 = fig.add_subplot(gs[0])  # Equity curve
ax2 = fig.add_subplot(gs[1])  # Daily P&L bars
ax3 = fig.add_subplot(gs[2])  # Cumulative P&L line

for ax in (ax1, ax2, ax3):
    ax.set_facecolor("#0d1117")
    ax.tick_params(colors="#c9d1d9", labelsize=8)
    for spine in ax.spines.values():
        spine.set_color("#30363d")
    ax.grid(True, color="#21262d", linewidth=0.5, alpha=0.8)
    ax.set_xlim(-0.5, len(df) - 0.5)

# ── Panel 1: Equity curve ──
ax1.plot(x, equity, color="#58a6ff", linewidth=2.5,
         marker="o", markersize=7,
         markerfacecolor="#58a6ff",
         markeredgecolor="#0d1117",
         markeredgewidth=2, zorder=4, label="Portfolio Equity")

ax1.axhline(starting, color="#8b949e", linestyle="--",
            linewidth=1.0, alpha=0.6,
            label="Starting Equity ($100,000)")

ax1.fill_between(x, equity, starting,
                 where=[e < starting for e in equity],
                 color="#f85149", alpha=0.12, interpolate=True,
                 label="Drawdown Zone")

ax1.fill_between(x, equity, starting,
                 where=[e >= starting for e in equity],
                 color="#3fb950", alpha=0.08, interpolate=True)

# Annotate equity points
for i, (xi, eq) in enumerate(zip(x, equity)):
    diff = eq - starting
    sign = "+" if diff >= 0 else ""
    ax1.annotate(
        f"${eq:,.0f}\n({sign}{diff:.0f})",
        (xi, eq),
        textcoords="offset points",
        xytext=(0, 14),
        ha="center", fontsize=7,
        color="#c9d1d9"
    )

# Annotate session notes below x axis
for i, (xi, note) in enumerate(zip(x, df["note"])):
    if note:
        ax1.annotate(
            note,
            (xi, min(equity) - 30),
            textcoords="data",
            ha="center", fontsize=6,
            color="#6e7681",
            annotation_clip=False
        )

ax1.set_ylabel("Account Equity ($)",
               color="#c9d1d9", fontsize=10)
ax1.set_title(
    "Autonomous Trading Agent  --  Paper Trading Performance\n"
    "Live Alpaca Paper Account  |  Aug–Sep 2026  |  NVDA Strategy",
    color="#f0f6fc", fontsize=13,
    fontweight="bold", pad=14
)
ax1.legend(loc="lower left",
           facecolor="#161b22",
           edgecolor="#30363d",
           labelcolor="#c9d1d9",
           fontsize=8)
ax1.set_xticks(x)
ax1.set_xticklabels(df["day_label"], fontsize=7.5,
                    color="#8b949e")

# ── KPI box top right ──
kpi_lines = [
    f"Starting Capital:  $100,000",
    f"Current Equity:    ${current_eq:,.2f}",
    f"Total P&L:         ${total_pnl:+,.2f}",
    f"Total Return:      {total_return_pct:+.3f}%",
    f"Avg Daily P&L:     ${avg_pnl:+,.2f}",
    f"Best Day:          ${best:+,.2f}",
    f"Worst Day:         ${worst:+,.2f}",
    f"Max Drawdown:      -{max_dd:.3f}%",
    f"Win Rate:          {win_rate:.1f}%",
    f"Win / Loss / Flat: {win_days} / {loss_days} / {flat_days}",
    f"Sessions:          {len(df)}",
]
kpi_text = "\n".join(kpi_lines)
ax1.text(
    0.995, 0.97, kpi_text,
    transform=ax1.transAxes,
    fontsize=7.8, color="#c9d1d9",
    verticalalignment="top",
    horizontalalignment="right",
    bbox=dict(
        boxstyle="round,pad=0.6",
        facecolor="#161b22",
        edgecolor="#30363d",
        alpha=0.92
    ),
    fontfamily="monospace"
)

# ── Panel 2: Daily P&L bars ──
bar_colors = []
for p in pnl:
    if p > 0:
        bar_colors.append("#3fb950")
    elif p < 0:
        bar_colors.append("#f85149")
    else:
        bar_colors.append("#8b949e")

bars = ax2.bar(x, pnl, color=bar_colors,
               width=0.6, zorder=3,
               edgecolor="#0d1117", linewidth=0.5)
ax2.axhline(0, color="#8b949e", linewidth=0.8)
ax2.set_ylabel("Daily P&L ($)",
               color="#c9d1d9", fontsize=9)
ax2.set_xticks(x)
ax2.set_xticklabels(df["day_label"], fontsize=7.5,
                    color="#8b949e")

for xi, p in zip(x, pnl):
    if abs(p) > 1:
        offset = 2 if p >= 0 else -14
        ax2.annotate(
            f"${p:+.2f}",
            (xi, p),
            textcoords="offset points",
            xytext=(0, offset),
            ha="center", fontsize=7.5,
            color="#c9d1d9"
        )

# ── Panel 3: Cumulative P&L line ──
cum_colors = ["#3fb950" if c >= 0 else "#f85149"
              for c in cum_pnl]
ax3.plot(x, cum_pnl, color="#e3b341", linewidth=1.8,
         marker="o", markersize=5,
         markerfacecolor="#e3b341",
         markeredgecolor="#0d1117",
         markeredgewidth=1.5, zorder=4,
         label="Cumulative P&L")
ax3.fill_between(x, cum_pnl, 0,
                 where=[c < 0 for c in cum_pnl],
                 color="#f85149", alpha=0.10,
                 interpolate=True)
ax3.fill_between(x, cum_pnl, 0,
                 where=[c >= 0 for c in cum_pnl],
                 color="#3fb950", alpha=0.10,
                 interpolate=True)
ax3.axhline(0, color="#8b949e", linewidth=0.8,
            linestyle="--", alpha=0.6)
ax3.set_ylabel("Cum. P&L ($)",
               color="#c9d1d9", fontsize=9)
ax3.set_xticks(x)
ax3.set_xticklabels(df["day_label"], fontsize=7.5,
                    color="#8b949e")
ax3.legend(loc="lower left",
           facecolor="#161b22",
           edgecolor="#30363d",
           labelcolor="#c9d1d9",
           fontsize=8)

for xi, c in zip(x, cum_pnl):
    ax3.annotate(
        f"${c:+.0f}",
        (xi, c),
        textcoords="offset points",
        xytext=(0, 6 if c >= 0 else -12),
        ha="center", fontsize=7,
        color="#c9d1d9"
    )

# ── Footer ──
fig.text(
    0.5, 0.005,
    f"Paper Trading on Alpaca  |  "
    f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}  |  "
    "github.com/Shashwat-911/Autonomous-Stock-Trading-System",
    ha="center", fontsize=8,
    color="#6e7681"
)

os.makedirs("outputs", exist_ok=True)
plt.savefig(
    "outputs/daily_pnl_chart.png",
    dpi=160,
    facecolor=fig.get_facecolor(),
    bbox_inches="tight"
)
print("Chart saved: outputs/daily_pnl_chart.png")
