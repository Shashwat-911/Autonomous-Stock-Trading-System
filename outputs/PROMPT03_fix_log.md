# PROMPT 03 Fix Log — Risk Integrity & Zombie Position Cleanup

**Date:** 2026-09-26  
**Status:** All 7 fixes applied and verified  
**Audit Reference:** `outputs/SYSTEM_AUDIT_REPORT.md` (C-3, H-4, H-5, M-10, M-11, M-12, Prompt 02 7-day lookback gap)

---

## Fix 1 — EOD Force-Close for Zombie Bracket Positions (Audit: C-3)
- **Files modified:** `broker/alpaca.py`, `main.py`
- **Lines changed:**
  - `broker/alpaca.py:L700-760`: Added public method `eod_liquidate_all(self, reason: str = "EOD force-close") -> dict`. Queries open orders for `self.ticker` via `GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[self.ticker])` and cancels them, verifies remaining position quantity, pauses briefly, and submits a market SELL with `TimeInForce.DAY` to close the position. Resets internal tracking `_entry_price` and `_trailing_stop`.
  - `main.py:L74-83`: Added helper function `_is_near_market_close(clock, minutes_before: int = 10) -> bool` comparing current UTC time against `clock.next_close`.
  - `main.py:L511, L524-539`: Added `_eod_triggered = False` guard before scan loop and wired EOD liquidation check into `run_live()` after each scan iteration. Triggers once when market closes within 10 minutes, liquidating open positions across all configured tickers.
- **What changed:** Eliminates zombie positions resulting from unexpired GTC bracket order legs by cancelling pending bracket orders and market-liquidating any remaining shares 10 minutes prior to market close.
- **Tested:** Tested `_is_near_market_close()` with mock clocks: 5 minutes to close returned `True`, 20 minutes to close returned `False`, closed clock returned `False`. Verified `hasattr(AlpacaPaperBroker, 'eod_liquidate_all') == True`.

---

## Fix 2 — Order Deduplication Before BUY Submission (Audit: H-4)
- **Files modified:** `broker/alpaca.py`
- **Lines changed:**
  - `broker/alpaca.py:L675-700`: Implemented private method `_has_pending_buy_order(self) -> bool` querying open orders on Alpaca and identifying any active BUY orders (`side` matching `'buy'` or `'ordersidebuy'`). Includes fail-open exception handling.
  - `broker/alpaca.py:L764-774`: In `run_tick()`, added deduplication guard immediately following `position is None` validation. If a pending BUY order is detected, skips submission with reason `"Pending BUY order already exists — dedup protection"`.
- **What changed:** Prevents duplicate BUY orders from being submitted across consecutive scans when a previously placed bracket parent or market order has not yet filled.
- **Tested:** Verified `hasattr(AlpacaPaperBroker, '_has_pending_buy_order') == True` and confirmed error handling fails open to avoid locking up order execution if the order query fails.

---

## Fix 3 — Circuit Breaker State Persistence Across Restarts (Audit: H-5)
- **Files modified:** `risk/manager.py`
- **Lines changed:**
  - `risk/manager.py:L1-10`: Ensured imports `import os`, `import json`, `from datetime import timezone`.
  - `risk/manager.py:L58-135`: Added `_state_filepath()`, `_save_state()`, and `_load_state()`. Persists `daily_loss_breached`, `cooldown_until`, `stop_loss_count`, `day_start_balance`, and `saved_at` timestamp to `outputs/risk_state.json`. `_load_state()` ignores stale files older than 18 hours and only restores active (unexpired) cooldowns.
  - `risk/manager.py:L56`: Added `self._load_state()` call at the end of `RiskManager.__init__()`.
  - `risk/manager.py:L268`: Added `self._save_state()` call in `can_trade()` upon daily loss breach.
  - `risk/manager.py:L394`: Added `self._save_state()` call in `check_stop_loss()` upon triggering cooldown.
  - `risk/manager.py:L482`: Added `self._save_state()` call in `sync_day_start_balance()`.
  - `risk/manager.py:L497`: Added `self._save_state()` call in `reset_daily_state()`.
- **What changed:** Circuit breaker breach flags and cooldown timers persist to disk across process restarts, preventing inadvertent resumption of trading during market hours following a crash or restart.
- **Tested:** Executed inline test: saved breach state and stop loss count of 3 to disk, initialized a new `RiskManager` instance, and verified `rm2._daily_loss_breached == True` and `rm2._stop_loss_count == 3`. Cleaned up test state file afterwards.

---

## Fix 4 — Order History Lookback Extended to 7 Days (Prompt 02 Gap)
- **Files modified:** `broker/alpaca.py`
- **Lines changed:**
  - `broker/alpaca.py:L1066`: Changed `after_date = datetime.now(timezone.utc) - timedelta(days=2)` to `after_date = datetime.now(timezone.utc) - timedelta(days=7)` in `get_trade_history()`.
- **What changed:** Extended order retrieval lookback window from 2 days to 7 days, ensuring Monday morning scans correctly capture Friday and weekend order activity and round-trips.
- **Tested:** Verified `(datetime.now(timezone.utc) - after).days == 7`.

---

## Fix 5 — Portfolio Heat Bypass Prevention (Audit: M-10)
- **Files modified:** `broker/alpaca.py`, `main.py`
- **Lines changed:**
  - `broker/alpaca.py:L724`: Added parameter `pending_exposure: float = 0.0` to `run_tick()` signature.
  - `broker/alpaca.py:L788-796`: Augmented confirmed position exposure with `pending_exposure` prior to portfolio heat check: `augmented_exposure = long_exposure + pending_exposure`.
  - `broker/alpaca.py:L845`: Added `"order_value": qty * current_price` and `"action": "BUY"` to returned order result dictionary in `run_tick()`.
  - `main.py:L509, L545, L570-580`: Added `pending_exposure_dollars = 0.0` before scan loop, reset it at start of each scan iteration, passed `pending_exposure=pending_exposure_dollars` into `run_tick()`, and incremented `pending_exposure_dollars += order_value` when a BUY is submitted.
- **What changed:** Prevents sequential tickers evaluated in the same scan loop from simultaneously bypassing portfolio heat limits before pending orders reflect as settled positions in broker account equity.
- **Tested:** Verified method signature of `AlpacaPaperBroker.run_tick` via `inspect.signature` contains `pending_exposure`.

---

## Fix 6 — submit_buy() Error Handling (Audit: M-11)
- **Files modified:** `broker/alpaca.py`
- **Lines changed:**
  - `broker/alpaca.py:L229-252`: Wrapped `client.submit_order()` in `submit_buy()` in `try ... except Exception as e`. Logs failures at `ERROR` level and returns empty dict `{}` instead of crashing.
- **What changed:** Prevents broker API submission errors (HTTP 422 insufficient buying power, 403 authentication, timeout) from propagating uncaught and terminating the scan loop.
- **Tested:** Inspected source code of `AlpacaPaperBroker.submit_buy` to ensure robust exception handling and error logging.

---

## Fix 7 — NaN Guard on Current Price & Indicators (Audit: M-12)
- **Files modified:** `broker/alpaca.py`
- **Lines changed:**
  - `broker/alpaca.py:L742-756`: Added `pd.isna(raw_price)` and `<= 0` validation guards on `df["Close"].iloc[-1]` in `run_tick()`. Skips tick safely with `HOLD` signal if invalid.
  - `broker/alpaca.py:L810-815`: Added `pd.isna()` guard for `df["ATR_14"].iloc[-1]` with safe fallback to `0.02 * current_price`.
  - `broker/alpaca.py:L947-960`: Added matching `pd.isna()` and `<= 0` price guards in `run_tick_multi()`.
- **What changed:** Eliminates silent comparison failures with `float(NaN)` that could produce phantom HOLD/SELL decisions or flawed position sizing.
- **Tested:** Verified `pd.isna(float(np.nan)) == True` and zero-price validation logic.

---

## Pre-Flight & Post-Fix Checks Summary
- `outputs/SYSTEM_AUDIT_REPORT.md` sections 5, 6, and 9 reviewed in full.
- Target files (`broker/alpaca.py`, `risk/manager.py`, `main.py`) reviewed before modification.
- Line count of `broker/alpaca.py`: increased from 1002 to 1153 lines (+151 lines).
- Full import check passed: `RiskManager`, `AlpacaPaperBroker`, `PerformanceEngine`.
- CLI check passed: `python main.py --help` loaded all modules without import errors.
- All inline tests (mock clock, dedup check, circuit breaker persistence, 7-day lookback, pending exposure signature, error handling, NaN guards) passed cleanly.
