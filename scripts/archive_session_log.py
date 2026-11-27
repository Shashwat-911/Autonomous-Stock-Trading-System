"""Archive stdout independently of measurement success; never exports debug/account dumps."""
import argparse
from datetime import datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from zoneinfo import ZoneInfo
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.post_session import git_environment

ROOT = Path(__file__).resolve().parents[1]
REMOTE = "https://github.com/Shashwat-911/Autonomous-Stock-Trading-System.git"


class LogParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inside = False
        self.parts = []
    def handle_starttag(self, tag, attrs):
        if tag == "div" and dict(attrs).get("class") == "log-content":
            self.inside = True
    def handle_endtag(self, tag):
        if tag == "div": self.inside = False
    def handle_data(self, data):
        if self.inside: self.parts.append(data)


def recover(day):
    name = "session_" + day.replace("-", "_") + ".txt"
    path = ROOT / "outputs/logs" / name
    if path.exists(): return path
    url = "https://autonomous-stock-trader.onrender.com/logs/" + name
    with urllib.request.urlopen(url, timeout=60) as response:
        page = response.read().decode("utf-8")
    parser = LogParser(); parser.feed(page)
    content = "".join(parser.parts)
    if name not in page or "LIVE PAPER TRADING" not in content:
        raise ValueError("Requested session log not available; refusing stale or generic page")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def publish(path):
    # Isolated checkout prevents failed/staged measurement outputs entering this commit.
    env = git_environment()
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)/"archive"
        def git(*args):
            return subprocess.run(["git", *args], cwd=repo, env=env, check=True,
                                  capture_output=True, text=True)
        subprocess.run(["git", "clone", "--depth", "1", "--filter=blob:none", "--sparse",
                        REMOTE, str(repo)], env=env, check=True, capture_output=True)
        git("sparse-checkout", "set", "outputs/logs")
        dest = repo/"outputs/logs"/path.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
        git("add", "outputs/logs/"+path.name)
        if not git("diff", "--cached", "--name-only").stdout.strip(): return
        git("-c", "user.name=SHASHWAT YADAV", "-c", "user.email=shashwatyadav975@gmail.com",
            "commit", "-m", "logs(session): archive " + path.stem + " independently of reporting")
        git("pull", "--rebase", "origin", "main")
        git("push", "origin", "HEAD:main")


def main():
    now = datetime.now(ZoneInfo("America/New_York"))
    default = (now - timedelta(days=1) if now.hour < 16 else now).date().isoformat()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=default)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    from datetime import date
    date.fromisoformat(args.date)
    path = recover(args.date)
    if args.publish: publish(path)
    print("Session log archived:", path.name)


if __name__ == "__main__":
    main()
