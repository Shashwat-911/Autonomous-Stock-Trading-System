# PROMPT-05 Fix Log — Late-Entry Cutoff Tightening
**Date:** 2026-10-17  
**Status:** Deployed to `main` — effective from Monday 2026-10-20 session

---

## Root Cause Analysis (Oct 14–16)

Three consecutive losing sessions investigated via session log analysis.

| Date | Equity | P&L | Root Cause |
|------|--------|-----|------------|
| Oct 14 | $99,940 | -$249 | Zero entries — loss is cumulative stale-trade lag, not live positions |
| Oct 15 | $99,866 | -$75 | JNJ entered 17:51 UTC (128 min to close) → bracket unresolved → EOD force-close |
| Oct 16 | $99,613 | -$253 | JPM entered 17:35 UTC, BAC entered 17:35 UTC (143 min to close) → ADX collapsed mid-session → EOD force-close |

### Key findings from log inspection
- **SPY regime: BULL all three days** — SPY $762–771 vs SMA-200 $721. The macro filter was not the cause.
- **No stop-losses triggered on any day** — neither SL nor TP bracket legs filled before close on any position.
- **ADX filter worked correctly on Oct 16** — blocked ~15 signals as ADX fell from 20 → 16 intraday. The two entries that slipped through (JPM, BAC) were made before ADX decayed.
- **Cause is purely mechanical**: bracket orders on 1-hour bars need ~2.5–3 hours to resolve. Entering at 143 minutes to close is insufficient.

---

## Fix Applied

### Files changed
| File | Change |
|------|--------|
| [`main.py`](../main.py) | `_should_allow_new_entries` default: `1.5` → `2.5`; docstring updated with live-data rationale; call site reads from config |
| [`config.py`](../config.py) | Added `TRADING["late_entry_cutoff_hours"] = 2.5` as single source of truth |
| [`README.md`](../README.md) | Session table notes updated; strategy evolution log entry added |
| [`outputs/performance_summary.json`](performance_summary.json) | `fix_deployed` metadata block added |

### Effective change
```
Entry window (ET):   09:30 → 13:30  (was 09:30 → 14:30)
Cutoff (UTC):        17:30           (was 18:30)
Cutoff (hours left): 2.5h            (was 1.5h)
```

### What this prevents
Positions entered after 13:30 ET with only 128–143 minutes to close will now be **blocked**. Existing open positions continue to be managed by their bracket orders until close.

### Trade-off acknowledged
Some late-day momentum setups will be missed. The Oct 15/16 data shows those setups were generating losses anyway (no time for brackets to resolve), so the expected value of blocking them is positive.

---

## What to watch Monday (Oct 20)

The metric to track is **not daily P&L** — it is whether any positions are EOD force-closed.

- ✅ Working correctly: brackets resolve via SL or TP; EOD liquidation fires with zero open positions
- ⚠️ Still a problem: positions still being EOD force-closed after this fix

If force-closes continue, the next diagnostic is whether entries are happening between 09:30–13:30 ET and still not resolving — which would point to ATR calibration or bracket multiplier issues rather than entry timing.

---

## Next review trigger
After 3–4 clean sessions (week of Oct 20). Bring the Alpaca equity history and session logs.
