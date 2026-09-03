"""
run_live_logger.py -- Live trading launcher with continuous UTF-8 log streaming.
"""
import sys
import subprocess
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
os.chdir(PROJECT_ROOT)

OUTPUTS_DIR = os.path.join(PROJECT_ROOT, "outputs")
os.makedirs(OUTPUTS_DIR, exist_ok=True)

OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

from datetime import datetime

import re
from datetime import datetime

today_str = datetime.now().strftime("%Y_%m_%d")

def get_next_session_number():
    max_num = 0
    pattern = re.compile(r"se[e]?ion[ _](\d+)\.txt", re.IGNORECASE)
    for folder in [OUTPUTS_DIR, LOGS_DIR, os.path.join(LOGS_DIR, "legacy"), PROJECT_ROOT]:
        if os.path.exists(folder):
            for fname in os.listdir(folder):
                m = pattern.match(fname)
                if m:
                    num = int(m.group(1))
                    if num > max_num:
                        max_num = num
    return max_num + 1 if max_num > 0 else 1

LOGS_DIR = os.path.join(OUTPUTS_DIR, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

if len(sys.argv) > 1:
    session_arg = sys.argv[1]
    if session_arg.isdigit():
        session_num = session_arg
        date_str = today_str
    elif "_" in session_arg or "-" in session_arg:
        date_str = session_arg.replace("-", "_")
        session_num = str(get_next_session_number())
    else:
        session_num = session_arg
        date_str = today_str
else:
    session_num = str(get_next_session_number())
    date_str = today_str

# Systematic log destinations:
# 1. Primary daily log: outputs/logs/session_YYYY_MM_DD.txt (tracked by git / Railway / post_session)
# 2. Numbered session log: outputs/logs/session_N.txt
# 3. Convenience root-outputs log: outputs/session_YYYY_MM_DD.txt
# 4. Live streaming log: outputs/trader.log (read by 'python main.py logs')
target_log_files = list(dict.fromkeys([
    os.path.join(LOGS_DIR, f"session_{date_str}.txt"),
    os.path.join(LOGS_DIR, f"session_{session_num}.txt"),
    os.path.join(OUTPUTS_DIR, f"session_{date_str}.txt"),
    os.path.join(OUTPUTS_DIR, "trader.log"),
]))

# Open log file handles with line buffering in append mode (UTF-8)
handles = []
for file_path in target_log_files:
    try:
        h = open(file_path, "a", encoding="utf-8", buffering=1, errors="replace")
        h.write(f"\n{'='*60}\n  SESSION {session_num} ({date_str}) -- {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n{'='*60}\n")
        h.flush()
        handles.append(h)
    except Exception as e:
        print(f"Warning: could not open {file_path}: {e}")

print(f"Starting main.py live for {date_str} (Session {session_num})... Output streaming to UTF-8 log files:")
for path in target_log_files:
    print(f"  -> {path}")

env = os.environ.copy()
env["PYTHONIOENCODING"] = "utf-8"
env["PYTHONUTF8"] = "1"

proc = subprocess.Popen(
    [sys.executable, "-X", "utf8", "-u", "main.py", "live"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1,
    cwd=PROJECT_ROOT,
    encoding="utf-8",
    errors="replace",
    env=env,
)

try:
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
        for h in handles:
            h.write(line)
            h.flush()
except KeyboardInterrupt:
    proc.terminate()
finally:
    proc.wait()
    for h in handles:
        h.close()
