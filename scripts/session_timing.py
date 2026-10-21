"""Read-only exchange-calendar preflight; no trading imports or mutations."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.reconcile_paper_account import PaperReader

ET = ZoneInfo("America/New_York")


def assess_session(now, calendar, max_lateness_minutes=15):
    if now.tzinfo is None:
        raise ValueError("Timezone-aware time required")
    day = now.astimezone(ET).date().isoformat()
    row = next((r for r in calendar if r["date"] == day), None)
    result = {"trading_date": day, "observed_at": now.isoformat()}
    if row is None:
        return dict(result, status="NON_TRADING_DAY")
    opening = datetime.fromisoformat(day+"T"+row["open"]).replace(tzinfo=ET)
    closing = datetime.fromisoformat(day+"T"+row["close"]).replace(tzinfo=ET)
    delay = (now-opening).total_seconds()/60
    status = ("PREOPEN" if now < opening else "CLOSED" if now >= closing else
              "LATE_START" if delay > max_lateness_minutes else "READY")
    return dict(result, status=status, market_open=opening.isoformat(),
                market_close=closing.isoformat(), minutes_after_open=round(delay,2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-lateness-minutes", type=float, default=15)
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    day = now.astimezone(ET).date().isoformat()
    calendar = PaperReader().get("/v2/calendar", {"start":day,"end":day})
    result = assess_session(now, calendar, args.max_lateness_minutes)
    result["execution_source"] = os.getenv("TRADING_EXECUTION_SOURCE", "unidentified")
    print(json.dumps(result, indent=2))
    if result["status"] != "READY":
        print("Session preflight refused startup; no cleanup or trading was performed.",file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
