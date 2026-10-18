"""Display validated v2 account/episode metrics, never legacy session averages."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from analytics.reporting import latest_report


def main():
    folder=latest_report()
    print((folder/"performance_summary.json").read_text(encoding="utf-8"))
    print("Daily equity changes and realized P&L: " + str(folder/"daily_account_measurement.csv"))
    print("Per-symbol gross episode metrics: " + str(folder/"symbol_summary.csv"))


if __name__ == "__main__":
    main()
