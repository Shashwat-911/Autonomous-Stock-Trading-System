"""Shared staging/publishing path for live wrap-up and scheduled reports."""
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from zoneinfo import ZoneInfo

from analytics.measurement import build_report, day_of, episode_metrics
from scripts.reconcile_paper_account import PaperReader, collect, write_csv, write_json
from scripts.reconciliation import timestamp

ROOT = Path(__file__).resolve().parents[1]


def atomic_text(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".report-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def _run_report(snapshot=None, start=None, end=None, since=None, publish=True,
               private_root=None, public_root=None, reader=None):
    """Stage all evidence first; publish aggregate v2 outputs only after checks pass."""
    private_root = Path(private_root or ROOT / "outputs/reporting_private")
    public_root = Path(public_root or ROOT / "outputs/measurement_v2")
    stage = private_root / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    stage.mkdir(parents=True)
    if snapshot is None:
        reader = reader or PaperReader()
        account = reader.get("/v2/account")
        start = start or day_of(account["created_at"])
        end = end or datetime.now(timezone.utc).astimezone(ZoneInfo("America/New_York")).date().isoformat()
        snapshot = collect(reader, date.fromisoformat(start), date.fromisoformat(end))
    start = start or day_of(snapshot["account_created_at"])
    end = end or snapshot["requested_end"]
    if end > snapshot["requested_end"]:
        raise ValueError("Report end exceeds snapshot history coverage")
    result = build_report(snapshot, start, end, since=since)
    summary = result["summary"]
    write_json(stage / "snapshot.json", snapshot)
    write_json(stage / "performance_summary.json", summary)
    write_csv(stage / "completed_position_episodes.csv", result["episodes"])
    write_csv(stage / "unfinished_position_episodes.csv", result["unfinished"])
    write_csv(stage / "open_fifo_lots.csv", result["lots"])
    write_csv(stage / "matched_fifo_fragments.csv", result["fragments"])
    write_csv(stage / "daily_account_measurement.csv", result["daily"])
    write_csv(stage / "broker_equity_history.csv", result["equity"])
    symbols = sorted({e["ticker"] for e in result["episodes"]})
    write_csv(stage / "symbol_summary.csv", [{"ticker": s, **episode_metrics(
        [e for e in result["episodes"] if e["ticker"] == s])} for s in symbols])
    if publish:
        if summary["issues"]:
            # Explicit failure status prevents consumers silently presenting stale success.
            atomic_text(public_root / ("run_report_status.json" if since else "report_status.json"), json.dumps({
                "status": "REQUIRES_REVIEW", "generated_at": summary["generated_at"],
                "issues": summary["issues"]}, indent=2))
            raise ValueError("Measurement checks failed; private report staged, aggregate promotion refused")
        # Immutable generation + atomic pointer avoids mixed files between concurrent reports.
        generation = public_root / "generations" / stage.name
        generation.mkdir(parents=True)
        for name in ("performance_summary.json", "daily_account_measurement.csv",
                     "broker_equity_history.csv", "symbol_summary.csv"):
            atomic_text(generation / name, (stage / name).read_text(encoding="utf-8"))
        pointer = "latest_run.json" if since else "latest.json"
        atomic_text(public_root / pointer, json.dumps({"generation": stage.name,
                    "schema_version": 2, "snapshot_sha256": summary["snapshot_sha256"]}, indent=2))
        atomic_text(public_root / ("run_report_status.json" if since else "report_status.json"), json.dumps({
            "status": summary["status"], "generated_at": summary["generated_at"],
            "generation": stage.name}, indent=2))
    return result, stage


def run_report(**kwargs):
    """Network and validation failures invalidate latest status, never mimic zero trades."""
    root = Path(kwargs.get("public_root") or ROOT / "outputs/measurement_v2")
    status_file = root / ("run_report_status.json" if kwargs.get("since") else "report_status.json")
    if kwargs.get("publish", True):
        atomic_text(status_file, json.dumps({"status": "IN_PROGRESS"}))
    try:
        return _run_report(**kwargs)
    except Exception:
        if kwargs.get("publish", True):
            # Do not serialize network exception bodies or credential-bearing objects.
            existing = json.loads(status_file.read_text()) if status_file.exists() else {}
            if existing.get("status") == "REQUIRES_REVIEW":
                raise
            atomic_text(status_file, json.dumps({"status": "FAILED",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "reason": "Collection or validation failed; inspect private evidence and local error."}))
        raise


def latest_report(root=None):
    root = Path(root or ROOT / "outputs/measurement_v2")
    status = json.loads((root / "report_status.json").read_text(encoding="utf-8"))
    if status["status"] != "VALIDATED_ACCOUNT_MEASUREMENT":
        raise ValueError("Latest reporting attempt failed; refusing stale measurement")
    pointer = json.loads((root / "latest.json").read_text(encoding="utf-8"))
    name = pointer["generation"]
    if name != status.get("generation"):
        raise ValueError("Incomplete report publication; generation/status disagree")
    if Path(name).name != name or ".." in name:
        raise ValueError("Invalid report generation")
    return root / "generations" / name
