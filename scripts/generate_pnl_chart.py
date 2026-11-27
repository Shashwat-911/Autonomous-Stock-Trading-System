"""Original performance-chart design, fed by validated measurement v2."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import json
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from analytics.reporting import latest_report


def main():
    folder = latest_report()
    summary = json.loads((folder / "performance_summary.json").read_text(encoding="utf-8"))
    df = pd.read_csv(folder / "daily_account_measurement.csv")
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df["day_label"] = [f"Day {i+1}\n{d.strftime('%b %d')}" for i,d in enumerate(df["date"])]
    df["note"] = ["Equity pending" if pd.isna(r["equity"]) else "" for _,r in df.iterrows()]
    starting = float(summary["lifetime_bridge"]["funding_net"])
    equity = df["equity"].tolist()
    pnl = df["gross_realized_pnl"].tolist()
    x = list(range(len(df)))
    total_pnl = sum(pnl)
    win_days = sum(p > 0 for p in pnl)
    loss_days = sum(p < 0 for p in pnl)
    flat_days = sum(p == 0 for p in pnl)
    best, worst = max(pnl), min(pnl)
    avg_pnl = total_pnl / len(pnl)
    current_eq = float(summary["current_account_equity"])
    win_rate = 100 * win_days / len(pnl)
    cum_pnl = np.cumsum(pnl).tolist()
    period = f"{df['date'].iloc[0]:%b %d}–{df['date'].iloc[-1]:%b %d, %Y}"

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
                label=f"Retained Funding (${starting:,.0f})")

    ax1.fill_between(x, equity, starting,
                     where=[e < starting for e in equity],
                     color="#f85149", alpha=0.12, interpolate=True,
                     label="Below Funding")

    ax1.fill_between(x, equity, starting,
                     where=[e >= starting for e in equity],
                     color="#3fb950", alpha=0.08, interpolate=True)

    # Annotate equity points
    for i, (xi, eq) in enumerate(zip(x, equity)):
        if not np.isfinite(eq):
            continue
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
                (xi, np.nanmin(equity) - 30),
                textcoords="data",
                ha="center", fontsize=6,
                color="#6e7681",
                annotation_clip=False
            )

    ax1.set_ylabel("Account Equity ($)",
                   color="#c9d1d9", fontsize=10)
    ax1.set_title(
        "Autonomous Trading Agent  --  Paper Trading Performance\n"
        f"Live Alpaca Paper Account  |  {period}  |  Mixed-version history",
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
        f"Retained Funding:  ${starting:,.0f}",
        f"Account Snapshot:  ${current_eq:,.2f}",
        f"Gross P&L:         ${total_pnl:+,.2f}",
        f"Account Fees:      ${float(summary['fees_in_date_window']):+,.2f}",
        f"Avg Daily Gross:   ${avg_pnl:+,.2f}",
        f"Best Gross Day:    ${best:+,.2f}",
        f"Worst Gross Day:   ${worst:+,.2f}",
        f"Equity Missing:    {df['equity'].isna().sum()} date(s)",
        f"Gross Up Days:     {win_rate:.1f}%",
        f"Up / Down / Flat:  {win_days} / {loss_days} / {flat_days}",
        f"Reported Dates:    {len(df)}",
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
    ax2.set_ylabel("Daily Gross P&L ($)",
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
             label="Cumulative Gross P&L")
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
    ax3.set_ylabel("Cum. Gross P&L ($)",
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
        f"Source: {summary['source_retrieved_at'][:16]} UTC  |  "
        "github.com/Shashwat-911/Autonomous-Stock-Trading-System",
        ha="center", fontsize=8,
        color="#6e7681"
    )

    path = folder / "daily_pnl_chart.png"
    plt.savefig(path, dpi=160, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    print(f"Chart saved: {path}")


if __name__ == "__main__":
    main()
