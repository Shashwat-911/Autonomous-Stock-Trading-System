"""Authoritative fill-activity reports; legacy output files are preserved."""
import argparse
from datetime import date
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analytics.reporting import run_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--start", type=date.fromisoformat)
    parser.add_argument("--end", type=date.fromisoformat)
    parser.add_argument("--stage-only", action="store_true")
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8")) if args.snapshot else None
    result, stage = run_report(snapshot=snapshot, start=str(args.start) if args.start else None,
                               end=str(args.end) if args.end else None, publish=not args.stage_only)
    print(json.dumps(result["summary"], indent=2))
    print(f"Private evidence and reconstructed trades: {stage}")


if __name__ == "__main__":
    main()
