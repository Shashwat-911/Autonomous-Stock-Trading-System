"""Resolve the post-market reporting slot across US daylight-saving changes."""
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")


def resolve_report_window(now: datetime, event_name: str, event_schedule: str = "") -> tuple[str, bool]:
    local = now.astimezone(NEW_YORK)
    if event_name == "workflow_dispatch":
        should_report = local.hour >= 17
    elif event_name == "schedule":
        try:
            scheduled_utc_hour = int(event_schedule.split()[1])
        except (IndexError, ValueError):
            raise ValueError("Unexpected schedule expression for report run")
        expected_local_hour = scheduled_utc_hour + int(local.utcoffset().total_seconds() / 3600)
        should_report = local.hour >= 17 and expected_local_hour == 17
    else:
        should_report = False
    return local.date().isoformat(), should_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-name", required=True)
    parser.add_argument("--event-schedule", default="")
    args = parser.parse_args()
    date, should_report = resolve_report_window(
        datetime.now(NEW_YORK), args.event_name, args.event_schedule
    )
    print(f"date={date}")
    print(f"report_required={'true' if should_report else 'false'}")


if __name__ == "__main__":
    main()
