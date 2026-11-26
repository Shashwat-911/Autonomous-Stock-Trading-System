"""Fetch the Render execution owner's public session log for archival."""
import argparse
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RENDER_URL = "https://autonomous-stock-trader.onrender.com"


class SessionLogParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self._depth = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "div" and dict(attrs).get("class") == "log-content":
            self._depth += 1

    def handle_endtag(self, tag):
        if tag == "div" and self._depth:
            self._depth -= 1

    def handle_data(self, data):
        if self._depth:
            self.parts.append(data)


def fetch_session_log(day: str, opener=urllib.request.urlopen, sleep=time.sleep) -> Path:
    date.fromisoformat(day)
    name = "session_" + day.replace("-", "_") + ".txt"
    url = f"{RENDER_URL}/logs/{name}"
    errors = []
    for attempt in range(6):
        try:
            with opener(urllib.request.Request(url, headers={"User-Agent": "session-archive"}), timeout=60) as response:
                page = response.read().decode("utf-8", errors="replace")
            parser = SessionLogParser()
            parser.feed(page)
            content = "".join(parser.parts).strip()
            if name not in page or "LIVE PAPER TRADING" not in content:
                raise ValueError("Render log is missing or is not a completed trading-session log")
            path = ROOT / "outputs" / "logs" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content + "\n", encoding="utf-8")
            return path
        except (OSError, urllib.error.URLError, TimeoutError, ValueError) as exc:
            errors.append(type(exc).__name__)
            if attempt < 5:
                sleep(min(60, 10 * (attempt + 1)))
    raise RuntimeError("Unable to archive Render session log after retries: " + ",".join(errors))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="Trading date in YYYY-MM-DD, New York time")
    args = parser.parse_args()
    path = fetch_session_log(args.date)
    print("Archived Render session log:", path.name)


if __name__ == "__main__":
    main()
