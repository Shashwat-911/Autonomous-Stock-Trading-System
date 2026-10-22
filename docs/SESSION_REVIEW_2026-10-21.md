# October 21 session and publication repair

Verified from recovered Render stdout/debug and read-only broker observations:
- Worker launched 13:30:26 UTC; 33 scans from 13:30:59 through 19:58:52 UTC.
- Last output 19:59:23 UTC. Integer minute truncation incorrectly declared the
  market closed during its last minute; countdown now rounds up while open.
- At 19:50 UTC, six EOD sells were rejected: bracket cancellation was acknowledged
  but shares were still reserved. The one-shot flag prevented later retries.
- Four positions persisted: AMD 5, GS 3, MSFT 5, NVDA 13. No open orders were
  returned at inspection. User explicitly requested leaving positions untouched.
- Three completed episodes on October 21: two winners, one loser; gross realized
  P&L -$31.39. Four unfinished episodes are excluded from win-rate statistics.
- Broker minute history returned $99,743.94 at exactly 20:00 UTC, versus prior
  daily observation $99,724.53 (+$19.41). The daily 1D endpoint still omitted Oct21.
  The exact regular-close fallback retains its source and timestamp. Later 1D
  observations may use different valuation times and supersede this fallback.
- Current account snapshots include later marks on overnight positions and must
  not be substituted for the October21 close.

Repairs:
1. Repeated EOD checks confirm cancellation before submitting an exit; accepted
   exits are tracked and not duplicated. Flat inventory is verified separately.
   Unclosed inventory at session end results in failure, not successful completion.
2. Equity reconciliation uses market values from the same account response as
   equity. Previously position prices came from a later endpoint response. This
   fixes a real race; the exact private Render validation issue was not retrieved,
   so it is not asserted to be the only cause of yesterday's wrap-up failure.
3. Preserve detailed validation failures. Recover only exact broker close marks
   when 1D history is missing; never interpolate or substitute account snapshots.
4. Archive stdout through an isolated log-only Git checkout before measurement;
   GitHub can recover Render stdout without requiring the report to succeed.
   Raw debug logs and broker exports remain private.
5. Generate the visible session table from validated rows; preserve the old table
   in LEGACY_SESSION_TABLE.md. Retain the requested chart design.

Validation includes delayed cancellations, rejected exits, pending exits,
confirmed flat inventory, mismatched valuation times, exact-close fallback,
HTML log extraction and current table generation. No broker mutations were run
by this investigation. Existing strategy thresholds and sizing are unchanged.
