"""Fetch timestamped broker history without changing the legacy equity ledger.

--today remains accepted by existing launchers; a full retained-history refresh
is intentional because broker fees and historical observations can be revised.
"""
import argparse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analytics.measurement import equity_observations, day_of
from scripts.reconcile_paper_account import PaperReader, ROOT, write_csv, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--today", action="store_true")
    parser.parse_args()
    reader = PaperReader()
    account = reader.get("/v2/account")
    start = day_of(account["created_at"])
    now = datetime.now(timezone.utc)
    end = day_of(now.isoformat())
    history = reader.get("/v2/account/portfolio/history", {
        "start": start, "end": str(date.fromisoformat(end)+timedelta(days=1)), "timeframe":"1D"})
    calendar = reader.get("/v2/calendar", {"start":start,"end":end})
    snapshot = {"portfolio_history":history,"calendar":calendar,
                "fetched_at":datetime.now(timezone.utc).isoformat()}
    folder = ROOT / "outputs/reporting_private" / ("equity-"+now.strftime("%Y%m%dT%H%M%S%fZ"))
    folder.mkdir(parents=True)
    write_json(folder/"broker_history.json",snapshot)
    write_csv(folder/"broker_equity_history.csv",equity_observations(snapshot))
    print(f"Timestamped broker history saved privately: {folder}")
    print("The session reporter independently publishes a coherent v2 generation; legacy ledger preserved.")


if __name__ == "__main__":
    main()
