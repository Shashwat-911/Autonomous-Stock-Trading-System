"""Small, dependency-free helpers for the Render market-clock loop."""
from datetime import datetime, time as wall_time, timezone
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")


def new_york_now(now=None):
    """Return a timezone-aware New York timestamp."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(NEW_YORK)


def session_date_tag(now=None) -> str:
    """Use the exchange's local date for durable session filenames."""
    return new_york_now(now).strftime("%Y_%m_%d")


def should_keep_service_awake(now=None) -> bool:
    """Limit Render free-instance keepalives to weekday operating hours.

    The early start gives a scheduled external health check time to wake a
    sleeping service before the US market opens. The evening buffer keeps the
    session log available for post-market archival. This avoids consuming the
    entire monthly free-instance allowance with a 24/7 self-ping.
    """
    local = new_york_now(now)
    return local.weekday() < 5 and wall_time(7, 0) <= local.time() < wall_time(19, 0)


def market_is_open(clock) -> bool:
    """Fail closed when the broker clock is unavailable."""
    return bool(clock is not None and getattr(clock, "is_open", False))


def seconds_until_next_check(clock, now=None) -> int:
    """Poll slowly when closed, then more often just before the broker open."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    next_open = getattr(clock, "next_open", None) if clock is not None else None
    if next_open is None:
        return 60
    if next_open.tzinfo is None:
        next_open = next_open.replace(tzinfo=timezone.utc)
    seconds = (next_open - now).total_seconds()
    if seconds <= 0:
        return 30
    if seconds <= 15 * 60:
        return max(15, min(60, int(seconds)))
    return 600
