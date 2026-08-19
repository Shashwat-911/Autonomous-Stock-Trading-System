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

session_num = sys.argv[1] if len(sys.argv) > 1 else "5"

target_log_files = [
    os.path.join(OUTPUTS_DIR, f"session {session_num}.txt"),
    os.path.join(OUTPUTS_DIR, f"session_{session_num}.txt"),
    os.path.join(OUTPUTS_DIR, f"seeion {session_num}.txt"),
    os.path.join(OUTPUT_DIR, f"session {session_num}.txt"),
    os.path.join(OUTPUT_DIR, f"session_{session_num}.txt"),
    os.path.join(PROJECT_ROOT, f"session {session_num}.txt"),
    os.path.join(PROJECT_ROOT, f"session_{session_num}.txt"),
    os.path.join(PROJECT_ROOT, f"seeion {session_num}.txt"),
]

# Open log file handles with line buffering (UTF-8)
handles = []
for file_path in target_log_files:
    # Clear / truncate existing file or append
    handles.append(open(file_path, "w", encoding="utf-8", buffering=1))

print(f"Starting main.py live... Output streaming to UTF-8 log files:")
for path in target_log_files:
    print(f"  -> {path}")

proc = subprocess.Popen(
    [sys.executable, "-u", "main.py", "live"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1,
    cwd=PROJECT_ROOT,
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
