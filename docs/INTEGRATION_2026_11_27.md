# Main and research integration — 2026-11-27

Main remains the sole Render execution branch. Research lives in the sibling checkout
on research-and-ml-preserved. No wholesale branch merge or strategy promotion.

## Main changes
- Unknown daily/regime observations block entries. Calendar-aware completed hourly
  bars exclude forming bars and reject stale, invalid or missing data.
- Broker inventory/account failures do not masquerade as flat/known state; only
  acknowledged buys consume pending exposure. Order client IDs include revision.
- Fill-based measurement v2 is restored in both reporting paths. Public charts
  retain the original style; old evidence is not overwritten with current equity.
- Private decision tapes capture actual broker/risk dependency responses and inputs.
  Public stdout contains sanitized decisions and missing-data states. Replay runs
  actual signal/broker decision code with taped dependencies and no order client.
- Private uploads verify privacy, retry with safe errors and compare content on
  conflicts. Ephemeral local evidence can still be lost before remote acknowledgement.
- EOD exit requests are not called closed until inventory confirms flat. Pending
  market exits are not duplicated on restart. Existing EOD policy is retained.
- Independent GitHub wake watchdog checks recent broker-clock and runner state.

## Isolated automation
The default-branch research_isolated.yml is the scheduler. It checks out research
and main separately, verifies private evidence destination, collects read-only
account evidence, replays recorded decisions, and advances one daily ETF shadow.
Only research-and-ml-preserved receives research summaries and state. Raw evidence
and frozen research inputs are committed only to the private evidence repository.
Weekly costed comparisons use fixed 2023–2025 validation inputs; 100 fixed random
seeds and 1x/2x/4x costs are retained. Random controls are daily, year-stratified
entry opportunities, not an exact hourly live baseline or significance verdict.
Failures remain failed GitHub jobs; notification delivery depends on account settings.

## Evidence boundaries
Recorded decision parity is not counterfactual fill parity. Historical observations
that were never captured remain unknown. Replay refuses changed code and flags
unsupported/error paths rather than inventing evidence. No claim of a validated
hourly historical baseline, zero losing trades, or exhaustive proof of correctness.

The original November 2 experiment remains intact. New ETF shadow registration
starts November 30, 2026, ends May 31, 2027, and cannot be reviewed for promotion
before June 1, 2027. Missing sessions or code/protocol drift block advancement.
No automatic deployment or broker orders from the shadow portfolio.

## Verification
Run `python -m unittest discover -s tests -v` separately in both checkouts.
Main CI runs Python 3.11 and 3.12. Cloud evidence/research failures are independent
of trading. Deployment verification must check the live /status revision and
/ready plus CI results; a closed-market check does not prove an open-market trade.

## Verification checkpoint

Local suites: main 64 passed; research 80 run, 79 passed and one optional
private-snapshot fixture skipped. GitHub Python 3.11/3.12 suites passed on the published checkpoints.
Daily run 45964751042 and weekly run 46030191384 succeeded. The latter retained
15 comparisons and 100 random controls at each of three cost levels. These are
completed research jobs, not proof of edge; hourly historical parity remains blocked.

Render successfully ran main during the November 27 open session with fresh
market data and sanitized decision_v2 events. Deployment verification discovered
that Render lacks GIT_TOKEN, although the GitHub Actions secret is configured and
works. Raw runtime replay bundles therefore remained ephemeral. Partial stdout was
archived before redeployment; it does not reconstruct the missing raw inputs.
The watchdog now fails explicitly for missing or delayed private delivery. Restoring
Render's private-repository write credential and confirming an actual remote bundle
are required before runtime evidence delivery can be called verified.

Final source deployment b1228d8 was verified Live in Render and running during market
hours. GitHub regression runs for b1228d8 and b825c71 succeeded. Check-only watchdog
run 46031426632 failed specifically with `Render private evidence credential is
missing`, confirming the failure is now visible rather than silently accepted.
