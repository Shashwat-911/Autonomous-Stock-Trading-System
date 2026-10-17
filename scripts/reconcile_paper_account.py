"""Read-only Alpaca paper audit. Raw account exports stay local and gitignored."""
import argparse
import csv
import json
import os
from pathlib import Path
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.reconciliation import amount, timestamp, match_fills, activity_pages, order_pages

ROOT = Path(__file__).resolve().parents[1]
ET = ZoneInfo("America/New_York")
UTC = timezone.utc


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class PaperReader:
    """Fixed paper origin and allowlisted GETs only; never imports trading code."""
    PATHS = {"/v2/account", "/v2/positions", "/v2/orders",
             "/v2/account/activities", "/v2/account/portfolio/history"}

    def __init__(self):
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
        key = os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID")
        secret = os.getenv("ALPACA_SECRET_KEY") or os.getenv("APCA_API_SECRET_KEY")
        if not key or not secret:
            raise ValueError("Paper credentials missing from environment/.env")
        self.headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
        self.opener = build_opener(NoRedirect())

    def get(self, path, params=None):
        if path not in self.PATHS and not re.fullmatch(r"/v2/orders/[0-9a-fA-F-]{36}", path):
            raise ValueError("Endpoint not permitted by read-only audit")
        url = "https://paper-api.alpaca.markets" + path
        if params:
            url += "?" + urlencode(params)
        for attempt in range(4):
            try:
                request = Request(url, headers=self.headers, method="GET")
                with self.opener.open(request, timeout=45) as response:
                    return json.load(response)
            except HTTPError as exc:
                if exc.code not in (429, 500, 502, 503, 504) or attempt == 3:
                    # Never emit response bodies, headers or credentials.
                    raise RuntimeError(f"Paper API GET {path}: HTTP {exc.code}") from None
            except (URLError, TimeoutError):
                if attempt == 3:
                    raise RuntimeError(f"Paper API GET {path}: network unavailable") from None
            time.sleep(2 ** attempt)


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def write_csv(path, rows):
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", newline="", encoding="utf-8") as stream:
        if fields:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)


def local_date(value):
    return timestamp(value).astimezone(ET).date()


def session_evidence(log_dir):
    """Canonical dated logs only. Never guess timezone from naive log timestamps."""
    sessions, order_mentions = {}, {}
    for path in sorted(log_dir.glob("session_????_??_??.txt")):
        text = path.read_text(encoding="utf-8", errors="replace")
        day = date.fromisoformat(path.stem.removeprefix("session_").replace("_", "-"))
        starts = re.findall(r"Session started\. Actual broker equity: \$([\d,.]+)", text)
        ends = re.findall(r"Equity: \$([\d,.]+) \| Long exposure:", text)
        sessions[day] = {
            "run_start_equity": starts[0].replace(",", "") if starts else "",
            "run_end_equity": ends[-1].replace(",", "") if ends else "",
            "multiple_starts": len(starts) > 1,
            "session_skipped": "Session skipped" in text,
        }
        for order_id in re.findall(r"\b[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\b", text):
            order_mentions.setdefault(order_id.lower(), []).append(path.name)
    return sessions, order_mentions


def collect(reader, start, end):
    account = reader.get("/v2/account")
    now = datetime.now(UTC)
    print("Reading all retained account activities...", flush=True)
    activities = activity_pages(reader.get)
    created = timestamp(account["created_at"])
    print("Reading orders with timestamp-safe pagination...", flush=True)
    orders = order_pages(reader.get, created - timedelta(days=1), now + timedelta(seconds=1))
    by_id = {o["id"]: o for o in orders}
    # Recover orders referenced by executions but omitted by the list endpoint.
    for activity in activities:
        oid = activity.get("order_id")
        if oid and oid not in by_id:
            by_id[oid] = reader.get("/v2/orders/" + oid)
    history = reader.get("/v2/account/portfolio/history", {
        "start": (start - timedelta(days=7)).isoformat(),
        "end": (end + timedelta(days=1)).isoformat(), "timeframe": "1D"})
    return {"schema_version": 1, "fetched_at": now.isoformat(),
            "requested_start": str(start), "requested_end": str(end),
            "account_created_at": account["created_at"],
            "account_snapshot": {k: account.get(k) for k in
                                 ("equity", "cash", "long_market_value", "short_market_value")},
            "positions_now": reader.get("/v2/positions"),
            "activities": activities, "orders": list(by_id.values()), "portfolio_history": history}


def analyze(snapshot, start, end, output, ledger_path, log_dir):
    activities = snapshot["activities"]
    fills = [a for a in activities if a.get("activity_type") == "FILL"]
    through_end = [a for a in fills if local_date(a["transaction_time"]) <= end]
    before_start = [a for a in fills if local_date(a["transaction_time"]) < start]
    matches, end_lots = match_fills(through_end)
    _, start_lots = match_fills(before_start)
    matches = [m for m in matches if start <= local_date(m["exit_time"]) <= end]
    window_fills = [a for a in through_end if start <= local_date(a["transaction_time"])]
    sessions, mentions = session_evidence(log_dir)
    orders = {o["id"]: o for o in snapshot["orders"]}
    fill_rows = []
    for f in window_fills:
        order = orders.get(f["order_id"], {})
        direct = mentions.get(f["order_id"].lower(), [])
        parent = mentions.get(str(order.get("parent_order_id", "")).lower(), [])
        fill_rows.append({**f, "client_order_id": order.get("client_order_id", ""),
                          "order_type": order.get("type", ""),
                          "log_evidence": "direct_order_id" if direct else
                                          "parent_order_id_only" if parent else "no_id_match",
                          "log_files": ";".join(direct or parent)})
    nontrade = []
    for a in activities:
        if a.get("activity_type") == "FILL":
            continue
        # Non-trade date is economic/settlement date; API retrieval is by creation.
        when = str(a.get("date") or a.get("transaction_time") or "")[:10]
        if when and start <= date.fromisoformat(when) <= end:
            nontrade.append(a)
    history = snapshot["portfolio_history"]
    broker_equity = {}
    for ts, value in zip(history.get("timestamp", []), history.get("equity", [])):
        if value is not None:
            broker_equity[datetime.fromtimestamp(ts, ET).date()] = amount(value)
    ledger = {}
    if ledger_path.exists():
        with ledger_path.open(encoding="utf-8-sig") as stream:
            ledger = {date.fromisoformat(r["timestamp"]): amount(r["equity"])
                      for r in csv.DictReader(stream)}
    daily = []
    realized_by_day = {}
    cash_by_day = {}
    for m in matches:
        day = local_date(m["exit_time"])
        realized_by_day[day] = realized_by_day.get(day, amount(0)) + amount(m["gross_pnl"])
    for a in nontrade:
        day = date.fromisoformat(str(a.get("date") or a.get("transaction_time"))[:10])
        cash_by_day[day] = cash_by_day.get(day, amount(0)) + amount(a.get("net_amount"))
    days = sorted(set(ledger) | set(broker_equity) | set(realized_by_day) | set(cash_by_day))
    prior_local = prior_broker = None
    for day in days:
        le, be = ledger.get(day), broker_equity.get(day)
        if start <= day <= end:
            s = sessions.get(day, {})
            run_change = (amount(s["run_end_equity"]) - amount(s["run_start_equity"])
                          if s.get("run_start_equity") and s.get("run_end_equity") else None)
            local_change = le - prior_local if le is not None and prior_local is not None else None
            broker_change = be - prior_broker if be is not None and prior_broker is not None else None
            realized = realized_by_day.get(day, amount(0))
            cash = cash_by_day.get(day, amount(0))
            daily.append({"date": str(day), "local_equity": le, "broker_equity": be,
                          "local_minus_broker": le-be if le is not None and be is not None else None,
                          "local_equity_change": local_change, "broker_equity_change": broker_change,
                          "matched_gross_realized": realized, "nontrade_net_amount": cash,
                          "residual_including_unrealized": broker_change-realized-cash
                          if broker_change is not None else None,
                          **s, "recorded_run_change": run_change,
                          "outside_recorded_run_or_snapshot_difference": local_change-run_change
                          if local_change is not None and run_change is not None else None})
        if le is not None:
            prior_local = le
        if be is not None:
            prior_broker = be
    # Identify unsupported basis-changing events across the entire inventory history.
    cash_only = {"DIV", "DIVNRA", "DIVFT", "DIVCGL", "DIVCGS", "INT", "FEE", "CFEE",
                 "FINT", "CSD", "CSW", "JNLC"}
    unsupported = [a for a in activities if a.get("activity_type") not in cash_only | {"FILL"}
                   and str(a.get("date") or a.get("transaction_time") or "9999")[:10] <= str(end)]
    # Compare cumulative executions with orders, only when all fills precede end.
    fill_totals = {}
    for f in fills:
        fill_totals[f["order_id"]] = fill_totals.get(f["order_id"], amount(0)) + amount(f["qty"])
    qty_gaps = [{"order_id": oid, "symbol": o.get("symbol"),
                 "order_filled_qty": o.get("filled_qty"),
                 "activity_qty": str(fill_totals.get(oid, amount(0)))}
                for oid, o in orders.items()
                if amount(o.get("filled_qty")) != fill_totals.get(oid, amount(0))]
    baseline_days = [d for d in broker_equity if d < start]
    baseline = broker_equity[max(baseline_days)] if baseline_days else None
    final = broker_equity.get(end)
    gross = sum((amount(m["gross_pnl"]) for m in matches), amount(0))
    nontrade_total = sum((amount(a.get("net_amount")) for a in nontrade), amount(0))
    bridge_residual = final - baseline - gross - nontrade_total if baseline is not None and final is not None else None
    _, current_lots = match_fills(fills)
    derived_qty, observed_qty = {}, {}
    for lot in current_lots:
        sym = lot["symbol"]
        derived_qty[sym] = derived_qty.get(sym, amount(0)) + amount(lot["signed_qty"])
    for pos in snapshot["positions_now"]:
        observed_qty[pos["symbol"]] = amount(pos["qty"])
    position_gaps = [{"symbol": sym, "activity_inventory": derived_qty.get(sym, amount(0)),
                      "current_broker_inventory": observed_qty.get(sym, amount(0))}
                     for sym in sorted(set(derived_qty) | set(observed_qty))
                     if derived_qty.get(sym, amount(0)) != observed_qty.get(sym, amount(0))]
    nontrade_by_type = {}
    for a in nontrade:
        kind = a["activity_type"]
        nontrade_by_type[kind] = nontrade_by_type.get(kind, amount(0)) + amount(a.get("net_amount"))
    summary = {
        "period": [str(start), str(end)], "fetched_at": snapshot["fetched_at"],
        "retained_activities": len(activities), "orders_including_legs": len(orders),
        "window_fill_events": len(window_fills), "fifo_matched_fragments": len(matches),
        "gross_realized_pnl_provisional": str(sum((amount(m["gross_pnl"]) for m in matches), amount(0))),
        "nontrade_net_amount": str(sum((amount(a.get("net_amount")) for a in nontrade), amount(0))),
        "opening_lots": len(start_lots), "ending_lots": len(end_lots),
        "fills_without_direct_log_id": sum(r["log_evidence"] != "direct_order_id" for r in fill_rows),
        "order_activity_quantity_mismatches": len(qty_gaps),
        "unsupported_inventory_activities": len(unsupported),
        "current_position_quantity_mismatches": len(position_gaps),
        "nontrade_net_by_type": {k: str(v) for k, v in nontrade_by_type.items()},
        "broker_equity_bridge": {
            "baseline_date": str(max(baseline_days)) if baseline_days else None,
            "baseline_equity": str(baseline) if baseline is not None else None,
            "ending_equity": str(final) if final is not None else None,
            "residual_including_unrealized": str(bridge_residual) if bridge_residual is not None else None,
            "both_inventory_boundaries_flat": not start_lots and not end_lots,
        },
        "status": "REQUIRES_REVIEW",
        "limitations": [
            "No automatic claim of complete reconciliation or strategy edge.",
            "FIFO P&L is provisional until retained history, opening basis and corporate actions are verified.",
            "Matched fragments are not independent trades; do not use their count as a win-rate denominator.",
            "Residual includes change in unrealized P&L and timing differences, not necessarily missing cash.",
            "Current positions are a retrieval-time snapshot, not historical end-of-window positions.",
            "No order-ID match means absent evidence in canonical local logs, not proof of an external process.",
            "Daily changes span consecutive available observations; missing days are not assumed flat.",
        ],
    }
    write_csv(output / "fills_with_log_evidence.csv", fill_rows)
    write_csv(output / "matched_lots.csv", matches)
    write_csv(output / "opening_lots.csv", start_lots)
    write_csv(output / "ending_lots.csv", end_lots)
    write_csv(output / "nontrade_activities.csv", nontrade)
    write_csv(output / "unsupported_activities.csv", unsupported)
    write_csv(output / "order_activity_quantity_gaps.csv", qty_gaps)
    write_csv(output / "current_position_quantity_gaps.csv", position_gaps)
    write_csv(output / "daily_reconciliation.csv", daily)
    write_json(output / "summary.json", summary)
    lines = ["# Paper-account reconciliation", "", "Status: REQUIRES_REVIEW", "",
             f"Period: {start} through {end} (America/New_York).", "",
             f"Fill events: {len(window_fills)}; matched FIFO fragments: {len(matches)}.",
             f"Provisional gross realized P&L: ${summary['gross_realized_pnl_provisional']}.",
             f"Order/activity quantity mismatches: {len(qty_gaps)}.",
             f"Unsupported inventory activity records: {len(unsupported)}.", "",
             "## October 14-16 attribution", "",
             "| Date | Local equity change | Recorded run change | Outside run / snapshot difference |",
             "|---|---:|---:|---:|"]
    for row in daily:
        if "2026-10-14" <= row["date"] <= "2026-10-16":
            lines.append(f"| {row['date']} | {row['local_equity_change']} | {row['recorded_run_change']} | "
                         f"{row['outside_recorded_run_or_snapshot_difference']} |")
    lines += ["", "## Interpretation limits", ""] + ["- " + s for s in summary["limitations"]]
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat, default=date(2026, 8, 11))
    parser.add_argument("--end", type=date.fromisoformat, default=date(2026, 10, 16))
    parser.add_argument("--snapshot", type=Path, help="Replay saved snapshot without network/credentials")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/private_reconciliation")
    args = parser.parse_args()
    if args.start > args.end:
        parser.error("start must not follow end")
    args.output.mkdir(parents=True, exist_ok=True)
    # Unique run directories preserve prior successful evidence if a later run fails.
    output = args.output / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    output.mkdir()
    try:
        snapshot = (json.loads(args.snapshot.read_text(encoding="utf-8")) if args.snapshot
                    else collect(PaperReader(), args.start, args.end))
        if args.snapshot and (str(args.start) < snapshot["requested_start"] or
                              str(args.end) > snapshot["requested_end"]):
            raise ValueError("Replay dates exceed snapshot portfolio-history coverage")
        write_json(output / "snapshot.json", snapshot)
        result = analyze(snapshot, args.start, args.end, output,
                         ROOT / "outputs/alpaca_equity_history.csv", ROOT / "outputs/logs")
        print(json.dumps(result, indent=2))
        print(f"Private audit artifacts: {output}")
    except (ValueError, RuntimeError, KeyError, OSError) as exc:
        write_json(output / "failure.json", {"status": "FAILED", "error": str(exc)})
        print(f"Audit failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
