# Research system: usage and evidence boundaries

This package is offline/read-only. It cannot promote models, change strategy
configuration, or submit orders. There is no zero-loss or profitability guarantee.

## Implemented mechanics

- Bar-close signals execute at the next available bar open.
- Long-only cash accounting, partial target reductions, completed position episodes.
- Explicit spread, slippage and per-share fee assumptions on both sides.
- Stops fill at the opening price if gapped through; ambiguous OHLC stop/target
  touches use stop-first. No guarantee of actual execution at these simulated prices.
- Scheduled end-of-session exits require caller-supplied calendar session flags.
- Open positions stay marked to market at the end; no invented terminal liquidation.
- Fill records identify bar-close label and execution phase. Intrabar timestamps
  cannot be reconstructed from OHLC and are not claimed.
- Input prices must be finite, positive, ordered, unique and internally consistent.

## Commands (from repository root)

```
python -m unittest discover -s tests -v
python -m research.download --output outputs/private_reconciliation/NEW_DATA_DIRECTORY
python -m research.compare --data outputs/private_reconciliation/NEW_DATA_DIRECTORY --start 2023-01-01 --end 2025-12-31 --output research/validation_results.json
python -m research.attribution --snapshot PRIVATE_SNAPSHOT --private-output PRIVATE_EPISODES --summary research/attribution_summary.json
```

Download validates every requested session against the broker calendar, keeps
adjusted historical data private, and records its source/limitations. No forward or
back filling is permitted. Comparison requires all five calendars to align.
The comparison API accepts daily input only by contract; do not feed intraday files
into the daily protocol. The first lookback period is held in cash for warmup.

## Preregistered experiment

See protocol.json. Development: 2015–2022. Diagnostic validation: 2023–2025.
The already-observed 2026 account history is not an untouched holdout.
Reserve November 2, 2026 through April 30, 2027 prospectively. This duration is
an initial research policy, not a statistically sufficient sample guarantee.
Research commands reject that period. Promotion remains unconditionally blocked
until a separate evidence review; editing a date cannot automatically activate a model.
Drawdown/exposure limits are provisional research limits, not changes to live risk.

Compare cash, equal capital sleeves of passive ETFs, and the 20/10 daily candidate.
15/8 and 25/12 variants are sensitivity checks, not an invitation to select the winner.
Use 1x, 2x, 4x costs; report source hashes, protocol hash, exposure, net P&L,
drawdown, yearly contributions and open inventory. Cash has zero interest in this
experiment. Prices are retrospectively adjusted: results are provisional research,
not a point-in-time execution reconstruction. No historical quotes are available.

## Hourly baseline and outstanding evidence

hourly_signal_adapter reuses the signal generator, but is explicitly NOT certified
live parity. Broker scan timing, partial current candles, risk cooldowns, historical
regime observations and actual order lifecycle require recorded replay inputs.
The comparison reports BLOCKED_MISSING_LIVE_PARITY_REPLAY rather than fabricating
an equivalent hourly baseline. No current strategy settings were changed.

The fresh October 19–30 account audit recovered 70 episodes, four overnight,
with gross P&L -452.54. Fourteen have broker-stop evidence; 56 have unknown exit
mechanisms. All entry versions remain unknown because order-linked version and
decision traces were not retained. Raw execution evidence remains gitignored.
No historical causal claim should be inferred from a loss or a time-of-day alone.

## Acceptance status

No candidate approved for deployment. Passing offline tests verifies covered
software behavior, not profitability or absence of all errors. The full strategy
promotion objective remains blocked by prospective observations, hourly replay
parity, missing historical decision evidence and independent review.
