import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from datetime import datetime
import os

# Load real Alpaca data
df = pd.read_csv("outputs/alpaca_equity_history.csv")
df["date"] = pd.to_datetime(df["timestamp"])
df = df.sort_values("date").reset_index(drop=True)

# Add day labels
df["day_label"] = [f"Day {i+1}\n{d.strftime('%b %d')}" 
                   for i, d in enumerate(df["date"])]

# Session annotations (what happened each day)
session_notes = {
    "2026-08-11": "First trade\n(NVDA bought)",
    "2026-08-12": "100-ticker\nchaos",
    "2026-08-13": "Rebuilt\nclean",
    "2026-08-14": "5-ticker\nstable",
    "2026-08-15": "Hourly\ncandles",
    "2026-08-18": "Bracket\ntuning",
    "2026-08-19": "RSI\nexperiment",
    "2026-08-20": "Simple\nreset",
}

# Add session notes
df["note"] = df["timestamp"].map(
    lambda x: session_notes.get(x, "")
)

# ── Figure setup ──
fig, (ax1, ax2) = plt.subplots(
    2, 1, figsize=(13, 8),
    height_ratios=[2.2, 1],
    facecolor="#0d1117"
)
for ax in (ax1, ax2):
    ax.set_facecolor("#0d1117")
    ax.tick_params(colors="#c9d1d9", labelsize=8)
    for spine in ax.spines.values():
        spine.set_color("#30363d")
    ax.grid(True, color="#21262d", linewidth=0.6, alpha=0.8)

x = range(len(df))
equity = df["equity"].tolist()
pnl = df["daily_pnl"].tolist()
starting = 100000.0

# ── Top panel: Equity curve ──
ax1.plot(x, equity, color="#58a6ff", linewidth=2.2,
         marker="o", markersize=7,
         markerfacecolor="#58a6ff",
         markeredgecolor="#0d1117",
         markeredgewidth=1.5, zorder=4)

ax1.axhline(starting, color="#8b949e", linestyle="--",
            linewidth=1.0, alpha=0.7,
            label=f"Starting equity ($100,000)")

# Shade below starting equity (loss zone)
ax1.fill_between(x, equity, starting,
                 where=[e < starting for e in equity],
                 color="#f85149", alpha=0.10,
                 interpolate=True)

# Annotate each point
for i, (xi, eq, note) in enumerate(
        zip(x, equity, df["note"])):
    diff = eq - starting
    sign = "+" if diff >= 0 else ""
    ax1.annotate(
        f"${eq:,.0f}\n({sign}{diff:.0f})",
        (xi, eq),
        textcoords="offset points",
        xytext=(0, 12),
        ha="center", fontsize=7.5,
        color="#c9d1d9"
    )

ax1.set_ylabel("Account Equity ($)",
               color="#c9d1d9", fontsize=10)
ax1.set_title(
    "Autonomous Trading Agent — Paper Trading Performance\n"
    "Live Alpaca Paper Account | Aug 2026",
    color="#f0f6fc", fontsize=13,
    fontweight="bold", pad=16
)
ax1.legend(loc="lower left",
           facecolor="#161b22",
           edgecolor="#30363d",
           labelcolor="#c9d1d9",
           fontsize=9)
ax1.set_xticks(list(x))
ax1.set_xticklabels(df["day_label"], fontsize=8,
                    color="#8b949e")

# ── Bottom panel: Daily P&L bars ──
bar_colors = ["#3fb950" if p >= 0 else "#f85149"
              for p in pnl]
bars = ax2.bar(x, pnl, color=bar_colors,
               width=0.55, zorder=3)

ax2.axhline(0, color="#8b949e", linewidth=0.8)
ax2.set_ylabel("Daily P&L ($)",
               color="#c9d1d9", fontsize=10)
ax2.set_xticks(list(x))
ax2.set_xticklabels(df["day_label"], fontsize=8,
                    color="#8b949e")

# Annotate bars
for xi, p in zip(x, pnl):
    offset = 1.5 if p >= 0 else -12
    ax2.annotate(
        f"${p:+.2f}",
        (xi, p),
        textcoords="offset points",
        xytext=(0, offset),
        ha="center", fontsize=8,
        color="#c9d1d9"
    )

# ── KPI box (top right of equity chart) ──
total_pnl = sum(pnl)
win_days = sum(1 for p in pnl if p > 0)
loss_days = sum(1 for p in pnl if p < 0)
best = max(pnl)
worst = min(pnl)
avg = total_pnl / len(pnl)
current_eq = equity[-1]

kpi_text = (
    f"Starting Capital: $100,000\n"
    f"Current Equity:   ${current_eq:,.2f}\n"
    f"Total P&L:        ${total_pnl:+,.2f}\n"
    f"Avg Daily P&L:    ${avg:+,.2f}\n"
    f"Best Day:         ${best:+,.2f}\n"
    f"Worst Day:        ${worst:+,.2f}\n"
    f"Win Days: {win_days} | Loss Days: {loss_days}\n"
    f"Sessions: {len(df)}"
)
ax1.text(
    0.99, 0.97, kpi_text,
    transform=ax1.transAxes,
    fontsize=8, color="#c9d1d9",
    verticalalignment="top",
    horizontalalignment="right",
    bbox=dict(
        boxstyle="round,pad=0.5",
        facecolor="#161b22",
        edgecolor="#30363d",
        alpha=0.9
    ),
    fontfamily="monospace"
)

# ── Footer ──
fig.text(
    0.5, 0.01,
    "Paper Trading on Alpaca  •  "
    f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}  •  "
    "github.com/Shashwat-911/Autonomous-Stock-Trading-System",
    ha="center", fontsize=8,
    color="#6e7681"
)

plt.tight_layout(rect=[0, 0.03, 1, 1])
os.makedirs("outputs", exist_ok=True)
plt.savefig(
    "outputs/daily_pnl_chart.png",
    dpi=160,
    facecolor=fig.get_facecolor(),
    bbox_inches="tight"
)
print("Chart saved: outputs/daily_pnl_chart.png")
