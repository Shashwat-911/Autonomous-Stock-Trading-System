"""
cloud_launcher.py
=================
Railway cloud deployment wrapper for the Autonomous Stock Trading System.

Purpose:
  - Runs continuously as a Railway 'worker' process.
  - Only launches the trading bot during US market hours (Mon-Fri 13:30-20:00 UTC).
  - Auto-restarts the bot if it crashes mid-session.
  - Streams all bot output to both Railway logs (stdout) and a date-stamped local log file.
  - After each session ends (market closes), runs the post-session pipeline:
      fetch equity → regenerate chart → git commit → git push to GitHub.
  - Sleeps when market is closed so Railway is not billed for idle compute.

Market Hours Reference:
  US Market:  Mon-Fri  09:30 - 16:00 ET
  = UTC:      Mon-Fri  13:30 - 20:00 UTC
  = IST:      Mon-Fri  19:00 - 01:30 IST (next day)

Post-Session Pipeline:
  Triggered once per day, after 20:00 UTC (market close).
  Calls scripts/post_session.py which:
    1. Fetches equity snapshot from Alpaca API
    2. Regenerates daily_pnl_chart.png
    3. Git commits: session log + equity CSV + chart
    4. Git pushes to GitHub (requires GIT_TOKEN env var)
"""

import subprocess
import sys
import os
import time
from datetime import datetime, timezone

# ── Working directory: always project root, regardless of where this script is called from ──
os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.chdir('..')  # go to project root


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def is_market_hours() -> bool:
    """
    Returns True if the current UTC time falls within US equity market hours.

    US market:  Monday – Friday, 09:30 – 16:00 Eastern Time
    UTC equiv:  Monday – Friday, 13:30 – 20:00 UTC  (standard / no DST adjustment)

    Note: This is a conservative approximation. The Alpaca broker layer inside
    main.py also checks the live market clock before submitting any orders,
    so this function only determines whether to *launch* the bot process at all.
    """
    now_utc = datetime.now(timezone.utc)
    weekday = now_utc.weekday()   # 0 = Monday … 4 = Friday, 5 = Saturday, 6 = Sunday

    # ── Weekend guard ──
    if weekday >= 5:
        return False

    # ── Build today's open / close timestamps in UTC ──
    market_open  = now_utc.replace(hour=13, minute=30, second=0, microsecond=0)
    market_close = now_utc.replace(hour=20, minute=0,  second=0, microsecond=0)

    return market_open <= now_utc <= market_close


def is_post_session_window() -> bool:
    """
    Returns True in the 30-minute window just after market close (20:00–20:30 UTC).
    This is when the post-session pipeline should run — market is definitively closed
    and all Alpaca order fills have settled.
    """
    now_utc = datetime.now(timezone.utc)
    weekday = now_utc.weekday()

    if weekday >= 5:
        return False

    post_open  = now_utc.replace(hour=20, minute=0,  second=0, microsecond=0)
    post_close = now_utc.replace(hour=20, minute=30, second=0, microsecond=0)

    return post_open <= now_utc <= post_close


def run_post_session(date_str: str):
    """
    Invoke scripts/post_session.py as a subprocess.
    Streams all output to Railway logs.
    """
    print(f"\n{'=' * 60}")
    print(f"  POST-SESSION PIPELINE — {date_str}")
    print(f"  Time: {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}")
    print(f"{'=' * 60}", flush=True)

    result = subprocess.run(
        [sys.executable, "scripts/post_session.py"],
        text=True,
        check=False
    )

    if result.returncode == 0:
        print(f"\n  ✅ Post-session pipeline succeeded.", flush=True)
    else:
        print(f"\n  ❌ Post-session pipeline failed (exit {result.returncode}).", flush=True)

    return result.returncode == 0


# ──────────────────────────────────────────────────────────────────────────────
# Main loop
# ──────────────────────────────────────────────────────────────────────────────

print("=" * 60)
print("  AutoTrader Cloud Runner started")
print(f"  Launch time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
print(f"  Python:      {sys.version.split()[0]}")
print(f"  Working dir: {os.getcwd()}")
print("=" * 60, flush=True)

# Track which date we last ran the post-session pipeline (prevent duplicate runs)
last_post_session_date: str = ""

while True:
    now_utc  = datetime.now(timezone.utc)
    today    = now_utc.strftime("%Y-%m-%d")
    date_tag = now_utc.strftime("%Y_%m_%d")

    # ──────────────────────────────────────────────────────────────────────────
    # Branch A: Market is OPEN — run the trading bot
    # ──────────────────────────────────────────────────────────────────────────
    if is_market_hours():
        log_path = f"outputs/logs/session_{date_tag}.txt"
        os.makedirs("outputs/logs", exist_ok=True)

        print(f"\n[{now_utc.strftime('%H:%M:%S UTC')}] Market OPEN — launching trading bot...", flush=True)
        print(f"  Session log: {log_path}", flush=True)

        try:
            # Launch main.py live as a child process
            process = subprocess.Popen(
                [sys.executable, "main.py", "live"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,   # merge stderr → stdout
                text=True,
                bufsize=1                   # line-buffered for real-time Railway log streaming
            )

            # Stream output line-by-line to Railway AND local log file simultaneously
            with open(log_path, "a") as log_file:   # 'a' = append; safe if bot restarts same day
                for line in process.stdout:
                    print(line, end="", flush=True)
                    log_file.write(line)
                    log_file.flush()

            process.wait()
            exit_code = process.returncode
            print(
                f"\n[{datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}] "
                f"Bot exited with code: {exit_code}",
                flush=True
            )

            if exit_code != 0:
                print("  Non-zero exit — bot may have crashed. Will retry after cooldown.", flush=True)

        except Exception as e:
            print(f"[ERROR] Bot crashed with exception: {e}", flush=True)

        # ── Brief cooldown before re-checking market hours ──
        print("  Cooling down 5 minutes before next check...", flush=True)
        time.sleep(300)   # 5 minutes

    # ──────────────────────────────────────────────────────────────────────────
    # Branch B: Post-session window (20:00–20:30 UTC) — run pipeline once/day
    # ──────────────────────────────────────────────────────────────────────────
    elif is_post_session_window() and last_post_session_date != today:
        print(
            f"\n[{now_utc.strftime('%H:%M:%S UTC')}] "
            f"Post-session window open — starting pipeline...",
            flush=True
        )
        # Wait 2 minutes after close for Alpaca fills to settle before fetching
        print("  Waiting 2 min for order fills to settle...", flush=True)
        time.sleep(120)

        run_post_session(today)
        last_post_session_date = today   # mark as done for today

        print("  Sleeping 15 minutes before next check...", flush=True)
        time.sleep(900)

    # ──────────────────────────────────────────────────────────────────────────
    # Branch C: Market is CLOSED (and not post-session window) — sleep
    # ──────────────────────────────────────────────────────────────────────────
    else:
        day_name = now_utc.strftime("%A")
        time_str = now_utc.strftime("%H:%M UTC")
        print(f"  Market CLOSED — {day_name} {time_str} — sleeping 10 minutes", flush=True)
        time.sleep(600)   # 10 minutes
