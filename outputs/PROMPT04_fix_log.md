# PROMPT 04 Fix Log — Signal Quality & Metrics Accuracy

**Date:** 2026-09-26  
**Status:** All 4 fixes applied and verified  
**Audit Reference:** `outputs/SYSTEM_AUDIT_REPORT.md` (M-9, M-13, M-14, client_order_id)  
**Dependencies:** `outputs/PROMPT02_fix_log.md` and `outputs/PROMPT03_fix_log.md` confirmed present and verified.

---

## Pre-Flight Verification
- Confirmed `outputs/PROMPT02_fix_log.md` and `outputs/PROMPT03_fix_log.md` exist.
- Read `outputs/SYSTEM_AUDIT_REPORT.md` Section 4 (Signal Logic Decision Tree) and Section 7 (Metrics Engine Data Integrity) in full.
- Read `strategy/signals.py` and `analytics/metrics.py` in full.
- Confirmed imports of `SignalGenerator` and `PerformanceEngine` succeeded.
- Noted pre-edit line numbers in `strategy/signals.py`:
  - `generate_signal` signature: `L107-113`
  - SELL condition calculation: `L217-246`
  - SELL threshold logic: `L281` (`sell_triggered = sell_count >= 1`)

---

## Fix 1 — SELL Signal Threshold: Position-Aware (Audit: M-9)
- **Files modified:** `strategy/signals.py`, `broker/alpaca.py`, `broker/paper.py`
- **Lines changed:**
  - `strategy/signals.py:L107-115`: Updated `generate_signal()` signature to accept `portfolio_value: float = 100000.0`, `has_position: bool = False`, and `**kwargs` (supporting backward compatibility for `current_portfolio_value`).
  - `strategy/signals.py:L281-290`: Replaced single static threshold `sell_triggered = sell_count >= 1` with position-aware threshold logic:
    ```python
    if has_position:
        sell_triggered = sell_count >= 1   # Protect open position aggressively
    else:
        sell_triggered = sell_count >= 2   # Require confirmation when flat
    ```
  - `broker/alpaca.py:L708-715`: Inside `run_tick()`, updated call to `generate_signal()` to pass `has_position=(position is not None)`.
  - `broker/alpaca.py:L895-945`: Inside `run_portfolio_tick()`, updated calls to pass `has_position=(all_positions.get(ticker) is not None)` when market is closed and `has_position=(position is not None)` when scanning.
  - `broker/paper.py:L468`: Updated `generate_signal()` call to pass `has_position=(self.shares > 0)`.
- **What changed:** Eliminates false-positive SELL noise emitted on 70%+ of flat tickers where a solitary MACD-bearish condition was triggering SELL signals. Flat tickers now require at least 2 confirming bearish indicators before triggering a SELL, while actively held positions preserve aggressive 1-condition exit protection.
- **Tested:**
  - `inspect.signature` confirmed `has_position` in parameters.
  - Synthetic 60-row DataFrame test passed without exceptions.
  - Explicit test confirmed: with single MACD-bearish condition, `has_position=False` outputs `HOLD` (confidence `0.0`), whereas `has_position=True` outputs `SELL` (confidence `0.33`).

---

## Fix 2 — Sortino Ratio Formula Correction (Audit: M-13)
- **Files modified:** `analytics/metrics.py`
- **Lines changed:**
  - `analytics/metrics.py:L155-177`: Replaced `_sortino_ratio()` implementation.
- **What changed:** Previously, downside deviation was computed as `returns[returns < 0].std()`, which only sampled negative returns and omitted zero/positive return periods, distorting the standard deviation denominator. The corrected implementation uses all returns, replacing positive returns above the daily risk-free rate (`mar = self._daily_rf`) with 0.0 before calculating the root-mean-square downside deviation:
  ```python
  downside_returns = returns.copy()
  downside_returns[downside_returns > mar] = 0.0
  downside_deviation = np.sqrt(np.mean(downside_returns ** 2))
  ```
- **Tested:** Evaluated with known sample returns `[0.02, -0.01, 0.01, -0.03, 0.005]`. Confirmed result is finite (`-1.3007`), non-zero, and matches exact theoretical formula within `< 0.001` precision.

---

## Fix 3 — Slippage Measurement for Market Orders (Audit: M-14)
- **Files modified:** `broker/alpaca.py`, `analytics/metrics.py`
- **Lines changed:**
  - `broker/alpaca.py:L100`: Added `self._slippage_log: list = []` to `AlpacaPaperBroker.__init__()`.
  - `broker/alpaca.py:L205-230`: In `submit_buy()`, added `current_price: float = 0.0` and `qty: Optional[int] = None` parameters. After successful order submission, appends intended price record to `self._slippage_log`:
    ```python
    self._slippage_log.append({
        "ticker": sym,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "intended_price": current_price,
        "order_id": str(order.id),
        "side": "buy",
    })
    ```
  - `broker/alpaca.py:L245-290`: In `submit_bracket_buy()`, added `current_price` logging to `self._slippage_log` and updated signature to accept `qty` parameter alias.
  - `broker/alpaca.py:L760-780`: In `run_tick()`, passed `current_price=current_price` to `submit_bracket_buy()` and `submit_buy()`.
  - `broker/alpaca.py:L940-955`: In `run_portfolio_tick()`, passed `current_price=current_price` to `submit_buy()`.
  - `analytics/metrics.py:L247-320`: Updated `_compute_slippage()` to support:
    - Path 1: Execution latency proxy via `hold_duration_minutes < 5` for short-turnaround round trips.
    - Path 2: Bracket leg slippage on limit/stop orders with valid `price` and `filled_avg_price`.
    - Path 3: Market order slippage using `intended_price` vs `filled_avg_price`.
    - Path 4: Fallback to timestamp latency (`submitted_at` vs `filled_at`) when present.
- **What changed:** Market orders (which previously had `price == 0`) now have their signal-evaluation price captured as `intended_price` at submission, enabling genuine slippage quantification instead of skipping market orders entirely.
- **Tested:** Tested `_compute_slippage()` with round-trip and bracket data. Verified non-negative `avg_slippage_pct` (`0.0159%`) and verified latency calculations.

---

## Fix 4 — Embedded Reason in Order Logging via client_order_id
- **Files modified:** `broker/alpaca.py`
- **Lines changed:**
  - `broker/alpaca.py:L195-204`: Verified Alpaca SDK `MarketOrderRequest` supports `client_order_id`. Implemented `_make_client_order_id(self, reason: str, ticker: Optional[str] = None) -> str`.
  - `broker/alpaca.py:L215`: Added `client_order_id=self._make_client_order_id(reason, ticker=sym)` to `MarketOrderRequest` in `submit_buy()`.
  - `broker/alpaca.py:L285`: Added `client_order_id=self._make_client_order_id(reason, ticker=sym)` to `MarketOrderRequest` in `submit_bracket_buy()`.
- **What changed:** Embeds signal reasoning directly into Alpaca order history metadata within the 48-character API limit (e.g. `NVDA-Momentum-crossover---09261917`), ensuring execution reasons are traceable from Alpaca API audit logs and trade history matching.
- **Tested:** Confirmed generated `client_order_id` adheres to character constraints (`<= 48` characters, alphanumeric + hyphens) and verified `MarketOrderRequest` serialization passes without SDK error.

---

## Smoke Test Verification
- Executed 60-second end-to-end paper trading smoke test (`python main.py paper`).
- Validated:
  - Fetched historical OHLCV and computed 8 indicator series without warnings.
  - Correctly evaluated indicator signals against live pricing.
  - ADX chop filter activated appropriately (`ADX=21.3 < 24.0`).
  - Position-aware SELL logic confirmed: with flat position and single MACD bearish condition, produced `HOLD` signal with `0.0` confidence (zero spurious SELL signals).
  - Process ran continuously with 0 unhandled exceptions and terminated cleanly on SIGINT.

---

## Post-Fix System Status

### Issues resolved across all 3 prompts:
- C-1: API key security ✓
- C-2: PnL calculation fixed ✓  
- C-3: Zombie position EOD cleanup ✓
- H-4: Order deduplication ✓
- H-5: Circuit breaker persistence ✓
- H-6: Day-start balance from broker ✓
- H-7: Order pagination fixed ✓
- H-8: Session deduplication ✓
- M-9: SELL threshold position-aware ✓
- M-10: Portfolio heat bypass prevented ✓
- M-11: submit_buy error handling ✓
- M-12: NaN guard on price ✓
- M-13: Sortino formula corrected ✓
- M-14: Slippage measurement extended ✓
- L-16: reset_daily_state called ✓
- L-18: .total_seconds() fix ✓

### Issues deferred (not in scope of these 3 prompts):
- L-15: ML model timeframe mismatch (requires retraining)
- L-17: GPU acceleration not wired in (performance only)

### Known remaining strategic limitations:
1. Strategy is still a mean-reversion / momentum hybrid —
   requires a dedicated walk-forward re-evaluation to confirm
   the signal quality improvements materially help win rate.
2. Long-only strategy correlated with SPY bull/bear cycles.
3. 20-ticker universe scanning for signals that only appear
   on 1-2 tickers (META) — universe curation needed.
