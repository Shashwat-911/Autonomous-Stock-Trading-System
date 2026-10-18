# Execution-based measurement v2

Implemented October 17-18, 2026. No strategy, sizing, ticker, entry cutoff,
cleanup, trading schedule, order submission or order cancellation changes.
This is an independent repair of accounting and report consumers. Changes are
committed locally for review; this implementation run does not push or deploy.

## Authoritative data and accounting

Individual Alpaca `FILL` activities supply execution prices, quantities and times.
Orders supply metadata and a cumulative-quantity completeness check. A canceled
partially filled order still has executions; a bracket child is not an extra fill.
The prior 50-order CSV is preserved and is not an input to measurement v2.

All retained history is reconstructed before filtering by date or episode exit
time. This preserves the basis of positions opened before the report window.
FIFO accounting is symbol-specific, uses decimal arithmetic and retains residual
quantities. Reversals close the old position and start the new direction at zero.
Duplicate activities, invalid fills and timezone-naive execution times fail.

Unsupported inventory events, missing funding evidence, missing order metadata,
order/fill quantity disagreements, current-position disagreements and a nonzero
retained-history equity residual block promotion to the public aggregate output.
The one-cent bridge tolerance is explicit. These checks are evidence of internal
consistency, not proof that the broker retained every historical event or that
an unrecognized initial basis can never coincidentally reconcile.

## What counts as a trade

A completed trade is one per-symbol **flat-to-flat position episode**. Multiple
partial entries/exits, reductions and additions while the position remains open
belong to one episode. Unfinished episodes do not enter completed-trade metrics.
FIFO fragments remain available separately for realized P&L by execution date.

Examples:

- Buy 10 AAPL, sell 10 MSFT: zero completed episodes; separate long and short
  inventory. A cumulative-orders DataFrame passed to the broker adapter is rejected
  with an explicit instruction to supply execution activities instead.
- Buy 2 shares at $10 and 3 at $20; sell 3 at $30 and 2 at $40: one completed
  episode, 5 shares, $90 gross P&L. The first partial sale alone does not finish it.
- Buy 2 at $10; sell 3 at $20; buy 1 at $15: a $20 long episode and a $5 short
  episode. The reversing execution is split at zero.
- Gross episode outcomes +$10, -$4, $0: expectancy $2, win rate 1/3, profit
  factor 2.5. Breakeven is in the denominator but is not a loss.

## Metric definitions

| Field | Definition |
|---|---|
| `total_trades` | Completed flat-to-flat episodes whose exit meets report selection |
| `winning_trades`, `losing_trades`, `breakeven_trades` | Counts by gross episode P&L sign |
| `win_rate` | Positive episodes / all completed episodes, including breakevens |
| `expectancy` | Arithmetic mean gross episode P&L, including breakevens |
| `profit_factor` | Sum of positive gross outcomes / absolute sum of negative outcomes |
| `profit_factor_status` | No-loss/no-outcome cases are explicit; ratio is null, not zero or a non-JSON infinity |
| `avg_gain`, `avg_loss` | Means within positive/negative outcome groups; empty groups are null |
| `completed_episode_gross_pnl` | Sum of selected completed episode outcomes |
| `realized_pnl_in_date_window` | FIFO realized P&L on exits in New York date window, including partial exits in unfinished episodes |
| `fees_in_date_window` | Signed fee cash activities on their economic date, not guessed execution allocation |
| `net_trade_expectancy` | Null: fees are unallocated at account level |
| `equity` | Broker 1D portfolio-history observation, not current equity substituted into history |
| `valuation_timestamp` | Exact UTC timestamp returned by broker history |
| `source_retrieved_at`, `generated_at` | API retrieval and later report construction timestamps, respectively |
| `equity_change_since_prior_observation` | Difference between consecutive available broker observations; null without a prior observation |
| `nontrade_net_amount` | Signed cash activities, including funding, fees and dividends |
| `residual_including_unrealized_and_observation_gaps` | Equity change minus same-date realized P&L and nontrade cash; may span missing observations |
| `lifetime_bridge` | Retained funding/cash + realized + current marked unrealized versus observed account equity |
| `current_account_equity` | Separately timestamped retrieval-time balance, never a historical closing value |

No completed episodes means null expectancy and win rate. The report does not
infer annualized Sharpe/Sortino or total return from irregular observations,
unadjusted cash movements, or a sequence of trade exits. Those fields remain null
until a verified cashflow-adjusted return series is implemented. Execution
slippage/latency are also null: holding duration is not order latency and a stop
level is not a signal-time quote. Gross trade P&L excludes fees; account equity
includes them. No per-trade fee allocation is invented.

## Time and selection policies

New York dates use DST-aware conversion. Session wrap-up selects episodes by
exit at or after the actual UTC run-start timestamp. A crossing episode's full
gross outcome is included, with `entry_before_reporting_boundary=true`; this is
not the same as P&L earned only during that run. The summary separately reports
date-window realized P&L and account-level fees.

Same-day historical bars are excluded unless a captured exchange calendar proves
the regular session has closed before retrieval. This supports early closes.
Older broker observations retain their raw timestamps and can be revised by later
fees; each generation records source retrieval time and snapshot SHA-256.
Missing history is never backfilled with a live account balance or assumed capital.

Snapshot retrieval is sequential rather than atomic. Active trading during capture
can create consistency failures; retry after the account is stable rather than
suppressing checks. Corporate actions/unknown activities require manual basis
handling. Current positions are not historical positions.

## Run and inspect

Existing production entry points remain available:

```powershell
python scripts/generate_session_report.py
python scripts/generate_pnl_chart.py
python scripts/update_readme.py
python scripts/session_analysis.py
python -m unittest discover -s tests -v
```

Historical offline validation, no network or credentials:

```powershell
python scripts/generate_session_report.py --snapshot outputs/private_reconciliation/20261017T155359282133Z/snapshot.json --start 2026-08-10 --end 2026-10-16 --stage-only
```

Remove `--stage-only` to promote validated aggregate reports **locally**. This is
not a Git push or deployment. `--start`/`--end` are inclusive New York dates.
The private snapshot is intentionally absent from a fresh clone; its regression
test skips there while synthetic tests remain available.

## Files and consumer migration

- `outputs/reporting_private/<run>/`: raw snapshot, completed episode trade log,
  unfinished positions, FIFO fragments and open lots; gitignored.
- `outputs/measurement_v2/generations/<run>/`: aggregate summary, daily account
  measurement, timestamped broker equity, per-symbol gross metrics, and chart.
- `latest.json`: atomically selects a complete cumulative generation.
- `latest_run.json`: separate run-selected summary pointer; cannot replace the
  cumulative report. Run and cumulative status files are independent.
- `report_status.json`: unsuccessful API/validation attempts invalidate consumer
  access instead of silently displaying stale success. Old generations remain.

Aggregate files are staged privately before promotion. A generation is complete
before its pointer is updated; readers also check that status and pointer agree.
Raw identifiers and snapshots are not in the public generation. Chart generation
adds its presentation artifact to that generation after accounting validation.

Updated consumers:

| Consumer | New behavior |
|---|---|
| `broker/alpaca.py::_build_round_trips` | Actual fill episodes; refuses cumulative order approximations |
| `broker/alpaca.py::get_trade_history` | Complete retained account history and checks, then per-symbol selection |
| `main.py` live wrap-up | One account-wide capture, explicit run-start exit selection; no 20 repeated per-ticker fetches |
| `generate_session_report.py` | Shared staged/validated cumulative report and offline replay CLI |
| `analytics/metrics.py` | Execution episode input cannot fabricate equity or latency; legacy mean expectancy handles breakevens |
| `fetch_alpaca_equity.py` | Private timestamped broker-history capture; never edits the legacy ledger |
| `generate_pnl_chart.py` | Broker equity, gross realized P&L and equity change shown separately |
| `update_readme.py` | Separate corrected block; preserves and labels legacy narrative as unverified |
| `session_analysis.py` | Reads latest validated v2 summary instead of averaging stale session rows |
| `post_session.py`, workflow artifact stage | Track v2 aggregates and metadata, not obsolete CSV/JSON or raw order exports |

Workflow scheduling, cleanup commands, deployment settings and trading commands
are unchanged. Post-session scripts and the workflow were not executed during
implementation because they can commit/push or run the trader. Only their reporting
references changed. The separate old `outputs/project_status.py` contains historical
hardcoded strategy claims and is not an authoritative measurement consumer.

The original `alpaca_equity_history.csv`, `trade_history.csv`,
`session_all_orders.csv`, `performance_summary.json` and old chart remain unchanged.
They are retained evidence, not the source for new reports.

## Verified snapshot results

For retained history August 10-October 16, 2026:

| Result | Value |
|---|---:|
| Completed episodes | 335 |
| Winning / losing / breakeven | 137 / 198 / 0 |
| Gross win rate | 40.8955% |
| Gross expectancy | -$1.10191 per episode |
| Gross profit factor | 0.926649 |
| Gross realized P&L | -$369.14 |
| Fees | -$18.59 |
| Retained funding | $100,000.00 |
| Broker equity | $99,612.27 |
| Ending inventory / reconciliation residual | Flat / $0.00 |

October 16 whole-date realized P&L is -$252.44; episodes exiting after the saved
17:35:51 UTC run start total -$3.85. The report preserves this distinction rather
than attributing all account losses to the late run.

These are **mixed-version account results**, not proof of the current strategy's
expectancy. Execution-owner attribution and version tagging remain outstanding.
Ten subsequent sessions can check operational measurement but cannot by themselves
establish a durable strategy edge. No replacement strategy is implemented here.

## Implementation verification

`python -m unittest discover -s tests -v`: 27 tests passed, including the
private snapshot replay. Synthetic cases cover symbol isolation, partial exits,
short reversals, duplicate fills, missing basis evidence, timestamps, staging,
failed-report invalidation and production adapter behavior.

A final comparison with commit `f4c5247` confirmed that only the broker's
`_build_round_trips` and `get_trade_history` methods changed, and that workflow
schedules, trading/cleanup commands, strategy/risk configuration and original
historical artifacts remained unchanged. The live main-loop diff is confined to
its final performance-reporting block. Public output contains aggregates; raw
execution evidence remains gitignored.
