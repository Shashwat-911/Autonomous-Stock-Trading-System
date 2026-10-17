# Read-only paper-account reconciliation

## Why this exists

The production report can match a buy in one symbol to a sell in another. The
saved order export contains only 50 orders. Existing win rate and expectancy
are unverified. This independent diagnostic gathers evidence before production
measurement or strategy changes. It does not repair the production report,
alter thresholds, enable ML, enforce trailing stops, or place/cancel orders.

## Run and replay

From the repository root with existing requirements installed:

```powershell
python scripts/reconcile_paper_account.py --start 2026-08-11 --end 2026-10-16
python -m unittest discover -s tests -v
```

Credentials: `ALPACA_API_KEY` / `ALPACA_SECRET_KEY`, or
`APCA_API_KEY_ID` / `APCA_API_SECRET_KEY`, from the environment or root `.env`.
The reader uses only allowlisted GETs on `https://paper-api.alpaca.markets`.
Base-URL overrides and redirects cannot send credentials to a live endpoint.

Each run creates a unique folder under gitignored `outputs/private_reconciliation/`.
Do not publish raw account exports. A custom `--output` location needs its own
Git exclusion. Replay saved evidence without credentials or network:

```powershell
python scripts/reconcile_paper_account.py --snapshot outputs/private_reconciliation/RUN_ID/snapshot.json --start 2026-08-11 --end 2026-10-16
```

Replay dates must fit the snapshot's original requested window. Collection reads
all retained account activities and orders, including pre-window inventory and
later-created fees. Collection is sequential, not atomic; preferably run while
trading is stopped. Current positions are retrieval-time observations.

## Outputs

| File | Evidence |
|---|---|
| `snapshot.json` | Private broker data for replay |
| `fills_with_log_evidence.csv` | Fills, client order IDs and direct/parent/no local log match |
| `matched_lots.csv` | Symbol-aware FIFO quantities and gross realized P&L |
| `opening_lots.csv`, `ending_lots.csv` | Reconstructed boundary inventory |
| `nontrade_activities.csv` | Cash movements, fees, dividends and adjustments |
| `unsupported_activities.csv` | Events requiring manual basis/classification review |
| `order_activity_quantity_gaps.csv` | Cumulative order quantities versus fill activities |
| `current_position_quantity_gaps.csv` | Retained-fill inventory versus current positions |
| `daily_reconciliation.csv` | Broker/local equity, run changes and residuals |
| `summary.json`, `report.md` | Aggregate results and limitations |
| `failure.json` | Failed run; never a successful empty audit |

## Accounting rules and limits

Use individual execution activities, not cumulative order quantities. Partially
filled orders later canceled still contribute their actual fills. Nested bracket
legs are metadata, not additional executions. Decimal FIFO queues are separate
per symbol and retain partial quantities; short covers are supported. Duplicate
activity IDs fail rather than double-counting.

Missing opening history can look like a short opening. Quantity comparisons help
detect missing records but cannot prove lifetime completeness. Corporate actions,
stock journals and unknown activities are flagged; no basis adjustment is invented.
Matched fragments are not independent trades or a valid win-rate denominator.

Dates use America/New_York with DST. Non-trade activity economic dates differ from
API creation dates. Fees dated after the window are retained in the snapshot but
not silently backdated. Historical revisions require a fresh API snapshot.

```text
equity change = gross realized P&L + change in unrealized P&L
              + net non-trade cash movements + remaining adjustments
```

Historical marks for residual lots are not independently retrieved. The remainder
is therefore explicitly `residual_including_unrealized`, not unexplained cash.
If both inventory boundaries are flat, unrealized P&L should be zero, conditional
on complete inventory history and aligned observations. The baseline uses a broker
observation before the start; no assumed $100,000 value is substituted when missing.
Inspect the baseline date: changes span consecutive available observations.

The report remains `REQUIRES_REVIEW`. A zero residual does not establish strategy edge.

## Local log attribution

Only canonical `outputs/logs/session_YYYY_MM_DD.txt` files are searched. Direct
order-ID evidence is stronger than a bracket-parent match. An absent ID does not
prove an external process placed the order. Naive log times are not assigned an
invented timezone. Multiple starts in one file are flagged.

October 14-16 local ledger changes total -$576.56; recorded run changes total
-$20.35. The -$556.21 difference is an attribution gap, not automatically a
late-entry loss. Compare broker history, execution events and cash activities.

The repository contains GitHub Actions and Render launch paths, plus pre-session
position cleanup. Their presence is an investigation lead, not proof of execution.
Deployment/job logs may still be needed to identify the process behind an order.

## Retrieval guarantees

Activities paginate using activity-ID tokens. Orders recursively split saturated
500-order timestamp windows with overlap, preserving ties. Unsplittable saturated
timestamps fail instead of silently truncating. Orders referenced by fills but
absent from list results are fetched individually. Network retries are bounded;
authentication failures, malformed responses and repeated activity pages fail.

Official references:
- https://docs.alpaca.markets/us/reference/getaccountactivities-2
- https://docs.alpaca.markets/us/docs/working-with-orders
- https://docs.alpaca.markets/us/docs/orders-at-alpaca
