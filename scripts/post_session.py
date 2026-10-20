"""
post_session.py
===============
Automated post-session pipeline — runs automatically after every trading session.

Pipeline (in order):
  1. Fetch timestamped broker history privately (preserve legacy ledger)
  2. Generate validated measurement_v2 reports and chart
  3. Git add: session logs + validated measurement aggregates + README
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
sys.path.insert(0, os.getcwd())

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


def git_environment():
    """Pass HTTPS credentials to child Git processes only, never .git/config."""
    import base64
    env = os.environ.copy()
    token = env.get("GIT_TOKEN", "")
    if token:
        count = int(env.get("GIT_CONFIG_COUNT", "0"))
        env[f"GIT_CONFIG_KEY_{count}"] = "http.https://github.com/.extraheader"
        encoded = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        env[f"GIT_CONFIG_VALUE_{count}"] = "AUTHORIZATION: basic " + encoded
        env["GIT_CONFIG_COUNT"] = str(count + 1)
    return env


def read_equity_summary() -> str:
    """
    Read the latest validated v2 report and return a compact summary string
    for use in the git commit message.
    """
    try:
        import json
        from analytics.reporting import latest_report
        folder = latest_report()
        report = json.loads((folder / "performance_summary.json").read_text(encoding="utf-8"))
        return f"measurement_v2 | equity=${float(report['current_account_equity']):,.2f} | completed_episodes={report['total_trades']}"
    except Exception:
        return "measurement unavailable; inspect report status"


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
        print("[WARN] Private equity fetch failed; shared report will independently collect history.", flush=True)

    # ── Step 2: Generate session performance report ───────────────────────────
    banner("Step 2/5 — Generating session performance report")
    report_ok = run_python("scripts/generate_session_report.py")
    if not report_ok:
        print("[ERROR] Report failed; refusing to publish stale artifacts.", flush=True)
        return False

    # ── Step 3: Regenerate P&L chart ──────────────────────────────────────────
    banner("Step 3/5 — Regenerating daily P&L chart")
    chart_ok = run_python("scripts/generate_pnl_chart.py")
    if not chart_ok:
        print("[ERROR] Chart failed; refusing incomplete publication.", flush=True)
        return False

    # ── Step 4: Update README session breakdown ────────────────────────────────
    banner("Step 4/5 — Updating README.md session breakdown table")
    readme_ok = run_python("scripts/update_readme.py")
    if not readme_ok:
        print("[ERROR] README update failed; refusing incomplete publication.", flush=True)
        return False

    # ── Step 5: Git stage, commit + push ──────────────────────────────────────
    banner("Step 5/5 — Staging files, committing and pushing to GitHub")

    files_to_stage = [
        "outputs/measurement_v2/",
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
        ["git", "diff", "--cached", "--name-only"],
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

    # Configure git identity for commits
    git_author_email = os.environ.get("GIT_AUTHOR_EMAIL", "shashwatyadav975@gmail.com")
    git_author_name = os.environ.get("GIT_AUTHOR_NAME", "SHASHWAT YADAV")
    subprocess.run(
        ["git", "config", "user.email", git_author_email],
        check=False, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", git_author_name],
        check=False, capture_output=True
    )

    if run(["git", "commit", "-m", commit_msg], check=False).returncode != 0:
        return False

    if DRY_RUN:
        print("\n  [DRY RUN] Skipping git push. Commit made locally only.", flush=True)
    else:
        env = git_environment()
        remote = "https://github.com/Shashwat-911/Autonomous-Stock-Trading-System.git"
        pull = subprocess.run(["git", "pull", "--rebase", remote, "main"], check=False, env=env)
        if pull.returncode != 0:
            print("[ERROR] Git synchronization failed; refusing push.", flush=True)
            return False

        push_result = subprocess.run(
            ["git", "push", remote, "HEAD:main"],
            capture_output=True, text=True, check=False, env=env
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
