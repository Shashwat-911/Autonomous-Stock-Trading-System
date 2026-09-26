# PROMPT 02 Fix Log — Critical Security & Data Integrity Fixes

**Date:** 2026-09-26  
**Status:** All 7 fixes applied and verified  
**Audit Reference:** `outputs/SYSTEM_AUDIT_REPORT.md` (C-1, C-2, H-6, H-7, H-8, L-16, L-18)

---

## Fix 1 — API Key Security (Audit: C-1)
- **Files modified:** `config.py`, `main.py`, `.env.example`, `.gitignore`
- **Lines changed:**
  - `config.py:L85-90`: Removed hardcoded plaintext API key and secret fallback literals. Replaced with `os.getenv("ALPACA_API_KEY")` and `os.getenv("ALPACA_SECRET_KEY")` with no fallback string (defaults to `None`).
  - `.env.example:L1-5`: Created template file for paper trading environment variables.
  - `main.py:L58-71`: Added `_validate_credentials()` function that checks `config.ALPACA` for missing keys and raises a clear `ValueError`.
  - `main.py:L389`: Called `_validate_credentials()` at the very start of `run_live()` before any broker or risk initialization.
  - `.gitignore:L32`: Verified `.env` is properly ignored (confirmed present at line 32).
- **What changed:** Hardcoded Alpaca API keys removed from tracked source code. Startup validation fails fast if credentials are not configured in environment or `.env`.
- **Tested:** Tested `_validate_credentials()` when keys are unset → correctly raised `ValueError: Missing required environment variables: ALPACA_API_KEY`. Tested credential loading with `.env` → verified loaded.

---

## Fix 2 — PnL Round-Trip Matching (Audit: C-2)
- **Files modified:** `broker/alpaca.py`, `analytics/metrics.py`
- **Lines changed:**
  - `broker/alpaca.py:L839-890`: Implemented `_build_round_trips(self, orders_df: pd.DataFrame) -> pd.DataFrame` which performs FIFO matching between filled BUY orders and subsequent filled SELL orders per ticker. Computes `pnl`, `pnl_pct`, and `hold_duration_minutes`.
  - `broker/alpaca.py:L927`: Updated `get_trade_history()` to return the output of `self._build_round_trips(orders_df)` instead of raw orders.
  - `analytics/metrics.py:L190-234`: Replaced `_trade_metrics(self, trades_df: pd.DataFrame)` to read the matched `pnl` column directly, computing total trades, winning/losing counts, win rate, expectancy, profit factor, average gain, and average loss.
- **What changed:** Fixed root cause where market orders had `price=0`, producing meaningless PnL values (`filled_avg_price - 0 = filled_avg_price`). Round trips now properly calculate PnL as `(exit_price - entry_price) * qty`.
- **Tested:** Executed inline test with synthetic round-trip trades:
  - Total trades: 2, Win rate: 0.5, Avg gain: $25.0, Avg loss: -$15.0, Expectancy: 5.0, Profit factor: 1.6667.
  - Assertions passed with `PnL fix verified OK`.
  - Verified `_build_round_trips` with synthetic BUY/SELL order DataFrame → matched 1 round-trip with PnL $100.0, 120.0 minutes duration.

---

## Fix 3 — Day-Start Balance From Broker (Audit: H-6)
- **Files modified:** `risk/manager.py`, `main.py`
- **Lines changed:**
  - `risk/manager.py:L397-409`: Added public method `sync_day_start_balance(self, current_equity: float) -> None` that updates `self._day_start_balance = current_equity`, resets `_daily_loss_breached = False`, and logs the balance synchronization.
  - `main.py:L469-474`: In `run_live()`, after fetching account info via `brokers[tickers[0]].get_account_info()`, added synchronization call `rm.sync_day_start_balance(actual_equity)` and `rm.reset_daily_state()`.
- **What changed:** Circuit breaker baseline is now synchronized to the actual opening broker equity rather than being hardcoded to the initial config balance ($100,000).
- **Tested:** Verified import and execution; confirmed `sync_day_start_balance` updates internal baseline and resets breach status.

---

## Fix 4 — Order Pagination Fix (Audit: H-7)
- **Files modified:** `broker/alpaca.py`
- **Lines changed:**
  - `broker/alpaca.py:L4`: Added `timedelta` and `timezone` to `datetime` imports.
  - `broker/alpaca.py:L901-908`: Updated `GetOrdersRequest` in `get_trade_history()` to pass `limit=500` and `after=after_date` (`datetime.now(timezone.utc) - timedelta(days=2)`).
- **What changed:** Overrode Alpaca's default 50-order limit by requesting up to 500 orders filtered to the last 2 days of trading, preventing truncation of order history.
- **Tested:** Inspected SDK request model; verified `GetOrdersRequest(limit=500, after=...)` executes and constructs valid request without error.

---

## Fix 5 — Session Deduplication in CSV (Audit: H-8)
- **Files modified:** `analytics/metrics.py`, `outputs/trade_history.csv`
- **Lines changed:**
  - `analytics/metrics.py:L341-343`: Extracted `_build_session_row(self) -> dict` helper.
  - `analytics/metrics.py:L345-392`: Updated `append_session_stats(self, filepath: str)` to add a `date` column (`date.today().isoformat()`), backfill `date` from `session_timestamp` if missing in existing CSV, and filter out existing rows for today's date before appending to prevent duplicate rows on restarts.
  - `outputs/trade_history.csv`: Backfilled `date` column for all 44 existing historical rows using ISO date strings extracted from `session_timestamp`.
- **What changed:** Process restarts within the same trading day now overwrite/update today's row rather than creating multiple duplicate rows in `trade_history.csv`.
- **Tested:** Executed deduplication test with mock session rows: verified 2 consecutive calls on the same date yielded exactly 1 updated row.

---

## Fix 6 — reset_daily_state in Live Mode (Audit: L-16)
- **Files modified:** `risk/manager.py`, `main.py`
- **Lines changed:**
  - `risk/manager.py:L411-420`: Updated `reset_daily_state()` to explicitly set `self._stop_loss_count = 0` in addition to resetting `_daily_loss_breached = False` and `_cooldown_until = None`.
  - `main.py:L473`: Called `rm.reset_daily_state()` at session startup in `run_live()` immediately after equity sync.
- **What changed:** Daily risk tracking variables (circuit breaker flag, cooldown timer, stop-loss counter) are cleanly reset at the start of each live session.
- **Tested:** Verified method resets all 3 state fields: `_daily_loss_breached`, `_cooldown_until`, and `_stop_loss_count`.

---

## Fix 7 — Hold Filter `.total_seconds()` Bug (Audit: L-18)
- **Files modified:** `broker/alpaca.py`
- **Lines changed:**
  - `broker/alpaca.py:L675-676`: Replaced `(datetime.now() - self._last_buy_time[self.ticker]).seconds / 60` with `.total_seconds() / 60`.
  - `broker/alpaca.py:L695-696`: Replaced fallback branch `(datetime.now() - self._last_buy_time[self.ticker]).seconds / 60` with `.total_seconds() / 60`.
- **What changed:** Eliminated 24-hour modulo wrap-around where positions held >24 hours were incorrectly treated as freshly entered (e.g. 25h 30m wrapping to 30m).
- **Tested:** Scanned file to ensure 0 remaining `.seconds` usages. Verified `timedelta(hours=25, minutes=30).total_seconds() / 60 == 1530.0` vs previous incorrect `30.0`.

---

## Pre-Flight & Post-Fix Checks Summary
- `outputs/SYSTEM_AUDIT_REPORT.md` sections 7, 9, and 11 reviewed in full.
- All target files read in full prior to code modifications.
- Pre-flight import verification: passed.
- Post-fix import verification (`RiskManager`, `PerformanceEngine`, `AlpacaPaperBroker`): `all imports OK` (passed).
- CLI verification (`python main.py --help`): CLI loaded intact (passed).
- PnL metrics calculation unit test: passed all assertions.
- Deduplication test: passed.
- Round-trip generator test: passed.
