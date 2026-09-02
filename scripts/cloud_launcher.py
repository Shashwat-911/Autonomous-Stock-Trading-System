"""
cloud_launcher.py
=================
Railway cloud deployment wrapper for the Autonomous Stock Trading System.

Purpose:
  - Runs continuously as a Railway 'worker' process.
  - Only launches the trading bot during US market hours (Mon-Fri 13:30-20:00 UTC).
  - Auto-restarts the bot if it crashes mid-session.
  - Streams all bot output to both Railway logs (stdout) and a date-stamped local log file.
  - Sleeps when market is closed so Railway is not billed for idle compute.

Market Hours Reference:
  US Market:  Mon-Fri  09:30 - 16:00 ET
  = UTC:      Mon-Fri  13:30 - 20:00 UTC
  = IST:      Mon-Fri  19:00 - 01:30 IST (next day)
"""

import subprocess
import sys
import os
import time
from datetime import datetime, timezone

# ── Working directory: always project root, regardless of where this script is called from ──
os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.chdir('..')  # go to project root


def is_market_hours():
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


# ──────────────────────────────────────────────────────────────────────────────
# Main loop
# ──────────────────────────────────────────────────────────────────────────────

print("=" * 60)
print("  AutoTrader Cloud Runner started")
print(f"  Launch time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
print(f"  Python:      {sys.version.split()[0]}")
print(f"  Working dir: {os.getcwd()}")
print("=" * 60)

while True:
    if is_market_hours():
        # ── Market is open: launch the trading bot ──
        now_utc  = datetime.now(timezone.utc)
        date_str = now_utc.strftime('%Y_%m_%d')
        log_path = f'outputs/logs/session_{date_str}.txt'

        os.makedirs('outputs/logs', exist_ok=True)

        print(f"\n[{now_utc.strftime('%H:%M:%S UTC')}] Market OPEN — launching trading bot...")
        print(f"  Session log: {log_path}")

        try:
            # Launch main.py live as a subprocess
            process = subprocess.Popen(
                [sys.executable, 'main.py', 'live'],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,   # merge stderr into stdout
                text=True,
                bufsize=1                   # line-buffered for real-time Railway log streaming
            )

            # Stream output line-by-line to Railway logs AND local log file simultaneously
            with open(log_path, 'a') as log_file:   # 'a' = append, safe if bot restarts same day
                for line in process.stdout:
                    print(line, end='', flush=True)  # Railway captures stdout in real time
                    log_file.write(line)
                    log_file.flush()

            process.wait()
            exit_code = process.returncode
            print(f"\n[{datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}] Bot exited with code: {exit_code}")

            if exit_code != 0:
                print("  Non-zero exit — bot may have crashed. Will retry after cooldown.")

        except Exception as e:
            print(f"[ERROR] Bot crashed with exception: {e}")

        # ── Brief cooldown before re-checking market hours ──
        print("  Cooling down 5 minutes before next check...")
        time.sleep(300)   # 5 minutes

    else:
        # ── Market is closed: sleep and check again later ──
        now_utc = datetime.now(timezone.utc)
        day_name = now_utc.strftime('%A')
        time_str = now_utc.strftime('%H:%M UTC')
        print(f"  Market CLOSED — {day_name} {time_str} — sleeping 10 minutes", flush=True)
        time.sleep(600)   # 10 minutes
