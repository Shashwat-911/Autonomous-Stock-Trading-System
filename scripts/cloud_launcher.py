"""
cloud_launcher.py
=================
Render cloud deployment wrapper for the Autonomous Stock Trading System.

Purpose:
  - Runs continuously as a Render 'worker' service.
  - Launches against the broker exchange calendar (DST, holidays and early closes).
  - Launches only within the configured opening tolerance; late starts require review.
  - Streams all bot output to both Render logs (stdout) and a date-stamped local log file.
  - After each session ends (market closes), runs the post-session pipeline:
      fetch equity → regenerate chart → git commit → git push to GitHub.
  - Polls the calendar while closed; sleeping does not eliminate hosting charges.

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
import threading
import json
from datetime import datetime, timedelta, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Working directory: always project root, regardless of where this script is called from ──
os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.chdir('..')  # go to project root
sys.path.insert(0, os.getcwd())


# ──────────────────────────────────────────────────────────────────────────────
# Health Server (Required for Render Free Web Service)
# ──────────────────────────────────────────────────────────────────────────────

RUNNER = {"started_at": datetime.now(timezone.utc).isoformat(),
          "revision": os.getenv("RENDER_GIT_COMMIT", "unknown"),
          "source": "render-cloud", "phase": "STARTING", "worker_pid": None,
          "worker_started_at": None, "worker_exit_code": None,
          "last_calendar_check": None, "last_keepalive_ok": None,
          "keepalive_error": None}
WORKER = None


def runner_status():
    result = dict(RUNNER)
    result["worker_running"] = WORKER is not None and WORKER.poll() is None
    now = datetime.now(timezone.utc)
    result["observed_at"] = now.isoformat()
    if result.get("market_close") and now >= datetime.fromisoformat(result["market_close"]):
        result["phase"] = "CLOSED"
    elif result["worker_running"]:
        result["phase"] = "TRADING"
    return result


class HealthCheckHandler(BaseHTTPRequestHandler):

    def _find_best_log(self):
        """
        Find the best available log file to display.

        Returns (log_content, log_label) or (None, None) if nothing found.

        Search order:
          1. Today's session log: outputs/logs/session_YYYY_MM_DD.txt
          2. Yesterday's session log
          3. Most recent session_*.txt in outputs/logs/ (by mtime)
          4. Legacy outputs/trader.log or outputs/session_log.txt
        """
        log_dir = "outputs/logs"
        now_utc = datetime.now(timezone.utc)

        # 1 & 2: Today and yesterday
        for delta_days in range(0, 3):
            dt = now_utc - timedelta(days=delta_days)
            tag = dt.strftime("%Y_%m_%d")
            path = os.path.join(log_dir, f"session_{tag}.txt")
            if os.path.exists(path) and os.path.getsize(path) > 0:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    return f.read(), f"session_{tag}.txt"

        # 3: Newest file by modification time
        if os.path.isdir(log_dir):
            candidates = []
            for fname in os.listdir(log_dir):
                fpath = os.path.join(log_dir, fname)
                if fname.startswith("session_") and fname.endswith(".txt") and os.path.isfile(fpath):
                    candidates.append((os.path.getmtime(fpath), fpath, fname))
            if candidates:
                candidates.sort(reverse=True)
                _, best_path, best_name = candidates[0]
                if os.path.getsize(best_path) > 0:
                    with open(best_path, "r", encoding="utf-8", errors="replace") as f:
                        return f.read(), best_name

        # 4: Legacy log files in outputs/
        for legacy in ["outputs/trader.log", "outputs/session_log.txt"]:
            if os.path.exists(legacy) and os.path.getsize(legacy) > 0:
                with open(legacy, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                # Show last 200 lines of legacy logs
                recent = lines[-200:] if len(lines) > 200 else lines
                return "".join(recent), os.path.basename(legacy)

        return None, None

    def _list_available_logs(self):
        """Return a list of (filename, size_bytes, mtime_str) for available log files."""
        log_dir = "outputs/logs"
        entries = []
        if os.path.isdir(log_dir):
            for fname in sorted(os.listdir(log_dir), reverse=True):
                fpath = os.path.join(log_dir, fname)
                if fname.startswith("session_") and fname.endswith(".txt") and os.path.isfile(fpath):
                    size = os.path.getsize(fpath)
                    mtime = datetime.fromtimestamp(os.path.getmtime(fpath), tz=timezone.utc)
                    entries.append((fname, size, mtime.strftime("%Y-%m-%d %H:%M UTC")))
        return entries

    def _render_logs_page(self, log_content, log_label, available_logs):
        """Render an HTML page displaying the trading logs."""
        import html as html_mod

        now_utc = datetime.now(timezone.utc)
        status_line = f"Server time: {now_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}"

        # Escape log content for safe HTML rendering
        escaped = html_mod.escape(log_content) if log_content else ""

        # Build available logs list
        log_list_html = ""
        if available_logs:
            items = []
            for fname, size, mtime in available_logs[:15]:  # Show last 15
                size_kb = size / 1024
                items.append(
                    f'<li><a href="/logs/{fname}">{fname}</a> '
                    f'<span class="meta">({size_kb:.1f} KB — {mtime})</span></li>'
                )
            log_list_html = "<ul>" + "\n".join(items) + "</ul>"

        page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Trading Logs — Autonomous Stock Trader</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', 'Consolas', monospace;
    background: #0d1117;
    color: #c9d1d9;
    min-height: 100vh;
  }}
  .header {{
    background: linear-gradient(135deg, #161b22 0%, #0d1117 100%);
    border-bottom: 1px solid #30363d;
    padding: 20px 24px;
  }}
  .header h1 {{
    font-size: 1.3em;
    color: #58a6ff;
    font-weight: 600;
  }}
  .header .status {{
    font-size: 0.85em;
    color: #8b949e;
    margin-top: 4px;
  }}
  .header .badge {{
    display: inline-block;
    background: #238636;
    color: #fff;
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 0.75em;
    margin-left: 8px;
  }}
  .header .badge.warn {{
    background: #d29922;
  }}
  .nav {{
    display: flex;
    gap: 12px;
    margin-top: 10px;
  }}
  .nav a {{
    color: #58a6ff;
    text-decoration: none;
    font-size: 0.85em;
    padding: 4px 10px;
    border-radius: 6px;
    background: #21262d;
    border: 1px solid #30363d;
    transition: all 0.2s;
  }}
  .nav a:hover {{ background: #30363d; }}
  .content {{
    display: flex;
    gap: 0;
    min-height: calc(100vh - 100px);
  }}
  .sidebar {{
    width: 260px;
    min-width: 260px;
    background: #161b22;
    border-right: 1px solid #30363d;
    padding: 16px;
    overflow-y: auto;
  }}
  .sidebar h3 {{
    font-size: 0.8em;
    color: #8b949e;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 10px;
  }}
  .sidebar ul {{ list-style: none; }}
  .sidebar li {{
    margin-bottom: 6px;
  }}
  .sidebar a {{
    color: #58a6ff;
    text-decoration: none;
    font-size: 0.8em;
  }}
  .sidebar a:hover {{ text-decoration: underline; }}
  .sidebar .meta {{
    color: #484f58;
    font-size: 0.7em;
  }}
  .log-panel {{
    flex: 1;
    padding: 16px 20px;
    overflow: auto;
  }}
  .log-panel h2 {{
    font-size: 0.9em;
    color: #58a6ff;
    margin-bottom: 12px;
    padding-bottom: 8px;
    border-bottom: 1px solid #21262d;
  }}
  .log-content {{
    white-space: pre-wrap;
    word-wrap: break-word;
    font-size: 0.82em;
    line-height: 1.6;
    color: #e6edf3;
    background: #0d1117;
    padding: 12px;
    border-radius: 6px;
    border: 1px solid #21262d;
    max-height: calc(100vh - 180px);
    overflow-y: auto;
  }}
  .empty-state {{
    text-align: center;
    padding: 60px 20px;
    color: #8b949e;
  }}
  .empty-state .icon {{ font-size: 3em; margin-bottom: 16px; }}
  .empty-state h3 {{ color: #c9d1d9; margin-bottom: 8px; }}
  @media (max-width: 700px) {{
    .content {{ flex-direction: column; }}
    .sidebar {{ width: 100%; min-width: 100%; border-right: none; border-bottom: 1px solid #30363d; }}
  }}
</style>
</head>
<body>
  <div class="header">
    <h1>📈 Autonomous Stock Trader
      {'<span class="badge">Live: ' + log_label + '</span>' if log_content else '<span class="badge warn">No active session</span>'}
    </h1>
    <div class="status">{status_line}</div>
    <div class="nav">
      <a href="/">Health</a>
      <a href="/logs">Latest Log</a>
      <a href="/debug">Debug Log</a>
    </div>
  </div>
  <div class="content">
    <div class="sidebar">
      <h3>Session History</h3>
      {log_list_html if log_list_html else '<p style="color:#484f58;font-size:0.8em;">No session logs found on disk.</p>'}
    </div>
    <div class="log-panel">
      {'<h2>📄 ' + (log_label or '') + '</h2><div class="log-content">' + escaped + '</div>' if log_content else '''
      <div class="empty-state">
        <div class="icon">📭</div>
        <h3>No session log available</h3>
        <p>The trading bot hasn't generated a log file for today yet.<br>
        Logs appear here during US market hours (09:30–16:00 ET).<br><br>
        On Render's free tier, log files from previous sessions may be<br>
        cleared on redeploy. Check the GitHub repo's <code>outputs/logs/</code><br>
        directory for committed session history.</p>
      </div>
      '''}
    </div>
  </div>
</body>
</html>"""
        return page

    def do_GET(self):
        try:
            if self.path.rstrip("/") == "/status":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(json.dumps(runner_status()).encode())
                return
            # --- /logs or /log: Show session logs ---
            if self.path.rstrip("/") in ("/logs", "/log"):
                log_content, log_label = self._find_best_log()
                available_logs = self._list_available_logs()
                page = self._render_logs_page(log_content, log_label, available_logs)

                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(page.encode("utf-8"))
                return

            # --- /logs/<filename>: Serve a specific log file ---
            if self.path.startswith("/logs/session_"):
                fname = self.path.split("/")[-1]
                # Sanitize: only allow alphanumeric, underscores, dots
                safe_name = "".join(c for c in fname if c.isalnum() or c in ("_", "."))
                fpath = os.path.join("outputs", "logs", safe_name)
                if os.path.isfile(fpath):
                    with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    available_logs = self._list_available_logs()
                    page = self._render_logs_page(content, safe_name, available_logs)
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(page.encode("utf-8"))
                else:
                    self.send_response(404)
                    self.send_header("Content-Type", "text/plain")
                    self.end_headers()
                    self.wfile.write(f"Log file not found: {safe_name}\n".encode())
                return

            # --- /debug: Show debug/stderr log for today ---
            if self.path.rstrip("/") in ("/debug", "/stderr"):
                now_utc = datetime.now(timezone.utc)
                debug_content = None
                debug_label = None
                for delta_days in range(0, 3):
                    dt = now_utc - timedelta(days=delta_days)
                    tag = dt.strftime("%Y_%m_%d")
                    dpath = os.path.join("outputs", "logs", f"debug_{tag}.log")
                    if os.path.exists(dpath) and os.path.getsize(dpath) > 0:
                        with open(dpath, "r", encoding="utf-8", errors="replace") as f:
                            debug_content = f.read()
                        debug_label = f"debug_{tag}.log"
                        break
                available_logs = self._list_available_logs()
                page = self._render_logs_page(
                    debug_content or "No debug log found.",
                    debug_label or "debug (empty)",
                    available_logs,
                )
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(page.encode("utf-8"))
                return

            # --- Default: Health check endpoint ---
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "healthy", "service": "Autonomous-Stock-Trading-System"}')

        except Exception as e:
            # Catch-all: ensure we never silently return an empty response
            import traceback
            error_msg = f"Internal server error:\n{traceback.format_exc()}"
            try:
                self.send_response(500)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(error_msg.encode("utf-8"))
            except Exception:
                # Headers may already be sent; write error to body only
                try:
                    self.wfile.write(error_msg.encode("utf-8"))
                except Exception:
                    pass

    def log_message(self, format, *args):
        # Silence access logs to keep stdout clean
        pass


def keep_alive():
    """Background keep-alive ping to prevent Render free tier from sleeping."""
    time.sleep(180)  # Wait 3 mins after startup
    url = os.environ.get("RENDER_EXTERNAL_URL", "https://autonomous-stock-trader.onrender.com/")
    if not url.endswith("/"):
        url += "/"
    while True:
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": "RenderKeepAlive/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                RUNNER["last_keepalive_ok"] = datetime.now(timezone.utc).isoformat()
                RUNNER["keepalive_error"] = None
        except Exception as exc:
            RUNNER["keepalive_error"] = type(exc).__name__
            print(f"[WARN] Keepalive failed: {type(exc).__name__}", flush=True)
        time.sleep(300)  # Ping every 10 minutes (Render timeout is 15 minutes)


def start_health_server():
    port_str = os.environ.get("PORT", "10000")
    try:
        port = int(port_str)
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        print(f"  Health check server listening on port {port} (Render Free Web Service mode)", flush=True)
        # Start keep-alive ping in background
        threading.Thread(target=keep_alive, daemon=True).start()
        server.serve_forever()
    except Exception as e:
        print(f"  Warning: health server could not bind to port {port_str}: {e}", flush=True)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

_calendar_day = None
_calendar_rows = None


def exchange_phase():
    """Use the broker exchange calendar for DST, holidays and early closes."""
    global _calendar_day, _calendar_rows
    from scripts.session_timing import assess_session, ET
    from scripts.reconcile_paper_account import PaperReader
    now = datetime.now(timezone.utc)
    day = now.astimezone(ET).date().isoformat()
    try:
        if _calendar_day != day:
            rows = PaperReader().get("/v2/calendar", {"start": day, "end": day})
            _calendar_rows, _calendar_day = rows, day
        result = assess_session(now, _calendar_rows)
        RUNNER["phase"] = result["status"]
        RUNNER["market_close"] = result.get("market_close")
        RUNNER["last_calendar_check"] = now.isoformat()
        return result
    except Exception as exc:
        print(f"[ERROR] Exchange calendar unavailable ({type(exc).__name__}); no launch.", flush=True)
        RUNNER["phase"] = "UNKNOWN"
        return {"status": "UNKNOWN"}


def is_market_hours() -> bool:
    return exchange_phase()["status"] == "READY"


def is_post_session_window() -> bool:
    return exchange_phase()["status"] == "CLOSED"


def run_post_session(date_str: str):
    """
    Invoke scripts/post_session.py as a subprocess.
    Streams all output to Railway logs.
    """
    print(f"\n{'=' * 60}")
    print(f"  POST-SESSION PIPELINE -- {date_str}")
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

# ── Start HTTP health server for Render Free Web Service ──
threading.Thread(target=start_health_server, daemon=True).start()

# Track which date we last ran the post-session pipeline (prevent duplicate runs)
last_post_session_date: str = ""
attempted_session_date: str = ""

while True:
    now_utc  = datetime.now(timezone.utc)
    today    = now_utc.strftime("%Y-%m-%d")
    date_tag = now_utc.strftime("%Y_%m_%d")

    # ──────────────────────────────────────────────────────────────────────────
    # Branch A: Market is OPEN — run the trading bot
    # ──────────────────────────────────────────────────────────────────────────
    if is_market_hours() and attempted_session_date != today:
        attempted_session_date = today
        log_path = f"outputs/logs/session_{date_tag}.txt"
        os.makedirs("outputs/logs", exist_ok=True)

        print(f"\n[{now_utc.strftime('%H:%M:%S UTC')}] Market OPEN — launching trading bot...", flush=True)
        print(f"  Session log: {log_path}", flush=True)

        try:
            debug_path = f"outputs/logs/debug_{date_tag}.log"

            env = os.environ.copy()
            env["TRADING_EXECUTION_SOURCE"] = "render-cloud"
            env["PYTHONUNBUFFERED"] = "1"
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"

            # Launch main.py live — stdout = clean print output, stderr = Python logging
            process = subprocess.Popen(
                [sys.executable, "-X", "utf8", "-u", "main.py", "live"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,     # keep stderr separate from clean output
                text=True,
                bufsize=1,                  # line-buffered for real-time log streaming
                encoding="utf-8",
                errors="replace",
                env=env,
            )

            WORKER = process
            RUNNER.update(worker_pid=process.pid,
                          worker_started_at=datetime.now(timezone.utc).isoformat(),
                          worker_exit_code=None)
            # ── Thread: drain stdout → session log (clean tabular output only) ──
            def stream_stdout():
                with open(log_path, "a", encoding="utf-8") as lf:
                    while True:
                        line = process.stdout.readline()
                        if not line:
                            break
                        RUNNER["last_worker_output"] = datetime.now(timezone.utc).isoformat()
                        print(line, end="", flush=True)
                        lf.write(line)
                        lf.flush()

            # ── Thread: drain stderr → debug log (Python logging INFO lines) ──
            def stream_stderr():
                with open(debug_path, "a", encoding="utf-8") as df:
                    while True:
                        line = process.stderr.readline()
                        if not line:
                            break
                        RUNNER["last_worker_output"] = datetime.now(timezone.utc).isoformat()
                        df.write(line)
                        df.flush()
                        # Surface critical errors or crashes to Render console
                        if any(k in line for k in ("ERROR", "Traceback", "Exception", "CRITICAL")):
                            print(line, end="", flush=True)

            t_out = threading.Thread(target=stream_stdout, daemon=True)
            t_err = threading.Thread(target=stream_stderr, daemon=True)
            t_out.start()
            t_err.start()
            t_out.join()
            t_err.join()

            process.wait()
            exit_code = process.returncode
            RUNNER["worker_exit_code"] = exit_code
            print(
                f"\n[{datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}] "
                f"Bot exited with code: {exit_code}",
                flush=True
            )

            if exit_code != 0:
                print("  Non-zero exit — bot may have crashed. Restart withheld to avoid resetting daily risk state; inspect /status and /debug.", flush=True)

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

        if run_post_session(today):
            last_post_session_date = today   # Retry failed publication on the next pass

        print("  Sleeping 15 minutes before next check...", flush=True)
        time.sleep(900)

    # ──────────────────────────────────────────────────────────────────────────
    # Branch C: Market is CLOSED (and not post-session window) — sleep
    # ──────────────────────────────────────────────────────────────────────────
    else:
        phase = exchange_phase()
        if phase["status"] == "LATE_START":
            print("[ERROR] MISSED_SESSION: opening tolerance exceeded; not a successful trading session.", flush=True)
        day_name = now_utc.strftime("%A")
        time_str = now_utc.strftime("%H:%M UTC")
        print(f"  Market CLOSED — {day_name} {time_str} — checking again in 30 seconds", flush=True)
        time.sleep(30)   # Check opening promptly; no ten-minute launch lag
