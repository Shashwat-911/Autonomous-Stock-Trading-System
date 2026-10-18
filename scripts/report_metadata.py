"""Read current v2 report metadata for artifact commit messages."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from analytics.reporting import latest_report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date",action="store_true")
    args=parser.parse_args()
    report=json.loads((latest_report()/"performance_summary.json").read_text(encoding="utf-8"))
    if args.date:
        print(report["period_end"])
    else:
        print(f"measurement_v2 | equity=${float(report['current_account_equity']):,.2f} | completed_episodes={report['total_trades']}")


if __name__ == "__main__":
    main()
