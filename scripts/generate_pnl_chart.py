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
    folder = latest_report()
    daily = pd.read_csv(folder / "daily_account_measurement.csv")
    daily["date"] = pd.to_datetime(daily["date"])
    fig, axes = plt.subplots(3, 1, figsize=(13, 9), sharex=True, layout="constrained")
    observed = daily.dropna(subset=["equity"])
    axes[0].plot(observed["date"], observed["equity"], color="#245b9e", linewidth=1.8)
    axes[0].set_ylabel("Broker equity ($)")
    axes[0].set_title("Mixed-version paper account | broker observations and execution accounting", loc="left")
    axes[0].ticklabel_format(axis="y", style="plain", useOffset=False)
    pnl = daily["gross_realized_pnl"]
    axes[1].bar(daily["date"], pnl, color=["#238443" if v>=0 else "#c53a35" for v in pnl])
    axes[1].set_ylabel("Gross realized P&L ($)")
    delta = daily["equity_change_since_prior_observation"]
    axes[2].bar(daily["date"], delta, color="#64748b")
    axes[2].set_ylabel("Equity change ($)\nsince prior observation")
    for ax in axes:
        ax.grid(axis="y", alpha=.2)
    axes[2].xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
    axes[2].xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    fig.supxlabel("New York dates. Equity includes unrealized P&L and cash movements; first change may be unavailable.")
    path = folder / "account_measurement_chart.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(path)


if __name__ == "__main__":
    main()
