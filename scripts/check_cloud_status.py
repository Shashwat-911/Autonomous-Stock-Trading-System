"""Read-only external wake/status probe. Never submits orders or starts a trader."""
from datetime import datetime, timezone
import json
import urllib.request

URL = "https://autonomous-stock-trader.onrender.com/status"


def validate_status(state, now):
    if not state.get("revision") or state["revision"] == "unknown":
        raise ValueError("Unverified deployment: runner revision missing")
    if state.get("phase") in ("STARTING", "UNKNOWN"):
        raise ValueError("Cloud calendar/runner is not ready")
    if state.get("phase") in ("READY", "LATE_START", "TRADING"):
        if not state.get("worker_running"):
            raise ValueError("Market open but trading worker is absent")
        heartbeat = state.get("last_worker_output") or state.get("worker_started_at")
        if not heartbeat or (now - datetime.fromisoformat(heartbeat)).total_seconds() > 25 * 60:
            raise ValueError("Trading worker has no recent output (25-minute limit)")


def main():
    with urllib.request.urlopen(URL, timeout=90) as response:
        state = json.load(response)
    print(json.dumps(state, indent=2))
    validate_status(state, datetime.now(timezone.utc))


if __name__ == "__main__":
    main()
