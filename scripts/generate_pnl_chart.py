"""Render broker equity and realized P&L separately from validated reporting v2."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analytics.reporting import latest_report


def main():
    import pandas as pd
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    plt.rcParams.update({
        "figure.facecolor": "#0b1017", "axes.facecolor": "#101722",
        "text.color": "#e6edf3", "axes.labelcolor": "#b8c4d2",
        "xtick.color": "#9aaabc", "ytick.color": "#9aaabc",
        "axes.edgecolor": "#2b3747", "grid.color": "#344154",
        "font.size": 10, "savefig.facecolor": "#0b1017",
    })
    folder = latest_report()
    daily = pd.read_csv(folder / "daily_account_measurement.csv")
    daily["date"] = pd.to_datetime(daily["date"])
    fig, axes = plt.subplots(3, 1, figsize=(15, 10), sharex=True, layout="constrained")
    observed = daily.dropna(subset=["equity"])
    axes[0].plot(daily["date"], daily["equity"], color="#58a6ff", linewidth=2.2, marker="o", markersize=3.5)
    axes[0].set_ylabel("Broker equity ($)")
    fig.suptitle("AUTONOMOUS TRADING AGENT  |  PAPER ACCOUNT", fontsize=19, fontweight="bold")
    axes[0].set_title("Mixed-version history • Actual broker observations • Gross execution accounting", loc="left", fontsize=11, pad=16)
    if not observed.empty:
        last = observed.iloc[-1]
        axes[0].annotate(f"Latest daily observation: ${last['equity']:,.2f} | {last['date']:%b %d}",
                         xy=(.015, .94), xycoords="axes fraction", va="top",
                         color="#58a6ff", bbox=dict(boxstyle="round,pad=.5", fc="#101722", ec="#2b3747"))
    missing = daily[daily["equity"].isna()]
    if not missing.empty:
        axes[0].text(.99, .04, f"{len(missing)} date(s) without daily equity observations; gaps are not estimated",
                     transform=axes[0].transAxes, ha="right", color="#e3b341", fontsize=9)
    axes[0].ticklabel_format(axis="y", style="plain", useOffset=False)
    pnl = daily["gross_realized_pnl"]
    axes[1].bar(daily["date"], pnl, color=["#3fb950" if v>=0 else "#f85149" for v in pnl])
    axes[1].set_ylabel("Gross realized P&L ($)")
    delta = daily["equity_change_since_prior_observation"]
    axes[2].bar(daily["date"], delta, color=["#3fb950" if v>=0 else "#f85149" for v in delta])
    axes[2].set_ylabel("Equity change ($)\nsince prior observation")
    for ax in axes:
        ax.grid(alpha=.28, linewidth=.6)
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)
    for ax in axes[1:]:
        ax.axhline(0, color="#8292a6", linewidth=.7, alpha=.7)
    axes[2].xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
    axes[2].xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    fig.supxlabel("New York dates  |  Equity changes include unrealized P&L and cash movements  |  Missing observations remain blank", fontsize=10, color="#9aaabc")
    path = folder / "account_measurement_chart.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(path)


if __name__ == "__main__":
    main()
