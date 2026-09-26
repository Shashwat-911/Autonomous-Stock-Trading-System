# SYSTEM AUDIT REPORT — Autonomous Stock Trading System

**Auditor:** Senior Quantitative Systems Engineer (AI)  
**Date:** 2026-09-26  
**Scope:** Full pre-production audit of every file, function, and execution path  
**Verdict:** NOT production-ready — 18 issues identified, 3 Critical, 5 High

---

## SECTION 1: System Identity Card

| Property | Value |
|---|---|
| Primary execution file | `main.py` (693 lines) — CLI dispatch via `main()` at L667 |
| Broker integration | Alpaca Markets (`alpaca-py >= 0.20.0`) — paper trading only (`paper=True`) |
| Trading universe (tickers) | 20 tickers: NVDA, AAPL, MSFT, TSLA, AMZN, GOOGL, META, AMD, NFLX, CRM, JPM, GS, BAC, V, MA, LLY, UNH, JNJ, PG, XOM |
| Bar interval | `1h` (hourly candles) for live trading; `1d` daily for multi-timeframe alignment |
| Scan frequency | Every 15 minutes (`scan_interval_minutes: 15`) |
| Risk per trade | 1% of equity via ATR (`risk_pct_per_trade: 0.01`) |
| Max daily loss circuit breaker | 5% (`max_daily_loss_pct: 0.05`) |
| Position sizing method | ATR-based: `shares = floor(equity * 0.01 / (ATR * 2.0))`, capped at min($3000, equity * 5%) |
| Signal engine type | Rule-based multi-indicator (RSI, MACD, SMA, BB) + optional LightGBM meta-label filter |
| Walk-forward validation | Yes — `backtest/walk_forward.py` (6-month train / 3-month test, rolling windows) |
| GPU acceleration | Inactive — CuPy module exists (`strategy/gpu_indicators.py`) but falls back to CPU NumPy. Not wired into live trading path. |
| Database backend | SQLite (`broker/trades.db`) for LocalPaperBroker; Alpaca API for live mode (no local DB in live) |
| Total lines of Python code | **8,351** across 37 `.py` files |
| External dependencies (pip) | pandas, numpy, yfinance, python-dateutil, alpaca-py, openpyxl, matplotlib, python-dotenv, (optional: cupy, lightgbm, scikit-learn) |

---

## SECTION 2: Architecture Map

```
main.py: main() [L667]
  |-- CLI arg: 'backtest' --> run_backtest() [L109]
  |    |-- config.TRADING["ticker"] --> str
  |    |-- data/fetcher.py: get_historical_data(ticker, start, end, interval) --> pd.DataFrame
  |    |    +-- yfinance.Ticker.history() with @retry_on_failure(3) decorator
  |    |-- strategy/indicators.py: add_all_indicators(df) --> pd.DataFrame
  |    |    |-- add_sma(df, 20) --> pd.DataFrame [SMA_20]
  |    |    |-- add_ema(df, 20) --> pd.DataFrame [EMA_20]
  |    |    |-- add_rsi(df, 14) --> pd.DataFrame [RSI_14]
  |    |    |-- add_macd(df, 12, 26, 9) --> pd.DataFrame [MACD, MACD_Signal, MACD_Hist]
  |    |    |-- add_bollinger_bands(df, 20, 2) --> pd.DataFrame [BB_Upper, BB_Middle, BB_Lower]
  |    |    |-- add_atr(df, 14) --> pd.DataFrame [ATR_14]
  |    |    +-- add_adx(df, 14) --> pd.DataFrame [ADX_14, DI_plus_14, DI_minus_14]
  |    |-- build_components(db_path) --> (RiskManager, SignalGenerator, LocalPaperBroker)
  |    +-- for i in range(n): broker.run_tick(window_df) --> dict
  |
  |-- CLI arg: 'paper' --> run_paper() [L220]
  |    +-- while True: [60s sleep loop]
  |         |-- get_historical_data() --> pd.DataFrame
  |         |-- add_all_indicators(df) --> pd.DataFrame
  |         +-- broker.run_tick(df) --> dict
  |
  |-- CLI arg: 'walkforward' --> run_walkforward() [L324]
  |    +-- WalkForwardBacktester.run() --> dict{windows, summary}
  |         +-- per window: LocalPaperBroker(db=':memory:').run_tick() loop
  |
  +-- CLI arg: 'live' --> run_live() [L357]
       |-- RiskManager(...) [L380-391] — from config.RISK
       |-- SignalGenerator(rm, ...) [L392-398] — from config.SIGNAL
       |-- for ticker in tickers: AlpacaPaperBroker(...) [L404-414]
       |-- PerformanceEngine() [L438]
       +-- while True: [scan_interval_secs sleep loop]
            |-- get_market_regime_data("SPY", 200) --> dict{is_bullish, price, sma}
            |    +-- yf.Ticker("SPY").history(period="260d", interval="1d")
            |
            |-- for ticker in tickers:
            |    |-- get_intraday_data(ticker, 30, "1h") --> pd.DataFrame
            |    |    +-- yf.Ticker.history(period="30d", interval="1h")
            |    |-- add_all_indicators(df) --> pd.DataFrame
            |    |-- get_historical_data(ticker, 30d, now, "1d") --> pd.DataFrame [daily trend]
            |    |    +-- daily_close > daily_sma_20 --> bool (daily_trend_bullish)
            |    +-- brokers[ticker].run_tick(df, market_regime_bullish, daily_trend_bullish)
            |         |-- [GET] Alpaca: client.get_clock() --> Clock{is_open, next_close}
            |         |-- [GET] Alpaca: client.get_account() --> Account{equity, cash}
            |         |-- risk/manager.py: rm.can_trade(portfolio_value) --> (bool, str)
            |         |    |-- checks: daily_loss_pct >= 0.05 --> BLOCK
            |         |    +-- checks: cooldown_until > now --> BLOCK
            |         |-- [GET] Alpaca: client.get_open_position(ticker) --> Position|None
            |         |-- _update_trailing_stop(ticker, price) [mental stop only]
            |         |-- rm.check_stop_loss(entry, current) --> (bool, str)
            |         |    +-- if (entry-current)/entry >= 0.05 --> trigger + cooldown
            |         |-- signals.py: sg.generate_signal(df, pv, regime, daily) --> dict
            |         |    |-- reads: RSI_14, MACD, MACD_Signal, Close, SMA_20, BB_Lower, ADX_14
            |         |    |-- 4 BUY conditions + momentum crossover path
            |         |    |-- 3+1 SELL conditions (RSI overbought, MACD bearish, below BB, risk block)
            |         |    |-- ADX gate: adx < 24.0 --> hard BLOCK on BUY
            |         |    |-- Market regime gate: SPY < SMA-200 --> hard BLOCK on BUY
            |         |    +-- [optional] ml/predictor.py: MetaLabelPredictor.should_trade(df)
            |         |         +-- LightGBM model.predict_proba() >= 0.65
            |         |-- [if BUY + conf >= 0.70 + can_trade]:
            |         |    |-- [GET] Alpaca: client.get_all_positions() --> positions
            |         |    |-- rm.check_portfolio_heat(exposure, equity) --> (bool, str)
            |         |    |-- rm.get_position_size_atr(equity, price, atr) --> int
            |         |    +-- [POST] Alpaca: submit_bracket_buy(qty, reason, price, atr,
            |         |         |                                SL=2*ATR, TP=2.5*ATR)
            |         |         +-- MarketOrderRequest(order_class=BRACKET, take_profit, stop_loss)
            |         +-- [if SELL + position exists]:
            |              |-- [GET] Alpaca: client.get_orders(OPEN, ticker)
            |              |-- if bracket legs active --> skip (let bracket handle exit)
            |              |-- if held < 60 min --> skip (hold filter)
            |              +-- [POST] Alpaca: submit_sell("ALL", reason) or close_position(ticker)
            |
            |-- Portfolio summary display
            |-- Market clock check --> if CLOSED: break
            +-- time.sleep(scan_interval_secs)

       finally: SESSION WRAP-UP [L579-638]
            |-- for ticker in tickers: brokers[ticker].get_trade_history() --> pd.DataFrame
            |    +-- [GET] Alpaca: client.get_orders(ALL, ticker) --> list[Order]
            |-- PerformanceEngine.compute_from_trades(combined, equity_curve,
            |                                        starting_equity, live_equity)
            |    |-- _estimate_equity_curve() or equity_curve from alpaca_equity_history.csv
            |    |-- _sharpe_ratio(returns) --> float (annualized)
            |    |-- _sortino_ratio(returns) --> float (annualized)
            |    |-- _max_drawdown(equity_curve) --> (float, int)
            |    |-- _trade_metrics(trades_df) --> dict{win_rate, expectancy, profit_factor}
            |    +-- _compute_slippage(trades_df) --> dict{avg_slippage_pct, latency_ms}
            |-- perf_engine.save_summary("outputs/performance_summary.json") --> [WRITE] JSON
            +-- perf_engine.append_session_stats("outputs/trade_history.csv") --> [APPEND] CSV
```

**SQLite writes** occur only in `LocalPaperBroker` (backtest/paper modes) at `broker/paper.py:L193-215` (`_save_trade()`).  
**No SQLite writes** occur in `AlpacaPaperBroker` (live mode) — all persistence is via Alpaca API + CSV/JSON.  
**`time.sleep()`** occurs at: `main.py:L286` (60s, paper mode), `main.py:L566` (scan_interval_secs=900, live mode).

---

## SECTION 3: Indicator Mathematics — Verified Implementation

### SMA (Simple Moving Average)
**Code** (`indicators.py:L37-38`):
```python
res[col_name] = res[column].rolling(window=window).mean()
```
**Formula:** SMA(n) = (Sum of Close[i] for i=1..n) / n  
**Verification:** CORRECT — pandas `.rolling().mean()` implements this exactly.  
**Warmup:** 20 bars (first valid SMA_20 at bar 20). First 19 bars = NaN.  
**Edge cases:** None unhandled — NaN propagation is correct.

### EMA (Exponential Moving Average)
**Code** (`indicators.py:L63`):
```python
res[col_name] = res[column].ewm(span=window, adjust=False).mean()
```
**Formula:** EMA(t) = alpha * Close(t) + (1-alpha) * EMA(t-1), where alpha = 2/(span+1)  
**Verification:** CORRECT — `adjust=False` gives recursive EMA. alpha = 2/21 = 0.0952.  
**Warmup:** Technically produces values from bar 1 (no `min_periods`), but is unreliable for ~20 bars.  
**Edge cases:** No `min_periods` set — EMA is valid from bar 1 but "warm" by ~20.

### RSI (Relative Strength Index — Wilder's Smoothing)
**Code** (`indicators.py:L88-100`):
```python
avg_gain = gain.ewm(alpha=1/window, min_periods=window, adjust=False).mean()
avg_loss = loss.ewm(alpha=1/window, min_periods=window, adjust=False).mean()
rs = avg_gain / avg_loss
rsi = 100.0 - (100.0 / (1.0 + rs))
rsi = rsi.where(avg_loss != 0, 100.0)
```
**Formula:** RSI = 100 - 100/(1 + RS), RS = avg_gain/avg_loss, Wilder's alpha = 1/14  
**Verification:** CORRECT — `alpha=1/window` implements Wilder's smoothing exactly. The `where(avg_loss != 0, 100.0)` correctly handles the division-by-zero edge case.  
**Warmup:** 15 bars (`min_periods=14` on the ewm + 1 bar for the initial `diff()`). First 14 bars = NaN.  
**Edge cases:** Division by zero handled explicitly.

### MACD (Moving Average Convergence Divergence)
**Code** (`indicators.py:L135-143`):
```python
ema_fast = res[column].ewm(span=fast, adjust=False).mean()  # span=12
ema_slow = res[column].ewm(span=slow, adjust=False).mean()  # span=26
macd_line = ema_fast - ema_slow
signal_line = macd_line.ewm(span=signal, adjust=False).mean()  # span=9
```
**Formula:** MACD = EMA(12) - EMA(26); Signal = EMA(9) of MACD; Histogram = MACD - Signal  
**Verification:** CORRECT.  
**Warmup:** EMA(26) needs ~26 bars. Signal needs 9 more. Total: ~35 bars for stable values. No `min_periods` means technically produces values from bar 1, but they are unreliable.  
**Edge cases:** WARNING — No `min_periods` on any of the EMAs — values in first 26 bars are mathematically valid but statistically unreliable.

### Bollinger Bands
**Code** (`indicators.py:L173-178`):
```python
middle_band = res[column].rolling(window=window).mean()
rolling_std = res[column].rolling(window=window).std()
res["BB_Upper"] = middle_band + (num_std * rolling_std)
res["BB_Lower"] = middle_band - (num_std * rolling_std)
```
**Formula:** Middle = SMA(20), Upper = SMA(20) + 2*sigma, Lower = SMA(20) - 2*sigma  
**Verification:** CORRECT.  
**Warmup:** 20 bars. First 19 = NaN.  
**Edge cases:** If all prices identical, sigma=0 and bands collapse to the SMA. Not explicitly handled but harmless.

### ATR (Average True Range)
**Code** (`indicators.py:L208-221`):
```python
true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
res[col_name] = true_range.ewm(alpha=1.0/window, min_periods=window, adjust=False).mean()
```
**Formula:** TR = max(H-L, |H-Prev_C|, |L-Prev_C|); ATR = Wilder EMA of TR  
**Verification:** CORRECT — Wilder's smoothing applied to True Range.  
**Warmup:** 15 bars (14 for ewm + 1 for shift). First 14 bars = NaN.  
**Edge cases:** If ATR=0 (all prices identical), position sizing uses `atr <= 0` guard in `get_position_size_atr()` (returns 0). Safe.

### ADX (Average Directional Index)
**Code** (`indicators.py:L226-267`):
```python
dm_plus = dm_plus.where((dm_plus > dm_minus) & (dm_plus > 0), 0.0)
# Wilder's smoothing, then DI+, DI-, DX, ADX
```
**Formula:** Standard Wilder's ADX implementation. DM+/DM- -> smooth with alpha=1/14 -> DI+/- = 100*smooth_DM/smooth_ATR -> DX = 100*|DI+ - DI-|/(DI+ + DI-) -> ADX = smooth DX.  
**Verification:** CORRECT. The `dm_plus.where(...)` line zeroes out DM+ if DM- is larger, matching Wilder's specification. Division by zero handled via `.replace(0, float('nan'))`.  
**Warmup:** ~42 bars (14 for ATR + 14 for DI + 14 for DX smoothing). First ~28 bars = NaN.  
**Edge cases:** Division by zero handled via NaN replacement.

### Warmup Math: 60-bar lookback (1h interval)

With 30 days of 1h bars (~7 trading hours/day x 30 days = **~147 bars** fetched via `get_intraday_data(ticker, 30, "1h")`):

| Indicator | Warmup Bars | Valid by bar? | Status |
|---|---|---|---|
| SMA_20 | 20 | 20 | VALID |
| EMA_20 | ~20 (no min_periods) | 1 (unreliable until ~20) | VALID (noisy early) |
| RSI_14 | 15 | 15 | VALID |
| MACD | ~35 | 1 (unreliable until ~35) | VALID (noisy early) |
| BB | 20 | 20 | VALID |
| ATR_14 | 15 | 15 | VALID |
| ADX_14 | ~42 | ~42 | VALID (147 >> 42) |

**Conclusion:** With ~147 bars, all indicators produce valid, non-NaN values by the time `generate_signal()` reads the last row. The system is safe here.

---

## SECTION 4: Signal Logic — Full Decision Tree

### Complete Decision Tree

```
generate_signal(df, portfolio_value, market_regime_bullish, daily_trend_bullish)
|
|-- [1] RISK GATE: rm.can_trade(portfolio_value)
|    |-- daily_loss >= 5% --> blocked=True
|    |-- cooldown active --> blocked=True
|    +-- else --> blocked=False
|
|-- [2] MARKET REGIME: if not market_regime_bullish --> regime_blocked=True
|
|-- [3] EVALUATE BUY CONDITIONS (4 conditions):
|    |-- cond_rsi_oversold:  RSI_14 < 37.0           [L176]
|    |-- cond_macd_bullish:  MACD > MACD_Signal       [L181]
|    |-- cond_above_sma:    Close > SMA_20            [L186]
|    +-- cond_above_bb:     Close > BB_Lower          [L191]
|    |
|    |-- buy_count = sum(conditions)
|    |-- buy_confidence = min(buy_count * 0.25, 1.0)  [L208]
|    |
|    |-- MOMENTUM CROSSOVER PATH:                      [L197-210]
|    |    |-- MACD[-1] > Signal[-1] AND MACD[-2] <= Signal[-2]  (crossover)
|    |    |-- Close > SMA_20
|    |    |-- 40.0 <= RSI <= 65.0
|    |    +-- if all three: momentum_buy=True, buy_confidence = max(0.75, current)
|    |
|    +-- DAILY TREND PENALTY:                          [L213-215]
|         +-- if !daily_trend_bullish AND buy_count >= 2:
|              buy_confidence -= 0.25 (floored at 0.0)
|
|-- [4] EVALUATE SELL CONDITIONS (3+1 conditions):
|    |-- cond_rsi_overbought: RSI_14 > 71.0            [L221]
|    |-- cond_macd_bearish:   MACD < MACD_Signal        [L228]
|    |-- cond_below_bb:       Close < BB_Lower           [L233]
|    +-- cond_forced_exit:    blocked (from risk gate)   [L240]
|    |
|    |-- sell_count = sum(sell_conditions)
|    +-- sell_confidence = min(sell_count * 0.33, 1.0)   [L246]
|
|-- [5] DETERMINE FINAL SIGNAL:
|    |-- path1_triggered:
|    |    |-- if require_confirmation=True: ALL 4 buy conditions must be True
|    |    +-- if require_confirmation=False: >= 3 of 4 buy conditions  [L254-255]
|    |
|    |-- adx_blocked: ADX_14 < 24.0 --> HARD BLOCK on BUY  [L258]
|    |
|    |-- buy_triggered = (path1 OR momentum_buy)
|    |                   AND NOT blocked
|    |                   AND NOT regime_blocked
|    |                   AND NOT adx_blocked           [L265-270]
|    |
|    |-- [OPTIONAL] ML META-LABEL FILTER:              [L284-298]
|    |    +-- if buy_triggered AND _META_AVAILABLE:
|    |         |-- predictor.should_trade(df) --> (bool, float)
|    |         +-- if P(success) < 0.65 --> buy_triggered = False
|    |
|    |-- sell_triggered = sell_count >= 1               [L281]
|    |
|    +-- PRIORITY:
|         |-- if buy_triggered --> signal="BUY", confidence=buy_confidence
|         |-- elif sell_triggered --> signal="SELL", confidence=sell_confidence
|         +-- else --> signal="HOLD", confidence=0.0
```

### Specific Questions Answered

**Q1: What produces SELL at confidence=0.33 on 18/20 tickers every scan?**

A SELL at confidence `0.33` means exactly **one** sell condition is true (`sell_count=1`, `1 * 0.33 = 0.33`). The condition `cond_macd_bearish = macd < macd_signal` fires whenever the MACD line is below the signal line (`signals.py:L228-231`). This is the **natural state** for most tickers most of the time — the MACD oscillates around the signal line, and on any given hourly scan, roughly half or more of tickers will have MACD < Signal. Since `sell_triggered = sell_count >= 1` (L281), a **single** MACD-bearish condition is sufficient to generate a SELL signal. This is why 18/20 tickers show SELL@0.33 — they simply have MACD < Signal at scan time. However, this SELL signal is **harmless for tickers with no position** because `alpaca.py:L642` only acts on SELL if `position is not None`.

**Q2: Minimum conditions for BUY at confidence >= 0.70?**

With `require_confirmation=False` (as configured in live mode at `main.py:L396`):
- **Path 1:** 3 of 4 conditions must be true (`buy_conditions_met >= 3`, L255), giving `buy_confidence = 0.75`. The minimum set: RSI < 37, MACD > Signal, Close > SMA_20 (with Close > BB_Lower being almost always true). Confidence = 0.75 >= 0.70.
- **Path 2 (Momentum):** MACD crossover + Close > SMA_20 + RSI in [40, 65], giving `buy_confidence = 0.75` (forced minimum at L210).

**Q3: Can a ticker satisfy both BUY and SELL simultaneously?**

Yes. Example: RSI=36 (oversold -> BUY condition), MACD < Signal (bearish -> SELL condition), Close > SMA_20 (BUY condition), Close > BB_Lower (BUY condition). This gives `buy_count=3` and `sell_count=1`. **Priority resolution at L300-318:** `buy_triggered` is checked first. If BUY conditions pass all gates (ADX, regime, risk), the signal is BUY. SELL is only emitted if BUY is not triggered. There is no conflict — BUY takes priority.

**Q4: ADX filter when ADX < 24?**

It is a **HARD BLOCK** on BUY. At `signals.py:L258-269`: `adx_blocked = adx < self.adx_min` (24.0). `buy_triggered` requires `not adx_blocked`. If ADX < 24, `buy_triggered = False` regardless of how many BUY conditions are met. The ADX filter does NOT reduce confidence — it completely prevents the BUY signal. The confidence value is calculated but never used because the signal becomes SELL or HOLD instead.

**Q5: Daily trend bearish penalty?**

At `signals.py:L213-215`:
```python
if not daily_trend_bullish and buy_count >= 2:
    buy_confidence = max(0.0, buy_confidence - 0.25)
    buy_reasons.append("Daily trend bearish (confidence reduced)")
```
The daily trend is calculated in `main.py:L470-483`: fetch 30 days of daily bars, compute 20-day SMA, compare last close to SMA. If `daily_close <= daily_sma_20`, `daily_trend_bullish=False`. The penalty is a **0.25 reduction** in buy_confidence. This can drop a 0.75 confidence to 0.50, which would be below the 0.70 threshold, effectively blocking the trade. It is a **soft penalty** that functionally becomes a hard block when confidence is near the threshold.

---

## SECTION 5: Risk Manager — State Machine Audit

### State Variables

| Variable | Init Location | Init Value | Mutated By | Persists Across Ticks? | Persists Across Sessions? |
|---|---|---|---|---|---|
| `initial_balance` | `manager.py:L77` | `config.TRADING["initial_balance"]` = 100000.0 | Never mutated | Yes | No (re-init at process start) |
| `_day_start_balance` | `manager.py:L89` | Same as `initial_balance` | `reset_daily_state()` (but never called in live mode) | Yes | No |
| `_daily_loss_breached` | `manager.py:L90` | `False` | `can_trade()` sets to `True` when loss >= 5% (L148) | Yes | No |
| `_cooldown_until` | `manager.py:L93` | `None` | `check_stop_loss()` sets to `now + cooldown_minutes` (L274) | Yes | No |
| `_stop_loss_count` | `manager.py:L94` | `0` | `check_stop_loss()` increments (L272) | Yes | No |
| `max_daily_loss_pct` | `manager.py:L78` | 0.05 | Never | N/A | N/A |
| `max_trade_loss_pct` | `manager.py:L79` | 0.05 | Never | N/A | N/A |
| `max_position_pct` | `manager.py:L80` | 0.05 | Never | N/A | N/A |
| `cooldown_minutes` | `manager.py:L81` | 5 | Never | N/A | N/A |
| `max_position_dollars` | `manager.py:L82` | 3000.0 | Never | N/A | N/A |
| `max_portfolio_heat_pct` | `manager.py:L83` | 0.60 | Never | N/A | N/A |

### Circuit Breaker Condition

The circuit breaker fires at `manager.py:L147-155`:
```python
daily_loss_pct = (self._day_start_balance - current_portfolio_value) / self._day_start_balance
if daily_loss_pct >= self.max_daily_loss_pct:  # >= 0.05
    self._daily_loss_breached = True
```
Once breached, trading is halted **permanently for the session** (L157-163). The `_daily_loss_breached` flag stays `True` even if the portfolio recovers. Only `reset_daily_state()` clears it, and **`reset_daily_state()` is never called in the live trading path** (`main.py:run_live()`).

### Cooldown Condition

A cooldown is triggered at `manager.py:L271-283`:
```python
if loss_pct >= self.max_trade_loss_pct:  # >= 0.05 (5%)
    self._cooldown_until = now + timedelta(minutes=self.cooldown_minutes)  # 5 min
```
The cooldown blocks trading for 5 minutes after a stop-loss event. It naturally expires when `now >= self._cooldown_until` (L167-177).

### What happens to positions when circuit breaker fires?

**Nothing automatically.** When `can_trade()` returns `False` due to daily loss breach, the `generate_signal()` method at `signals.py:L240-243` adds a "Forced exit" SELL condition. This means `sell_triggered=True` and the signal becomes SELL. However, this SELL signal only results in liquidation if the ticker has an open position (`alpaca.py:L642`) AND the bracket legs check passes. **Open positions with bracket orders are NOT automatically liquidated by the circuit breaker.**

### Is `_day_start_balance` read from broker at session start?

**No.** It is set to `config.TRADING["initial_balance"]` (100000.0) at construction time (`manager.py:L89`). The actual broker equity (e.g., $99,940) is NOT used as the day-start balance. This means the daily loss calculation compares against the **original starting balance**, not today's opening equity.

---

## SECTION 6: Broker Integration — Alpaca API Audit

### API Call Inventory

| API Call | Method | Endpoint | When Called | What it Returns | Error Handling? |
|---|---|---|---|---|---|
| `get_clock()` | GET | `/v2/clock` | Every tick + market close check | `Clock{is_open, next_open, next_close}` | YES: Try/except returns None (L130-134) |
| `get_account()` | GET | `/v2/account` | Every tick (via `get_account_info()`) | `Account{cash, equity, buying_power}` | PARTIAL: Bare except in run_tick falls back to 100000 (L545-546) |
| `get_open_position(ticker)` | GET | `/v2/positions/{ticker}` | Every tick | `Position` or raises 404 | YES: Returns None on any exception (L172-173) |
| `get_all_positions()` | GET | `/v2/positions` | Portfolio heat check + portfolio summary | `list[Position]` | YES: Returns {} on exception (L196-197) |
| `submit_order()` (buy) | POST | `/v2/orders` | On BUY signal | `Order{id, status}` | NO: No try/except in `submit_buy()` — will crash |
| `submit_order()` (bracket) | POST | `/v2/orders` | On BUY signal with ATR>0 | `Order{id}` with bracket legs | YES: Falls back to market buy on failure (L336-341) |
| `submit_order()` (sell) | POST | `/v2/orders` | On SELL signal | `Order{id}` | YES: Try/except logs and returns {} (L468-470) |
| `close_position(ticker)` | DELETE | `/v2/positions/{ticker}` | Full position liquidation | `Order` | YES: Falls back to cancel+market sell (L434-440) |
| `get_orders(OPEN, ticker)` | GET | `/v2/orders?status=open` | Bracket check + cancel orders | `list[Order]` | YES: Try/except (L370-371) |
| `cancel_order_by_id(id)` | DELETE | `/v2/orders/{id}` | Pre-sell cleanup | success/failure | YES: Per-order try/except (L368-369) |
| `get_orders(ALL, ticker)` | GET | `/v2/orders?status=all` | Trade history retrieval | `list[Order]` | YES: Returns empty DataFrame (L873-875) |

### Specific Questions

**Q1: What happens if `get_clock()` throws?**  
The scan loop does NOT crash. `get_clock()` at `alpaca.py:L130-134` catches all exceptions and returns `None`. `is_market_open()` at L119 returns `False` when clock is `None`. In `main.py:L532-538`, if clock fails, it falls back to local timezone calculation.

**Q2: What happens on 422 (insufficient buying power)?**  
`submit_buy()` at `alpaca.py:L229` has NO try/except — a 422 error would propagate up. However, `submit_bracket_buy()` at L293-341 DOES catch exceptions and falls back to `submit_buy()`. In `main.py:L511`, the per-ticker try/except catches it and prints ERROR, then continues to next ticker.

**Q3: Bracket order legs and price calculations?**  
At `alpaca.py:L284-302`:
- **Stop-loss price:** `current_price - (stop_loss_mult * ATR)` = `price - (2.0 * ATR)`
- **Take-profit price:** `current_price + (take_profit_mult * ATR)` = `price + (2.5 * ATR)`
- **Order class:** `OrderClass.BRACKET` with `TimeInForce.GTC`
- **Legs:** 1 parent market buy + 1 stop-loss leg + 1 take-profit limit leg (3 legs total)
- Guard: if `stop_price <= 0`, fallback to `price * 0.95`. If `take_profit_price <= current_price`, fallback to `price * 1.06`.

**Q4: "SELL skipped — bracket exit orders active" logic?**  
Implemented at `alpaca.py:L643-708`. Function: `run_tick()`. It queries open orders for the ticker, filters for order types `stop`, `limit`, or `stop_limit` (bracket legs). If any exist, manual sell is skipped — the bracket will handle the exit. **There is NO timeout.** If a bracket order's stop-loss and take-profit are never hit, the position stays open **indefinitely**. This is a documented gap — there is no force-close mechanism.

**Q5: `feed=iex` parameter?**  
Set at `config.py:L89` and passed to `AlpacaPaperBroker.__init__()`. The IEX feed provides **free** 15-minute delayed quotes and does not include all exchanges. The `sip` feed (consolidated tape) provides real-time data from all US exchanges but requires a paid subscription. **Limitation:** IEX data is delayed and only covers IEX exchange volume (~2-5% of total market volume). However, the `feed` parameter is stored but **never actually used** in any API call in the code — it's only passed for informational purposes.

---

## SECTION 7: Metrics Engine — Data Integrity Audit

### Q1: Source of `starting_equity`

At `analytics/metrics.py:L56`, `starting_equity` is a parameter with default 100000.0. In the live path (`main.py:L617`), it's passed as `config.TRADING["initial_balance"]` = 100000.0. It is **hardcoded via config**, not read from the broker's actual day-start equity.

### Q2: Source of `ending_equity`

At `metrics.py:L95`: `metrics["ending_equity"] = live_equity if live_equity is not None else float(equity_curve.iloc[-1])`. In live mode (`main.py:L618`), `live_eq = account.get("equity")` is fetched from Alpaca. So `ending_equity` IS read from the broker — this is correct.

### Q3: How are winning/losing trades counted?

At `metrics.py:L190-246` (`_trade_metrics()`):
- Looks for `pnl` column first. If absent, estimates PnL from `filled_avg_price - price` for SELL trades.
- In live mode, `get_trade_history()` returns Alpaca order history. The `price` field is `o.limit_price or o.stop_price or 0` (L868). For **market orders**, both are None, so `price=0`. This means the PnL estimation logic (`filled_avg_price - price`) produces meaningless values — it's computing `fill_price - 0 = fill_price` as the "PnL".
- `total_trades` at L210 is `len(trades_df)` — the count of ALL orders (including buy orders, cancelled orders, partial fills), NOT just round-trip trades.

### Q4: Why does `total_trades: 50` never exceed 50?

Because Alpaca's `get_orders()` API returns a **maximum of 50 orders** by default (the API's default `limit` parameter). At `alpaca.py:L849-853`, no `limit` parameter is specified in `GetOrdersRequest`, so Alpaca returns the most recent 50 orders. This is a **pagination bug** — the system never retrieves orders beyond the first page.

### Q5: Why `avg_gain` shows values like $0.17 and $4.99?

The `avg_gain` is computed at `metrics.py:L224`: `float(wins.mean())`. The "PnL" is calculated as `filled_avg_price - price`. For market orders, `price=0`, so `pnl = filled_avg_price - 0 = filled_avg_price`. For stop/limit orders where `price` is nonzero, `pnl = fill - limit_price`, which is typically very small (a few cents of slippage). The $4.99 and $0.17 values represent the price difference between limit/stop price and fill price on bracket order legs, NOT actual trade profit.

### Q6: Why `profit_factor` alternates between extreme values?

Looking at `trade_history.csv`, alternating rows show two different computations. The extreme profit_factor values arise because `profit_factor = gross_gains / gross_losses`. When `gross_losses` is near zero (because the PnL calculation is broken for market orders), profit factor explodes to infinity or very large values. When `gross_gains` is near zero, it collapses. The duplicate rows come from multiple process restarts within the same session.

### Q7: Are Sharpe and Sortino computed correctly?

**Sharpe** (`metrics.py:L147-153`):
```python
excess = returns.mean() - self._daily_rf  # daily risk-free rate
sharpe = (excess / returns.std()) * np.sqrt(252)
```
Formula: Sharpe = (mean_excess_return / std_return) * sqrt(252). **Verification:** CORRECT annualization for daily returns.

**Sortino** (`metrics.py:L155-162`):
```python
downside = returns[returns < 0]
excess = returns.mean() - self._daily_rf
sortino = (excess / downside.std()) * np.sqrt(252)
```
**Verification:** PARTIALLY INCORRECT. Standard Sortino uses downside deviation computed from ALL returns (replacing positive returns with zero), not just the subset of negative returns. The current implementation uses `std()` of only negative returns, which overestimates downside risk.

---

## SECTION 8: Performance Data Reconciliation

### Discrepancy 1: Win Rate differences across outputs

The session log shows `Total Trades: 307` and `Win Rate: 29.6%`. The `performance_summary.json` shows `total_trades: 50, win_rate: 0.1143`.

**Root cause:** Two different populations. The 307 trades come from concatenating `get_trade_history()` across all 20 ticker brokers. The 50 trades in the JSON come from Alpaca's 50-order pagination limit per ticker. Additionally, the PnL calculation is fundamentally broken for market orders (price=0), making all win rate values unreliable regardless of sample size.

### Discrepancy 2: Duplicate timestamps on 2026-09-05

Lines 12-17 of `trade_history.csv` show 6 rows within the same date. **Cause:** The system was restarted multiple times (likely debugging). Each restart triggers the `finally` block in `run_live()`, which appends a new row to `trade_history.csv`. The `06:14` timestamps are UTC while `10:34` are IST (UTC+5:30), confirming timezone inconsistency.

### Discrepancy 3: Rows with `total_trades: 19` and `win_rate: 0.0`

This occurs when `get_trade_history()` returns only 19 orders (a session that barely started). The `win_rate: 0.0` with `winning_trades: 0` means the `pnls` Series was empty — likely because all 19 orders were BUY-only (no SELL trades matched in `_trade_metrics()` at L199, which filters for SELL trades only when using `filled_avg_price - price`).

### Discrepancy 4: Execution latency 573,896ms to 2,060ms

In August: `avg_execution_latency_ms: 573,896` (573 seconds = ~9.5 minutes). In September: `avg_execution_latency_ms: 2,060` (2 seconds).

**Cause:** The latency 60-second sanity cap at `metrics.py:L302-304` was added in a code update between August and September. Before the cap, bracket order legs whose `filled_at` was hours/days after `submitted_at` (waiting for SL/TP to hit) inflated the average. The 2,060ms in September reflects actual market order fill times with the 60s cap filtering out bracket legs.

---

## SECTION 9: Vulnerability Assessment

### Data Vulnerabilities

- **[Low] Look-ahead bias:** In backtesting, `add_all_indicators()` is applied to the full dataset before slicing (`main.py:L136`). However, MACD/EMA without `min_periods` only use past data in their rolling calculation. The walk-forward engine properly splits train/test. No actual look-ahead detected.
  - File: `main.py:L136`

- **[Low] Survivorship bias:** Ticker universe is a fixed list of 20 large-cap S&P 500 stocks in `config.py:L18-23`. All are currently active. Risk is minimal for this universe but would increase for small-cap stocks.
  - File: `config.py:L18-23`

- **[Medium] Data snooping:** RSI/MACD thresholds were tuned via Bayesian optimization (`ml/optimize.py`, `ml/optimal_params.json`) using overlapping time periods. The walk-forward test partially mitigates this, but the final threshold values were chosen from optimization results and hardcoded.
  - File: `config.py:L34-38`

- **[Medium] NaN poisoning:** In `run_tick()`, `current_price = float(df["Close"].iloc[-1])` at `alpaca.py:L538` has no NaN check. If `get_intraday_data()` returns a DataFrame with NaN in the last row, `current_price` would be NaN, and all downstream comparisons would silently fail (NaN comparisons return False), producing a phantom HOLD signal.
  - File: `alpaca.py:L538`

- **[Low] yfinance column name changes:** The fetcher handles MultiIndex flattening at `fetcher.py:L108-109`. Handled correctly.
  - File: `data/fetcher.py:L108`

### Execution Vulnerabilities

- **[Low] Race condition:** No shared mutable state between ticker processing. Tickers are processed sequentially in `main.py:L461`. The shared `RiskManager` only has mutations in `check_stop_loss()`, which is called sequentially. Safe.
  - File: `main.py:L461`

- **[High] Order duplication:** If the scan loop runs and a ticker has a bracket order pending fill, `get_current_position()` returns None, and the system may submit another BUY. The `position is None` check at `alpaca.py:L610` does not verify pending orders.
  - File: `alpaca.py:L610`

- **[Critical] Zombie positions:** There is NO timeout mechanism for bracket-held positions. Bracket orders use `TimeInForce.GTC` with no expiry. Combined with the bracket-active SELL skip logic, positions can remain open indefinitely.
  - File: `alpaca.py:L298`, `alpaca.py:L664`

- **[High] Circuit breaker bypass on restart:** `RiskManager.__init__()` resets all state. A stop-loss cooldown or daily loss breach active at restart time would be lost. No persistent state across restarts.
  - File: `risk/manager.py:L89-94`

- **[Critical] API key exposure:** Alpaca API keys are hardcoded as plaintext fallbacks in `config.py:L86-87`. While `.env` is gitignored, `config.py` is tracked in git and the keys are visible to anyone with repo access.
  - File: `config.py:L86-87`

### Financial Vulnerabilities

- **[Low] Position sizing with ATR=0:** `get_position_size_atr()` at `manager.py:L326` checks `atr <= 0` and returns 0. Safe.
  - File: `risk/manager.py:L326`

- **[Medium] Portfolio heat bypass:** Heat is checked per-ticker sequentially. If multiple tickers generate BUY signals in the same scan, each individually passes the heat check because the previous buy's position isn't reflected in `get_all_positions()` until Alpaca processes the order. Heat could breach 60%.
  - File: `alpaca.py:L601-608`

- **[Medium] Slippage underestimation:** The avg slippage metric is based on limit/stop order price vs fill price, NOT market order fills. Market orders (the primary order type) have unmeasured slippage.
  - File: `analytics/metrics.py:L263-280`

---

## SECTION 10: Pros and Cons — Honest Assessment

### Strengths

1. **Clean architecture and separation of concerns.** Each module has a single responsibility: `fetcher.py` fetches data, `indicators.py` computes indicators, `signals.py` generates signals, `manager.py` manages risk, `alpaca.py` executes orders. Code is well-documented with complete docstrings.

2. **Multi-layer safety system.** Four independent gates before any BUY order: (a) `can_trade()` circuit breaker, (b) market regime filter (SPY>SMA-200), (c) ADX trend strength filter, (d) portfolio heat cap. Defense-in-depth.

3. **Bracket order implementation with trailing stop tracking.** ATR-based stop-loss (2x ATR) and take-profit (2.5x ATR), with mental trailing stop logic at `alpaca.py:L473-522`.

4. **Walk-forward validation framework.** `backtest/walk_forward.py` implements proper out-of-sample testing with rolling train/test windows, preventing overfitting.

5. **ML meta-label filter.** LightGBM model trained with `TimeSeriesSplit` prevents data leakage. Filters BUY signals with P(success) < 0.65.

6. **Robust data fetching.** `@retry_on_failure` decorator with exponential backoff handles transient yfinance failures. MultiIndex column flattening handled consistently.

7. **ATR-based position sizing.** Using `shares = equity * 1% / (ATR * 2)` sizes positions inversely to volatility — sound risk management.

### Weaknesses

**(a) Fixable with code changes:**
1. API keys hardcoded in `config.py` — move to environment variables only
2. Alpaca order pagination capped at 50 — add `limit=500` to `GetOrdersRequest`
3. PnL calculation broken for market orders (`price=0`) — use entry/exit price matching
4. No position deduplication check before submitting BUY — check pending orders
5. No force-close timeout for zombie bracket positions — add EOD liquidation
6. `_day_start_balance` not synced from broker — read from `get_account_info()` at session start
7. `reset_daily_state()` never called in live mode — call at session start
8. Sortino ratio uses wrong downside deviation formula
9. Session metrics written from multiple restarts creating duplicates

**(b) Fixable with parameter tuning:**
1. SELL signal too sensitive — single MACD-bearish triggers SELL at conf=0.33, creating noise
2. RSI oversold threshold (37) rarely triggers on large-cap stocks — lower to 30-35
3. Cooldown too short (5 min) — a stop-loss at 5% loss should pause longer

**(c) Fundamental strategy limitations:**
1. Mean-reversion + trend-following hybrid creates conflicting signals — RSI oversold is mean-reversion, MACD + SMA are trend-following
2. 1-hour bars with 15-minute scans means the system evaluates the same candle multiple times until a new hourly candle forms
3. Long-only strategy during a bull market. Performance is highly correlated with SPY
4. The ML model is trained on daily bars but applied to hourly signals (timeframe mismatch)

### Production Readiness Score

| Dimension | Score | Justification |
|---|---|---|
| Signal quality | 4/10 | SELL fires on 90% of tickers every scan (single MACD condition). BUY conditions rarely align. 11.4% win rate in latest metrics. Strategy has negative expectancy. |
| Risk management | 6/10 | Multi-layer safety (circuit breaker, heat cap, ATR sizing). But `_day_start_balance` is stale, no persistent state across restarts, no zombie position cleanup. |
| Data pipeline reliability | 7/10 | Retry decorator, MultiIndex handling, yfinance limit clamping. But no NaN check on final price, no data freshness validation. |
| Broker integration robustness | 6/10 | Bracket orders, position liquidation, graceful error handling on most API calls. But `submit_buy()` has no try/except, order pagination broken, no pending-order dedup. |
| Metrics accuracy | 2/10 | PnL calculation fundamentally broken (market orders have price=0). Total trades capped at 50. Slippage measurement excludes market orders. Profit factor values meaningless. |
| Code maintainability | 8/10 | Excellent documentation, clean separation of concerns, consistent logging, self-test scripts for every module. |
| **Overall production readiness** | **4/10** | The infrastructure is solid but the metrics are unreliable, the strategy has negative expectancy, and critical vulnerabilities must be fixed before any production deployment. |

---

## SECTION 11: Prioritized Fix List

```
[Priority #1] — CRITICAL
Issue: Alpaca API keys hardcoded as plaintext fallbacks in config.py
Root cause: config.py:L86-87 — keys are string literals in tracked source code
Fix: Remove hardcoded key values entirely. Use only os.getenv() with no fallback.
     Add startup validation that raises if env vars are unset.
Estimated effort: 30min
Blocks: Any public repository sharing, security compliance

[Priority #2] — CRITICAL
Issue: PnL and trade metrics calculation is fundamentally broken for market orders
Root cause: analytics/metrics.py:L197-206 and broker/alpaca.py:L868 — market orders
     have price=0 (limit_price and stop_price are None), making pnl = fill_price - 0
Fix: Implement proper round-trip trade matching: pair each BUY fill with the
     subsequent SELL fill for the same ticker. PnL = sell_fill - buy_fill.
     Use filled_avg_price and filled_qty from Alpaca orders.
Estimated effort: 1 day
Blocks: All performance analysis, strategy evaluation, win rate accuracy

[Priority #3] — CRITICAL
Issue: No force-close timeout for bracket-held positions (zombie positions)
Root cause: alpaca.py:L298 — bracket orders use TimeInForce.GTC with no expiry.
     alpaca.py:L664 — bracket legs prevent manual SELL indefinitely.
Fix: Add EOD liquidation logic: before market close (e.g., 3:50 PM ET),
     cancel all open bracket legs and submit market SELL for all positions.
     Alternative: set bracket orders to TimeInForce.DAY instead of GTC.
Estimated effort: 2hr
Blocks: Capital recovery, portfolio cleanup

[Priority #4] — HIGH
Issue: Order deduplication missing — can submit duplicate BUY for same ticker
Root cause: alpaca.py:L610 — checks position=None but doesn't check pending orders
Fix: Before submitting BUY, query open orders for the ticker. If any pending
     BUY orders exist, skip. Add to run_tick() before submit_bracket_buy().
Estimated effort: 1hr
Blocks: Position sizing accuracy, capital allocation

[Priority #5] — HIGH
Issue: Circuit breaker state lost on process restart
Root cause: risk/manager.py:L89-94 — all state is in-memory, no persistence
Fix: Serialize circuit breaker state (daily_loss_breached, cooldown_until,
     stop_loss_count) to a JSON file. Load on startup. Clear at session start.
Estimated effort: 2hr
Blocks: Risk management reliability during server restarts

[Priority #6] — HIGH
Issue: _day_start_balance hardcoded to initial_balance, not actual broker equity
Root cause: risk/manager.py:L89 — set from config, never updated from broker
Fix: At session start in run_live(), fetch account equity from Alpaca and set
     rm._day_start_balance = account["equity"]. Call rm.reset_daily_state() too.
Estimated effort: 30min
Blocks: Daily loss circuit breaker accuracy (5% threshold is vs wrong baseline)

[Priority #7] — HIGH
Issue: Alpaca order history pagination capped at 50 orders
Root cause: alpaca.py:L849-853 — GetOrdersRequest without limit parameter
Fix: Add limit=500 to GetOrdersRequest. Implement pagination loop if >500.
Estimated effort: 30min
Blocks: Trade history completeness, metrics accuracy

[Priority #8] — HIGH
Issue: Session metrics duplicated from multiple process restarts
Root cause: main.py:L628-633 — append_session_stats runs in finally block on
     every process exit, including crashes and restarts.
Fix: Add session deduplication: before appending to CSV, check if a row with
     the same date already exists. Use session_date as unique key.
Estimated effort: 1hr
Blocks: Historical performance analysis accuracy

[Priority #9] — MEDIUM
Issue: SELL signal fires on single MACD-bearish condition (noise)
Root cause: signals.py:L281 — sell_triggered = sell_count >= 1
Fix: Raise threshold to sell_count >= 2 to require two confirming conditions.
Estimated effort: 30min
Blocks: Clean trade logging, reduced false sell triggers

[Priority #10] — MEDIUM
Issue: Portfolio heat bypass via sequential BUY submission
Root cause: alpaca.py:L601-608 — heat check uses stale position data within
     the same scan loop iteration
Fix: Track submitted-but-not-yet-filled order value locally. Add to
     long_exposure before the heat check for subsequent tickers.
Estimated effort: 1hr
Blocks: Portfolio heat cap reliability (60% cap can be breached)

[Priority #11] — MEDIUM
Issue: submit_buy() has no error handling — will crash on API error
Root cause: alpaca.py:L229 — no try/except around client.submit_order()
Fix: Wrap in try/except, log error, return empty dict.
Estimated effort: 15min
Blocks: Scan loop stability (crash stops all trading)

[Priority #12] — MEDIUM
Issue: NaN not checked in current_price extraction
Root cause: alpaca.py:L538 — float(df["Close"].iloc[-1]) with no NaN guard
Fix: Add: if pd.isna(current_price): return {"signal":"HOLD", ...}
Estimated effort: 15min
Blocks: Signal integrity under bad data conditions

[Priority #13] — MEDIUM
Issue: Sortino ratio uses incorrect downside deviation formula
Root cause: analytics/metrics.py:L157 — uses std of negative returns only
Fix: Compute downside deviation from all returns: replace positive returns
     with 0 (or risk-free rate), then take std of the full series.
Estimated effort: 30min
Blocks: Risk-adjusted return metric accuracy

[Priority #14] — MEDIUM
Issue: Slippage measurement excludes market orders (primary order type)
Root cause: analytics/metrics.py:L266-267 — filters out price==0 rows
Fix: For market orders, estimate slippage as |fill_price - last_close|.
     Requires storing the signal price at order submission time.
Estimated effort: 1hr
Blocks: Accurate transaction cost analysis

[Priority #15] — LOW
Issue: ML model trained on daily bars but applied to hourly signals
Root cause: ml/data_pipeline.py:L15 — INTERVAL="1d" for training data
Fix: Retrain model on hourly bar data. yfinance caps 1h at 730 days,
     so use rolling retraining or multiple fetch windows.
Estimated effort: 1 day
Blocks: ML filter effectiveness in live trading

[Priority #16] — LOW
Issue: reset_daily_state() never called in live mode
Root cause: main.py:run_live() — no call to rm.reset_daily_state()
Fix: Add rm.reset_daily_state() at the start of run_live(), after
     fetching initial account equity to set _day_start_balance.
Estimated effort: 15min
Blocks: Clean daily state after multi-day running

[Priority #17] — LOW
Issue: GPU indicator engine not integrated into live path
Root cause: main.py:run_live() calls add_all_indicators() (CPU) per ticker.
     gpu_indicators.py exists but is never imported in main.py.
Fix: If CuPy is available, batch-compute indicators for all 20 tickers
     via GPUIndicatorEngine.compute_batch_indicators().
Estimated effort: 2hr
Blocks: Performance optimization (not a correctness issue)

[Priority #18] — LOW
Issue: Hold filter uses .seconds instead of .total_seconds()
Root cause: alpaca.py:L675-676 — (.seconds / 60) resets to 0 after 24 hours
Fix: Use .total_seconds() / 60 for correct elapsed time calculation.
Estimated effort: 15min
Blocks: Hold filter accuracy for positions held >24 hours
```

---

*End of Audit Report*
