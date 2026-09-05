"""
update_readme.py
================
Auto-updates the Daily Session Breakdown table in README.md
from the latest outputs/alpaca_equity_history.csv data.

Usage:
  python scripts/update_readme.py
"""

import pandas as pd
import json
import os
import re
from datetime import datetime, timezone


def get_session_status(date_str, pnl):
    """Return a human readable status for the session."""
    notes = {
        "2026-08-11": "First Trade - NVDA Bought",
        "2026-08-12": "100-Ticker Chaos",
        "2026-08-13": "Rebuilt Clean",
        "2026-08-14": "5-Ticker Stable",
        "2026-08-17": "Multi-ticker Session",
        "2026-08-18": "Bracket Tuning",
        "2026-08-19": "RSI Experiment",
        "2026-08-20": "Simple Reset - Profitable",
        "2026-08-21": "Disciplined HOLD",
        "2026-08-24": "Post-cleanup Fresh Start",
        "2026-08-25": "Pre-earnings Watch",
        "2026-08-26": "NVDA Earnings - Disciplined HOLD",
        "2026-08-27": "Momentum Strategy - First Live Session",
        "2026-08-28": "Momentum Whipsaw - Hold Filter Added",
        "2026-08-31": "Sideways Market - Disciplined HOLD",
        "2026-09-01": "MACD Bearish - Disciplined HOLD",
        "2026-09-02": "RSI Threshold Adjusted to 45",
        "2026-09-03": "Active Session",
        "2026-09-04": "Bullish Trend - Best Day (+0.18%)",
    }
    if date_str in notes:
        return notes[date_str]
    if pnl > 50:
        return "Profitable Session"
    elif pnl < -100:
        return "Loss Session"
    elif abs(pnl) < 1:
        return "Flat Session - Disciplined HOLD"
    else:
        return "Active Session"


def update_readme():
    # ── Paths ──────────────────────────────────────────────────────────────────
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    csv_path     = os.path.join(project_root, "outputs", "alpaca_equity_history.csv")
    readme_path  = os.path.join(project_root, "README.md")

    if not os.path.exists(csv_path):
        print(f"[ERROR] No equity history CSV found at: {csv_path}")
        return

    # ── Load equity history ────────────────────────────────────────────────────
    df = pd.read_csv(csv_path)
    df["date"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("date").reset_index(drop=True)

    # Calculate cumulative P&L and return %
    starting = 100000.0
    df["cumulative_pnl"] = df["daily_pnl"].cumsum()
    df["return_pct"]     = (df["cumulative_pnl"] / starting) * 100

    # ── Build session table rows ───────────────────────────────────────────────
    rows = []
    for i, row in df.iterrows():
        day_num    = i + 1
        date_str   = row["timestamp"]
        date_obj   = pd.to_datetime(date_str)
        date_label = date_obj.strftime("%b %d (%a)")
        equity     = row["equity"]
        daily_pnl  = row["daily_pnl"]
        cum_pnl    = row["cumulative_pnl"]
        ret_pct    = row["return_pct"]
        status     = get_session_status(date_str, daily_pnl)

        if daily_pnl > 0:
            pnl_str = f"+${daily_pnl:.2f}"
        elif daily_pnl < 0:
            pnl_str = f"-${abs(daily_pnl):.2f}"
        else:
            pnl_str = "$0.00"

        cum_str = f"+${cum_pnl:.2f}" if cum_pnl > 0 else f"-${abs(cum_pnl):.2f}"

        # Bold profitable days (>$50)
        if daily_pnl > 50:
            pnl_str = f"**{pnl_str}**"

        rows.append(
            f"| **Day {day_num}** | {date_label} | "
            f"${equity:,.2f} | {pnl_str} | "
            f"{cum_str} | {ret_pct:+.3f}% | {status} |"
        )

    # ── Summary stats ──────────────────────────────────────────────────────────
    total_pnl      = df["daily_pnl"].sum()
    current_equity = df["equity"].iloc[-1]
    win_days       = int((df["daily_pnl"] > 0).sum())
    loss_days      = int((df["daily_pnl"] < 0).sum())
    flat_days      = int((df["daily_pnl"] == 0).sum())
    best_day       = df["daily_pnl"].max()
    max_drawdown   = df["return_pct"].min()
    sessions       = len(df)
    win_rate       = (win_days / sessions * 100) if sessions > 0 else 0

    # ── Build new table block ──────────────────────────────────────────────────
    table_header = (
        "### Daily Session Breakdown\n\n"
        "| Session | Date | Ending Equity | Daily P&L | Cumulative P&L | Return (%) | Status |\n"
        "|---|---|---|---|---|---|---|"
    )
    table_body = "\n".join(rows)
    footer = (
        f"\n> **Current Equity**: ${current_equity:,.2f} "
        f"| **Total P&L**: ${total_pnl:+,.2f} "
        f"| **Best Day**: ${best_day:+,.2f} "
        f"| **Win Rate**: {win_rate:.1f}% "
        f"({win_days}W / {loss_days}L / {flat_days} Flat) "
        f"| **Max Drawdown**: {max_drawdown:.3f}% "
        f"| **Sessions**: {sessions}"
    )
    new_table = f"{table_header}\n{table_body}\n{footer}"

    # ── Read and patch README ──────────────────────────────────────────────────
    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()

    pattern = r"### Daily Session Breakdown.*?(?=\n---|\n## |\Z)"
    match   = re.search(pattern, content, flags=re.DOTALL)

    if not match:
        print("[WARNING] Could not find '### Daily Session Breakdown' section in README.")
        print("          The table was NOT updated. Check the README header exactly.")
        return

    if match.group(0).strip() == new_table.strip():
        print(f"[OK] README is already up to date with {sessions} sessions.")
        return

    new_content = content[:match.start()] + new_table + content[match.end():]
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"[OK] README updated with {sessions} sessions.")
    print(f"     Current equity : ${current_equity:,.2f}")
    print(f"     Total P&L      : ${total_pnl:+,.2f}")
    print(f"     Win / Loss / Flat: {win_days} / {loss_days} / {flat_days}")
    print(f"     Max Drawdown   : {max_drawdown:.3f}%")


if __name__ == "__main__":
    update_readme()
