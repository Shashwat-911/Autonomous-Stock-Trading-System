"""Refresh the account summary and one collapsible daily-history table."""
import csv
import json
import re
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analytics.reporting import latest_report, ROOT

START = "<!-- MEASUREMENT_V2_START -->"
END = "<!-- MEASUREMENT_V2_END -->"


def render_block(folder):
    summary = json.loads((folder/"performance_summary.json").read_text(encoding="utf-8"))
    def money(value):
        return f"${float(value):,.2f}" if value not in (None, "") else "Unavailable"
    rate = summary["win_rate"]
    lines = [START, "## Corrected account measurement", "",
        "Mixed-version account history; **not a validated baseline for the current strategy**.",
        "The earlier unverified session table is archived in docs/LEGACY_SESSION_TABLE.md.", "",
        f"Period: {summary['period_start']} through {summary['period_end']} (New York dates).",
        f"Source retrieved: {summary['source_retrieved_at']}. Report generated: {summary['generated_at']}.", "",
        f"Completed flat-to-flat episodes: **{summary['total_trades']}**; gross win rate: **{rate:.2%}**." if rate is not None else "No completed episodes in this period.",
        f"Gross expectancy: **{money(summary['expectancy'])}**. Fees are unallocated account-level costs, excluded from trade metrics.", "",
        f"Latest account snapshot: **{money(summary['current_account_equity'])}** at {summary['current_account_observation']} (separate from daily history).", "",
        "[Measurement definitions and limitations](docs/MEASUREMENT_V2.md)", END]
    return "\n".join(lines)


def render_daily_table(folder):
    with (folder/"daily_account_measurement.csv").open(encoding="utf-8", newline="") as stream:
        daily = list(csv.DictReader(stream))
    def money(value):
        return f"${float(value):,.2f}" if value not in (None, "") else "Unavailable"
    lines = ["### Daily Session Breakdown", "", "<details>", "<summary>View daily account history and session logs</summary>", "",
             "Validated account measurements (mixed strategy versions). Realized P&L excludes fees and open-position P&L.", "",
             "| Day | Date (New York) | Broker equity | Gross realized P&L | Cumulative gross realized | Equity change | Session log |",
             "|---:|---|---:|---:|---:|---:|---|"]
    from decimal import Decimal
    cumulative = Decimal(0)
    for index, row in enumerate(daily, 1):
        cumulative += Decimal(row["gross_realized_pnl"])
        log = ROOT/"outputs/logs"/("session_"+row["date"].replace("-", "_")+".txt")
        link = f"[Log]({log.relative_to(ROOT).as_posix()})" if log.exists() else "Not archived"
        lines.append(f"| {index} | {row['date']} | {money(row['equity'])} | {money(row['gross_realized_pnl'])} | {money(cumulative)} | {money(row['equity_change_since_prior_observation'])} | {link} |")
    lines += ["", "[Archived legacy table — unverified](docs/LEGACY_SESSION_TABLE.md). Missing equity is never estimated from the current account snapshot.", "", "</details>", ""]
    return "\n".join(lines)


def update_readme():
    folder = latest_report()
    path = ROOT/"README.md"
    text = path.read_text(encoding="utf-8")
    block = render_block(folder)
    if START in text and END in text:
        before, rest = text.split(START,1)
        _, after = rest.split(END,1)
        text = before+block+after
    else:
        title, rest = text.split("\n",1)
        text = title+"\n\n"+block+"\n"+rest
    chart = folder/"daily_pnl_chart.png"
    if chart.exists():
        reference = f"![Daily P&L Chart]({chart.relative_to(ROOT).as_posix()})"
        text = re.sub(r"!\[Daily P&L Chart\]\([^\n]+\)", lambda _: reference, text)
    daily_table = render_daily_table(folder)
    if "### Daily Session Breakdown\n" in text:
        text = re.sub(r"### Daily Session Breakdown\n.*?(?=\n---|\Z)",
                      lambda _: daily_table, text, flags=re.S)
    else:
        text = text.replace(END, END + "\n\n" + daily_table + "\n---", 1)
    path.write_text(text,encoding="utf-8")
    print("Updated corrected-measurement block; legacy content preserved.")


if __name__ == "__main__":
    update_readme()
