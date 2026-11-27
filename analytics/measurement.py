"""Execution-based accounting and flat-to-flat episodes; no trading side effects."""
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from zoneinfo import ZoneInfo

from scripts.reconciliation import amount, match_fills, timestamp

ET = ZoneInfo("America/New_York")
CASH_TYPES = {"DIV", "DIVNRA", "DIVFT", "DIVCGL", "DIVCGS", "INT", "FEE", "CFEE",
              "FINT", "CSD", "CSW", "JNLC"}


def day_of(value):
    return timestamp(value).astimezone(ET).date().isoformat()


def position_episodes(activities):
    """One trade = symbol position flat-to-flat, reversal split at zero.

    Partial reductions realize accounting P&L but do not complete a trade.
    Gross episode P&L is cash proceeds minus basis (opposite for shorts).
    """
    match_fills(activities)  # shared validation: duplicate IDs, positive finite fills
    state, completed = {}, []
    fills = sorted((a for a in activities if a.get("activity_type") == "FILL"),
                   key=lambda a: (timestamp(a["transaction_time"]), a["id"]))
    for f in fills:
        sym = f["symbol"]
        direction = 1 if f["side"].lower() in ("buy", "buy_to_cover") else -1
        remaining, price = amount(f["qty"]), amount(f["price"])
        while remaining:
            if sym not in state:
                state[sym] = {"symbol": sym, "direction": direction, "position": amount(0),
                              "entry_time": f["transaction_time"], "entry_qty": amount(0),
                              "exit_qty": amount(0), "entry_notional": amount(0),
                              "exit_notional": amount(0)}
            e = state[sym]
            if direction == e["direction"]:
                e["position"] += remaining
                e["entry_qty"] += remaining
                e["entry_notional"] += remaining * price
                remaining = amount(0)
            else:
                qty = min(remaining, e["position"])
                e["exit_qty"] += qty
                e["exit_notional"] += qty * price
                e["position"] -= qty
                remaining -= qty
                if not e["position"]:
                    pnl = (e["exit_notional"] - e["entry_notional"]) * e["direction"]
                    completed.append({
                        "ticker": sym, "direction": "long" if e["direction"] == 1 else "short",
                        "entry_time": e["entry_time"], "exit_time": f["transaction_time"],
                        "qty": str(e["entry_qty"]), "pnl": str(pnl),
                        "entry_price": str(e["entry_notional"] / e["entry_qty"]),
                        "exit_price": str(e["exit_notional"] / e["exit_qty"]),
                        "pnl_pct": str(100 * pnl / e["entry_notional"]),
                        "hold_duration_minutes": (timestamp(f["transaction_time"]) - timestamp(e["entry_time"])).total_seconds()/60,
                        "side": "round_trip", "basis": "gross_fill_activity_episode",
                    })
                    del state[sym]
    unfinished = [{"ticker": sym, "direction": "long" if e["direction"] == 1 else "short",
                   "entry_time": e["entry_time"], "signed_qty": str(e["position"] * e["direction"])}
                  for sym, e in sorted(state.items())]
    return completed, unfinished


def episode_metrics(episodes):
    pnls = [amount(e["pnl"]) for e in episodes]
    wins, losses = [x for x in pnls if x > 0], [x for x in pnls if x < 0]
    n = len(pnls)
    return {"total_trades": n, "winning_trades": len(wins), "losing_trades": len(losses),
            "breakeven_trades": n-len(wins)-len(losses),
            "win_rate": len(wins)/n if n else None,
            "expectancy": float(sum(pnls)/n) if n else None,
            "profit_factor": float(sum(wins)/abs(sum(losses))) if losses else None,
            "profit_factor_status": "defined" if losses else "no_gross_losses" if wins else "no_nonzero_outcomes",
            "avg_gain": float(sum(wins)/len(wins)) if wins else None,
            "avg_loss": float(sum(losses)/len(losses)) if losses else None,
            "completed_episode_gross_pnl": str(sum(pnls, amount(0))),
            "trade_metric_basis": "gross_completed_flat_to_flat_episodes"}


def equity_observations(snapshot):
    """Preserve broker valuation timestamps; never substitute current account equity.

    Same-day bars are excluded unless a captured exchange calendar establishes
    that the regular session closed before retrieval. Later fees can revise history.
    """
    history = snapshot["portfolio_history"]
    times, values = history.get("timestamp", []), history.get("equity", [])
    if len(times) != len(values):
        raise ValueError("Portfolio history timestamp/value length mismatch")
    fetched = timestamp(snapshot["fetched_at"])
    today = fetched.astimezone(ET).date().isoformat()
    closes = {c["date"]: datetime.fromisoformat(c["date"] + "T" + c["close"]).replace(tzinfo=ET)
              for c in snapshot.get("calendar", [])}
    rows, seen = [], set()
    for ts, value in zip(times, values):
        dt = datetime.fromtimestamp(ts, timezone.utc)
        day = dt.astimezone(ET).date().isoformat()
        if value is None or day > today:
            continue
        if day == today and (day not in closes or fetched < closes[day]):
            continue
        if day in seen:
            raise ValueError("Duplicate daily broker valuation date")
        seen.add(day)
        rows.append({"timestamp": day, "valuation_timestamp": dt.isoformat(),
                     "equity": str(amount(value)), "retrieved_at": snapshot["fetched_at"],
                     "source": "broker_portfolio_history_1D"})
    for observation in snapshot.get("closing_equity_observations", []):
        day = observation["timestamp"]
        close = closes.get(day)
        if day not in seen and close and timestamp(observation["valuation_timestamp"]) == close and fetched >= close:
            rows.append(observation)
            seen.add(day)
    return sorted(rows, key=lambda r: r["timestamp"])


def build_report(snapshot, start, end, since=None):
    """Reconstruct history before selecting completed episodes and daily realizations."""
    if start > end:
        raise ValueError("start must not follow end")
    all_activities = snapshot["activities"]
    activity_ids = [a["id"] for a in all_activities]
    if len(set(activity_ids)) != len(activity_ids):
        raise ValueError("Duplicate account activity ID")
    fills = [a for a in all_activities if a.get("activity_type") == "FILL"
             and day_of(a["transaction_time"]) <= end]
    fragments, lots = match_fills(fills)
    completed, unfinished = position_episodes(fills)
    selected = [e for e in completed if start <= day_of(e["exit_time"]) <= end
                and (since is None or timestamp(e["exit_time"]) >= timestamp(since))]
    for e in selected:
        e["entry_before_reporting_boundary"] = (day_of(e["entry_time"]) < start or
            (since is not None and timestamp(e["entry_time"]) < timestamp(since)))
    unknown = [a for a in all_activities if a.get("activity_type") not in CASH_TYPES | {"FILL"}]
    issues = []
    if unknown:
        issues.append("Unsupported inventory/cash activity types: " + ", ".join(sorted({a.get("activity_type", "missing") for a in unknown})))
    # Full retained order/position consistency is a coverage check, not proof of basis.
    totals = defaultdict(Decimal)
    for a in all_activities:
        if a.get("activity_type") == "FILL":
            totals[a["order_id"]] += amount(a["qty"])
    orders = {o["id"]: o for o in snapshot["orders"]}
    gaps = sum(amount(o.get("filled_qty")) != totals[oid] for oid, o in orders.items())
    missing_orders = sum(oid not in orders for oid in totals)
    if gaps or missing_orders:
        issues.append(f"Order/activity coverage mismatch: {gaps} quantities, {missing_orders} missing orders")
    lifetime_fragments, current_lots = match_fills(all_activities)
    derived = defaultdict(Decimal)
    for lot in current_lots:
        derived[lot["symbol"]] += amount(lot["signed_qty"])
    observed = {p["symbol"]: amount(p["qty"]) for p in snapshot["positions_now"]}
    if any(derived[s] != observed.get(s, amount(0)) for s in set(derived) | set(observed)):
        issues.append("Current inventory differs from retained fills; opening basis may be missing")
    nontrade = [a for a in all_activities if a.get("activity_type") != "FILL"]
    if any(not a.get("date") or a.get("net_amount") is None for a in nontrade):
        issues.append("Non-trade activity lacks economic date or cash amount")
    funding = [a for a in nontrade if a.get("activity_type") in {"CSD", "CSW", "JNLC"}]
    if not funding:
        issues.append("No retained funding evidence; initial cash/basis not established")
    lifetime_realized = sum((amount(f["gross_pnl"]) for f in lifetime_fragments), amount(0))
    lifetime_cash = sum((amount(a.get("net_amount")) for a in nontrade), amount(0))
    account = snapshot.get("account_snapshot", {})
    # Account and position endpoints are separate observations. Use market values
    # from the SAME account response as equity; position prices can move meanwhile.
    if account.get("long_market_value") is not None and account.get("short_market_value") is not None:
        market_value = amount(account["long_market_value"]) - abs(amount(account["short_market_value"]))
        valuation_basis = "account_response_market_values"
    else:
        market_value = sum((amount(p.get("market_value")) for p in snapshot["positions_now"]), amount(0))
        valuation_basis = "legacy_separate_position_observations"
    unrealized = market_value - sum(
        (amount(l["signed_qty"])*amount(l["entry_price"]) for l in current_lots), amount(0))
    observed_equity = account.get("equity")
    residual = amount(observed_equity)-lifetime_realized-lifetime_cash-unrealized if observed_equity is not None else None
    if residual is None or abs(residual) > Decimal("0.01"):
        issues.append("Retained-history/current-equity bridge does not reconcile within one cent")
    realized_by_day, cash_by_day = defaultdict(Decimal), defaultdict(Decimal)
    for f in fragments:
        realized_by_day[day_of(f["exit_time"])] += amount(f["gross_pnl"])
    for a in nontrade:
        cash_by_day[str(a.get("date", ""))[:10]] += amount(a.get("net_amount"))
    valuations = equity_observations(snapshot)
    by_date = {r["timestamp"]: r for r in valuations}
    daily, previous = [], None
    for day in sorted(set(by_date) | set(realized_by_day) | set(cash_by_day)):
        obs = by_date.get(day)
        delta = amount(obs["equity"])-amount(previous["equity"]) if obs and previous else None
        if start <= day <= end:
            day_episodes = [e for e in completed if day_of(e["exit_time"]) == day]
            daily.append({"date": day, "equity": obs["equity"] if obs else None,
                          "valuation_source": obs["source"] if obs else None,
                          "valuation_timestamp": obs["valuation_timestamp"] if obs else None,
                          "prior_valuation_timestamp": previous["valuation_timestamp"] if previous else None,
                          "equity_change_since_prior_observation": str(delta) if delta is not None else None,
                          "gross_realized_pnl": str(realized_by_day[day]),
                          "nontrade_net_amount": str(cash_by_day[day]),
                          "residual_including_unrealized_and_observation_gaps": str(delta-realized_by_day[day]-cash_by_day[day]) if delta is not None else None,
                          **episode_metrics(day_episodes)})
        if obs:
            previous = obs
    chosen_fees = [a for a in nontrade if start <= str(a.get("date", ""))[:10] <= end
                   and a.get("activity_type") in {"FEE", "CFEE", "FINT"}]
    summary = {"schema_version": 2, "status": "VALIDATED_ACCOUNT_MEASUREMENT" if not issues else "REQUIRES_REVIEW",
               "strategy_scope": "mixed_version_account_history_not_current_strategy_baseline",
               "period_start": start, "period_end": end, "episode_exit_since": since,
               "generated_at": datetime.now(timezone.utc).isoformat(),
               "source_retrieved_at": snapshot["fetched_at"],
               "snapshot_sha256": hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest(),
               "issues": issues, **episode_metrics(selected),
               "realized_pnl_in_date_window": str(sum((amount(f["gross_pnl"]) for f in fragments if start <= day_of(f["exit_time"]) <= end), amount(0))),
               "fees_in_date_window": str(sum((amount(a.get("net_amount")) for a in chosen_fees), amount(0))),
               "fee_allocation": "unallocated_account_level; trade metrics are gross",
               "net_trade_expectancy": None, "open_position_episodes": len(unfinished),
               "current_account_equity": observed_equity, "valuation_basis": valuation_basis,
               "current_account_observation": snapshot.get("account_observed_at", snapshot["fetched_at"]),
               "latest_broker_valuation": next((r for r in reversed(valuations) if r["timestamp"] <= end), None),
               "lifetime_bridge": {"funding_net": str(sum((amount(a.get("net_amount")) for a in funding), amount(0))),
                   "gross_realized": str(lifetime_realized), "nontrade_net": str(lifetime_cash),
                   "fees": str(sum((amount(a.get("net_amount")) for a in nontrade if a.get("activity_type") in {"FEE", "CFEE", "FINT"}), amount(0))),
                   "unrealized": str(unrealized), "residual": str(residual) if residual is not None else None},
               "sharpe_ratio": None, "sortino_ratio": None, "total_return_pct": None,
               "return_metrics_status": "not_computed_without_verified_cashflow_adjusted_return_series",
               "avg_slippage_pct": None, "avg_execution_latency_ms": None,
               "execution_metrics_status": "not_estimated_from_holding_duration_or_stop_prices"}
    return {"summary": summary, "episodes": selected, "unfinished": unfinished, "lots": lots,
            "daily": daily, "equity": valuations, "fragments": fragments}
