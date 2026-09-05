"""
post_session.py
===============
Automated post-session pipeline — runs automatically after every trading session.

Pipeline (in order):
  1. Fetch today's equity snapshot from Alpaca API → update alpaca_equity_history.csv
  2. Regenerate daily_pnl_chart.png from updated CSV
  3. Git add: session log + equity CSV + chart PNG
  4. Git commit: dated message with equity summary
  5. Git push to GitHub via HTTPS token (GIT_TOKEN env var)

Usage:
  python scripts/post_session.py                  # full pipeline
  python scripts/post_session.py --dry-run        # skip git push (safe for local testing)

Railway Setup:
  Set environment variable GIT_TOKEN = your GitHub Personal Access Token
  (Settings → Variables in Railway dashboard)
  Token needs: repo → Contents (write) permission.
"""

import subprocess
import sys
import os
import time
from datetime import datetime, timezone

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Working directory: always project root ─────────────────────────────────────
os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.chdir('..')

DRY_RUN = "--dry-run" in sys.argv

# ── Helpers ────────────────────────────────────────────────────────────────────

def banner(msg: str):
    """Print a clearly visible section header to Railway logs."""
    print(f"\n{'-' * 60}")
    print(f"  {msg}")
    print(f"{'-' * 60}", flush=True)


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """
    Run a subprocess command, stream output to Railway logs, return result.
    Raises on non-zero exit if check=True.
    """
    print(f"$ {' '.join(cmd)}", flush=True)
    result = subprocess.run(
        cmd,
        capture_output=False,   # let stdout/stderr flow to Railway logs directly
        text=True,
        check=check
    )
    return result


def run_python(script: str, *args: str) -> bool:
    """
    Run a Python script in the same interpreter. Returns True on success.
    """
    cmd = [sys.executable, script] + list(args)
    print(f"$ {' '.join(cmd)}", flush=True)
    result = subprocess.run(cmd, text=True, check=False)
    if result.returncode != 0:
        print(f"[WARN] {script} exited with code {result.returncode}", flush=True)
        return False
    return True


def git_configure_remote():
    """
    Configure git remote to use HTTPS token auth.
    Required on Railway (no SSH keys available).
    GIT_TOKEN must be set as a Railway environment variable.
    """
    token = os.environ.get("GIT_TOKEN", "")
    if not token:
        print("[WARN] GIT_TOKEN not set — git push will use existing credentials.", flush=True)
        return

    # Rewrite remote URL to embed token (never logged — token stays in memory only)
    remote_url = (
        f"https://{token}@github.com/Shashwat-911/Autonomous-Stock-Trading-System.git"
    )
    subprocess.run(
        ["git", "remote", "set-url", "origin", remote_url],
        check=False, capture_output=True   # suppress URL from logs (contains token)
    )
    print("[INFO] Git remote configured with HTTPS token.", flush=True)


def read_equity_summary() -> str:
    """
    Read the last row of the equity CSV and return a compact summary string
    for use in the git commit message.
    """
    csv_path = "outputs/alpaca_equity_history.csv"
    try:
        import pandas as pd
        df = pd.read_csv(csv_path)
        if df.empty:
            return "equity data unavailable"
        row = df.iloc[-1]
        equity  = row.get("equity", 0)
        pnl     = row.get("daily_pnl", 0)
        cum_pnl = df["daily_pnl"].sum()
        sign    = "+" if pnl >= 0 else ""
        return (
            f"equity=${equity:,.2f} | "
            f"daily={sign}${pnl:.2f} | "
            f"cumulative=${cum_pnl:+,.2f}"
        )
    except Exception as e:
        return f"summary unavailable ({e})"


# ──────────────────────────────────────────────────────────────────────────────
# Pipeline
# ──────────────────────────────────────────────────────────────────────────────

def run_post_session_pipeline():
    now_utc  = datetime.now(timezone.utc)
    date_str = now_utc.strftime("%Y-%m-%d")          # YYYY-MM-DD  (for commit message)
    date_tag = now_utc.strftime("%Y_%m_%d")          # YYYY_MM_DD  (for log filename)
    log_path = f"outputs/logs/session_{date_tag}.txt"

    print("=" * 60)
    print("  AutoTrader Post-Session Pipeline")
    print(f"  Date:    {date_str} (UTC)")
    print(f"  Dry run: {DRY_RUN}")
    print("=" * 60, flush=True)

    # ── Step 1: Fetch today's equity from Alpaca ───────────────────────────────
    banner("Step 1/5 — Fetching equity snapshot from Alpaca API")
    fetch_ok = run_python("scripts/fetch_alpaca_equity.py", "--today")
    if not fetch_ok:
        print("[WARN] Equity fetch failed — CSV may be stale. Continuing pipeline.", flush=True)

    # ── Step 2: Generate session performance report ───────────────────────────
    banner("Step 2/5 — Generating session performance report")
    report_ok = run_python("scripts/generate_session_report.py")
    if not report_ok:
        print("[WARN] Session report generation failed. Continuing.", flush=True)

    # ── Step 3: Regenerate P&L chart ──────────────────────────────────────────
    banner("Step 3/5 — Regenerating daily P&L chart")
    chart_ok = run_python("scripts/generate_pnl_chart.py")
    if not chart_ok:
        print("[WARN] Chart generation failed — PNG may be stale. Continuing.", flush=True)

    # ── Step 4: Update README session breakdown ────────────────────────────────
    banner("Step 4/5 — Updating README.md session breakdown table")
    readme_ok = run_python("scripts/update_readme.py")
    if not readme_ok:
        print("[WARN] README update failed. Continuing.", flush=True)

    # ── Step 5: Git stage, commit + push ──────────────────────────────────────
    banner("Step 5/5 — Staging files, committing and pushing to GitHub")

    files_to_stage = [
        "outputs/alpaca_equity_history.csv",
        "outputs/daily_pnl_chart.png",
        "outputs/performance_summary.json",
        "outputs/trade_history.csv",
        "outputs/session_all_orders.csv",
        "README.md",
    ]

    for f in files_to_stage:
        if os.path.exists(f):
            run(["git", "add", f], check=False)
        else:
            print(f"  [SKIP] {f} — file does not exist", flush=True)

    # Stage all session logs
    if os.path.exists("outputs/logs"):
        run(["git", "add", "outputs/logs/"], check=False)
        print("  Staged outputs/logs/", flush=True)

    # ── Check if there's anything to commit ────────────────────────────────────
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True
    )
    staged_changes = status.stdout.strip()

    if not staged_changes:
        print("\n  Nothing to commit — files unchanged since last push.", flush=True)
        print("  Pipeline complete (no commit needed).", flush=True)
        return True

    print(f"\n  Staged changes:\n{staged_changes}", flush=True)

    equity_summary = read_equity_summary()
    commit_msg = (
        f"auto(session): {date_str} trading session - {equity_summary}"
    )
    print(f"  Commit message: {commit_msg}", flush=True)

    # Configure git identity (required on fresh Railway/Render container)
    subprocess.run(
        ["git", "config", "user.email", "autotrader@railway.app"],
        check=False, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "AutoTrader Bot"],
        check=False, capture_output=True
    )

    run(["git", "commit", "-m", commit_msg], check=False)

    if DRY_RUN:
        print("\n  [DRY RUN] Skipping git push. Commit made locally only.", flush=True)
    else:
        git_configure_remote()

        push_result = subprocess.run(
            ["git", "push", "origin", "main"],
            capture_output=True, text=True, check=False
        )
        if push_result.returncode == 0:
            print("\n  ✅ Pushed to GitHub successfully.", flush=True)
            if push_result.stdout:
                print(push_result.stdout.strip(), flush=True)
        else:
            print(f"\n  ❌ Push failed (exit {push_result.returncode}).", flush=True)
            if push_result.stdout:
                print(f"Stdout: {push_result.stdout.strip()}", flush=True)
            if push_result.stderr:
                print(f"Stderr: {push_result.stderr.strip()}", flush=True)
            return False

    print(f"\n  Pipeline complete — {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}", flush=True)
    return True


# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    success = run_post_session_pipeline()
    sys.exit(0 if success else 1)
