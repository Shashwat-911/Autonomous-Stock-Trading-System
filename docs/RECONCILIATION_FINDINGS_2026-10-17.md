# Paper-account audit findings: October 17, 2026

## Scope and reproducibility

Read-only paper API collection began at 2026-10-17 15:54 UTC. The requested
report window is August 11 through October 16 in America/New_York. Retained
account history was also fetched to establish opening inventory and funding.
No trading or production reporting code was invoked or changed.

The private snapshot is at
`outputs/private_reconciliation/20261017T155359282133Z/snapshot.json` on the audit
machine. It is intentionally not published. Replay instructions are in
[RECONCILIATION.md](RECONCILIATION.md). Final replay used the audit implementation
through commit `9d25967`. Automated checks: 12 passing unit/regression tests.

## Coverage and checks

| Observation | Result |
|---|---:|
| Retained account activities | 1,498 |
| Orders including bracket children | 1,032 |
| Fill events within requested window | 1,180 |
| Orders submitted in window or linked to its fills | 912 |
| Order versus activity filled-quantity mismatches | 0 |
| Current position versus retained-fill inventory mismatches | 0 |
| Unsupported inventory/corporate-action activities detected | 0 |
| Current and October 16 ending inventory | Flat |

The snapshot contains 973 matched FIFO fragments in the requested window. These
are not 973 independent trades. Partial fills split matches; do not infer a win
rate or statistical sample size from this count.

The audit found 870 window orders without a direct ID match in canonical local
session logs. Missing IDs do not by themselves establish another process: logs
can omit bracket children or orders entirely. The private order/fill CSVs retain
identifiers and client IDs for follow-up investigation.

## Account equity reconciles exactly across retained history

Broker evidence includes funding and trading on August 10, before the requested
August 11 start. The earlier narrative describing August 11 as the first trade
date is therefore not a reliable account-history boundary.

| Component | USD |
|---|---:|
| Retained funding journal | +100,000.00 |
| Lifetime FIFO gross realized trading P&L | -369.14 |
| Retained fees | -18.59 |
| Ending unrealized P&L (flat inventory) | 0.00 |
| Reconstructed equity | **99,612.27** |
| Broker current equity | **99,612.27** |
| Residual | **0.00** |

This reconciles the account, not strategy quality or process ownership.
The saved October 16 ledger equity is $99,612.93, $0.66 above the fresh broker
value; October 16 fee activities total $0.66. This is consistent with the saved
snapshot preceding fee posting.

Within August 11-October 16 alone, gross realized P&L is -$351.02 and non-trade
cash is -$17.92. The August 10 broker equity baseline is $99,923.23, so the
shorter-window residual is +$57.98. Opening inventory is non-flat (187 FIFO
lots). The retained cash/fill history and baseline equity imply opening unrealized
P&L of -$57.98; its disappearance at the flat endpoint explains that residual.
This opening unrealized value is inferred from the accounting identity, not an
independent historical price-mark query.

## October 14-16: the missing trading was before the recorded runs

Fill timestamps and matching client-order identifiers confirm executions before
the late runs in the saved logs. Realized P&L grouped by exit relative to the
recorded UTC startup times is:

| Date | Recorded startup UTC | Gross realized before startup | Gross realized during recorded run | Total gross realized |
|---|---|---:|---:|---:|
| Oct 14 | 18:07:12 | -319.54 | 0.00 | -319.54 |
| Oct 15 | 17:50:52 | -57.70 | -16.50 | -74.20 |
| Oct 16 | 17:35:51 | -248.59 | -3.85 | -252.44 |
| Total | | **-625.83** | **-20.35** | **-646.18** |

Examples from broker records:

- October 14: morning buys in NVDA, GOOGL, CRM and UNH; subsequent exits;
  UNH and CRM market sells at approximately 18:07:02, ten seconds before the
  saved run starts.
- October 15: morning JPM, NFLX and JNJ entries; an earlier JNJ stop-out and
  re-entry; three market liquidations around 17:50:44, eight seconds before
  startup; the recorded run then buys JNJ again.
- October 16: morning and afternoon entries, TSLA and GS stop exits, then seven
  market liquidations around 17:35:42, nine seconds before startup. The recorded
  run subsequently opens JPM and BAC again.

These clustered exits immediately preceding startup are consistent with the
workflow's `force_close_all.py` pre-session cleanup. Earlier client IDs use the
bot's momentum naming pattern. **The API does not identify the host or process.**
Render versus another workflow/manual run remains unproven without deployment
logs. The evidence demonstrates unlogged earlier trading, not necessarily
concurrent processes.

## Exact bridge for the $556.21 attribution gap

The three-day broker equity change is -$550.94, from $100,163.21 on October 13
to $99,612.27 on October 16. October 13 had open lots; retained cash/fills imply
-$96.83 unrealized P&L at that close, versus zero at the final close.

```text
Earlier gross realized P&L                         -625.83
Recorded-run gross realized P&L                     -20.35
Change in inferred unrealized P&L                    +96.83
October 14-16 fees                                    -1.59
----------------------------------------------------------
Broker equity change                               -550.94
Change in saved-ledger minus broker-equity offset    -25.62
----------------------------------------------------------
Saved local ledger change                          -576.56
Less recorded-run change (subtract -20.35)           +20.35
----------------------------------------------------------
Outside-run / snapshot attribution difference       -556.21
```

The offset changed from +$26.28 on October 13 to +$0.66 on October 16. The exact
capture-time cause of the October 13 offset is not independently established.
Consequently the gap is numerically reconciled into earlier trades, changes in
unrealized P&L, fees, and differing snapshots; it is not all late-entry loss.

## Historical ledger limitations

Fresh broker history differs from saved ledger values on numerous dates. For
example, the saved August 11 value $99,923.23 is the fresh broker August 10 value;
the saved August 12 value $99,551.43 is the fresh broker August 11 value. This is
evidence of historical date/snapshot inconsistencies, not grounds to blindly
shift every row. October discrepancies include fees and non-flat intraday marks.
The audit leaves the original ledger untouched and exports side-by-side values.

## What remains before strategy evaluation

1. Obtain GitHub Actions and Render execution logs for the earlier trading windows
   to establish process ownership and cleanup provenance. Do not stop or change
   deployments merely on inference from client IDs.
2. Agree on a single execution owner and intentional cleanup/overnight policy.
3. Repair the production multi-symbol reporting path and historical ledger with
   reviewed evidence. The production bug is still present; this is an independent
   diagnostic, not a silent production replacement.
4. Evaluate strategy versions on clean matched outcomes and comparable execution
   assumptions. Neither this reconciliation nor the old metrics establish an edge.

Raw credentials, account identifiers, order IDs and fill-level exports are not
included in this public findings document.
