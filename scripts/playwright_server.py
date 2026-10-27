"""Serve the production monitor with synthetic logs, without starting trading."""
import os
import sys
import tempfile
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# The launch loop is guarded by __main__; importing only defines the monitor.
from scripts import cloud_launcher

if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="trader-playwright-") as folder:
        os.chdir(folder)
        logs = Path("outputs/logs")
        logs.mkdir(parents=True)
        (logs / "session_2000_01_01.txt").write_text(
            "PLAYWRIGHT SYNTHETIC SESSION — no broker connection\n"
            "AAPL: example observation\n<script>window.logInjected=true</script>\n",
            encoding="utf-8",
        )
        cloud_launcher.RUNNER.update(source="playwright-fixture", phase="MONITOR_ONLY")
        port = int(os.environ.get("PLAYWRIGHT_PORT", "9101"))
        print(f"Read-only monitor with synthetic logs: http://127.0.0.1:{port}", flush=True)
        ThreadingHTTPServer(("127.0.0.1", port), cloud_launcher.HealthCheckHandler).serve_forever()
