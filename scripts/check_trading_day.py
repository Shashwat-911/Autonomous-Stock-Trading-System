"""Print whether a New York date is an Alpaca exchange session (true/false)."""
import argparse
import json
import sys
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def is_trading_day(day: str) -> bool:
    date.fromisoformat(day)
    import config

    key = config.ALPACA.get("api_key")
    secret = config.ALPACA.get("secret_key")
    if not key or not secret:
        raise RuntimeError("Alpaca credentials are required for the exchange calendar check")

    base = config.ALPACA.get("base_url", "https://paper-api.alpaca.markets").rstrip("/")
    parsed_base = urllib.parse.urlsplit(base)
    if parsed_base.scheme != "https" or parsed_base.netloc != "paper-api.alpaca.markets":
        raise RuntimeError("Calendar check is restricted to the Alpaca paper endpoint")
    endpoint = base if base.endswith("/v2") else base + "/v2"
    query = urllib.parse.urlencode({"start": day, "end": day})
    request = urllib.request.Request(
        endpoint + "/calendar?" + query,
        headers={
            "APCA-API-KEY-ID": key,
            "APCA-API-SECRET-KEY": secret,
            "Accept": "application/json",
            "User-Agent": "autotrader-calendar-check",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        calendar = json.load(response)
    return any(item.get("date") == day for item in calendar)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="Trading date in YYYY-MM-DD, New York time")
    args = parser.parse_args()
    print("true" if is_trading_day(args.date) else "false")


if __name__ == "__main__":
    main()
