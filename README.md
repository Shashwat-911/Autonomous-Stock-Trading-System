# Autonomous Stock Trading & Quantitative Backtesting System

<!-- MEASUREMENT_V2_START -->
## Corrected account measurement

Mixed-version account history; **not a validated baseline for the current strategy**.
The earlier unverified session table is archived in docs/LEGACY_SESSION_TABLE.md.

Period: 2026-08-09 through 2026-11-27 (New York dates).
Source retrieved: 2026-11-28T04:07:08.913296+00:00. Report generated: 2026-11-28T04:07:23.756955+00:00.

Completed flat-to-flat episodes: **507**; gross win rate: **41.22%**.
Gross expectancy: **$-2.99**. Fees are unallocated account-level costs, excluded from trade metrics.

Latest account snapshot: **$98,455.71** at 2026-11-28T04:07:08.913296+00:00 (separate from daily history).

[Measurement definitions and limitations](docs/MEASUREMENT_V2.md)
<!-- MEASUREMENT_V2_END -->

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Alpaca API](https://img.shields.io/badge/broker-Alpaca%20Trading%20API-green.svg)](https://alpaca.markets/)
[![Render Service](https://img.shields.io/badge/Render-Live%20Service-46E3B7.svg?logo=render&logoColor=white)](https://autonomous-stock-trader.onrender.com/)
[![Live Logs](https://img.shields.io/badge/Render-Live%20Logs-informational.svg?logo=render&logoColor=white)](https://autonomous-stock-trader.onrender.com/logs)
[![GPU Accelerated](https://img.shields.io/badge/acceleration-NVIDIA%20CUDA%20%2F%20CuPy-76B900.svg)](https://cupy.dev/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An autonomous, production-grade algorithmic trading system and quantitative research framework built in Python. Designed for automated multi-asset equity trading, the system combines multi-timeframe technical indicator analysis, GPU-accelerated batch computations, dynamic ATR risk sizing, multi-tier circuit breakers, automated bracket order management (take-profit, stop-loss, and trailing stops), rolling walk-forward backtesting, and institutional-style quantitative performance metrics.

---

## Table of Contents

- [Live Cloud Deployment & Monitoring](#live-cloud-deployment--monitoring)
- [Live Paper Trading Performance](#live-paper-trading-performance)
- [System Architecture](#system-architecture)
- [Key Features](#key-features)
- [Quantitative Strategy & Signal Engine](#quantitative-strategy--signal-engine)
- [ML Meta-Labeling & Optimization Subsystem](#machine-learning-meta-labeling--optimization-subsystem)
- [Risk Management & Circuit Breakers](#risk-management--circuit-breakers)
- [Execution Layer](#execution-layer)
- [Performance Analytics & Metrics](#performance-analytics--metrics)
- [Walk-Forward Validation](#walk-forward-validation)
- [Project Directory Structure](#project-directory-structure)
- [Installation & Setup](#installation--setup)
- [Configuration Reference](#configuration-reference)
- [Usage & Execution Modes](#usage--execution-modes)
- [Outputs & Reporting](#outputs--reporting)
- [Disclaimer](#disclaimer)

---

## Live Cloud Deployment & Monitoring

Render is the sole live order executor. It polls Alpaca's exchange clock and starts the existing paper-trading strategy only while the exchange is open. GitHub Actions does not place orders or close positions; it sends scheduled health requests to wake Render and publishes the session log and reports after the market closes.

| Endpoint | Link | Description |
|---|---|---|
| **Live Web Service / Health** | [autonomous-stock-trader.onrender.com](https://autonomous-stock-trader.onrender.com/) | Real-time web server endpoint and operational status |
| **Runner Status** | [autonomous-stock-trader.onrender.com/status](https://autonomous-stock-trader.onrender.com/status) | Execution owner, broker clock state, and last session timestamps |
| **Live Streaming Logs** | [autonomous-stock-trader.onrender.com/logs](https://autonomous-stock-trader.onrender.com/logs) | Live real-time session execution and trade logs stream |

The runner uses the broker's live market clock for daylight-saving changes, holidays, and early closes. A trading session with no qualifying signal can correctly place no orders; automation does not force an entry. Render's free service can restart and has a monthly instance-hour limit, so this setup improves wake-up coverage but cannot guarantee uninterrupted service. See [Render's free-instance limits](https://render.com/docs/free).

---

## Live Paper Trading Performance

> **Paper Trading on Alpaca** | Started: Aug 11, 2026 | Initial Capital: $100,000.00 | Universe: NVDA, TSLA, META, MSFT, AAPL (5-Stock High-Momentum Universe)

![Daily P&L Chart](outputs/measurement_v2/generations/20261128T040708150901Z/daily_pnl_chart.png)

*Chart auto-generated from live Alpaca Portfolio History API and verified session telemetry via [`scripts/generate_pnl_chart.py`](scripts/generate_pnl_chart.py).*

### Daily Session Breakdown

<details>
<summary>View daily account history and session logs</summary>

Validated account measurements (mixed strategy versions). Realized P&L excludes fees and open-position P&L.

| Day | Date (New York) | Broker equity | Gross realized P&L | Cumulative gross realized | Equity change | Session log |
|---:|---|---:|---:|---:|---:|---|
| 1 | 2026-08-10 | $99,923.23 | $-18.12 | $-18.12 | $-76.77 | Not archived |
| 2 | 2026-08-11 | $99,551.43 | $-332.03 | $-350.15 | $-371.80 | Not archived |
| 3 | 2026-08-12 | $99,555.06 | $-11.39 | $-361.54 | $3.63 | Not archived |
| 4 | 2026-08-13 | $99,551.03 | $0.00 | $-361.54 | $-4.03 | Not archived |
| 5 | 2026-08-14 | $99,543.69 | $-21.02 | $-382.56 | $-7.34 | Not archived |
| 6 | 2026-08-17 | $99,515.93 | $-88.84 | $-471.40 | $-27.76 | Not archived |
| 7 | 2026-08-18 | $99,513.39 | $0.97 | $-470.43 | $-2.54 | Not archived |
| 8 | 2026-08-19 | $99,612.24 | $0.00 | $-470.43 | $98.85 | Not archived |
| 9 | 2026-08-20 | $99,506.06 | $0.00 | $-470.43 | $-106.18 | [Log](outputs/logs/session_2026_08_20.txt) |
| 10 | 2026-08-21 | $99,513.11 | $0.00 | $-470.43 | $7.05 | [Log](outputs/logs/session_2026_08_21.txt) |
| 11 | 2026-08-24 | $99,598.94 | $74.60 | $-395.83 | $85.83 | [Log](outputs/logs/session_2026_08_24.txt) |
| 12 | 2026-08-25 | $99,598.94 | $0.00 | $-395.83 | $0.00 | [Log](outputs/logs/session_2026_08_25.txt) |
| 13 | 2026-08-26 | $99,598.94 | $0.00 | $-395.83 | $0.00 | [Log](outputs/logs/session_2026_08_26.txt) |
| 14 | 2026-08-27 | $99,598.94 | $0.00 | $-395.83 | $0.00 | [Log](outputs/logs/session_2026_08_27.txt) |
| 15 | 2026-08-28 | $99,352.40 | $-246.11 | $-641.94 | $-246.54 | [Log](outputs/logs/session_2026_08_28.txt) |
| 16 | 2026-08-31 | $99,352.40 | $0.00 | $-641.94 | $0.00 | [Log](outputs/logs/session_2026_08_31.txt) |
| 17 | 2026-09-01 | $99,329.81 | $-22.36 | $-664.30 | $-22.59 | [Log](outputs/logs/session_2026_09_01.txt) |
| 18 | 2026-09-02 | $99,314.21 | $0.00 | $-664.30 | $-15.60 | [Log](outputs/logs/session_2026_09_02.txt) |
| 19 | 2026-09-03 | $99,491.97 | $0.00 | $-664.30 | $177.76 | [Log](outputs/logs/session_2026_09_03.txt) |
| 20 | 2026-09-04 | $99,576.01 | $0.00 | $-664.30 | $84.04 | [Log](outputs/logs/session_2026_09_04.txt) |
| 21 | 2026-09-08 | $99,524.99 | $180.56 | $-483.74 | $-51.02 | [Log](outputs/logs/session_2026_09_08.txt) |
| 22 | 2026-09-09 | $99,329.57 | $-177.39 | $-661.13 | $-195.42 | [Log](outputs/logs/session_2026_09_09.txt) |
| 23 | 2026-09-10 | $99,283.72 | $-75.71 | $-736.84 | $-45.85 | [Log](outputs/logs/session_2026_09_10.txt) |
| 24 | 2026-09-11 | $99,340.55 | $83.83 | $-653.01 | $56.83 | [Log](outputs/logs/session_2026_09_11.txt) |
| 25 | 2026-09-14 | $99,407.39 | $43.40 | $-609.61 | $66.84 | [Log](outputs/logs/session_2026_09_14.txt) |
| 26 | 2026-09-15 | $99,232.51 | $-139.76 | $-749.37 | $-174.88 | [Log](outputs/logs/session_2026_09_15.txt) |
| 27 | 2026-09-16 | $99,227.05 | $35.97 | $-713.40 | $-5.46 | [Log](outputs/logs/session_2026_09_16.txt) |
| 28 | 2026-09-17 | $99,355.76 | $100.34 | $-613.06 | $128.71 | [Log](outputs/logs/session_2026_09_17.txt) |
| 29 | 2026-09-18 | $99,368.13 | $-47.60 | $-660.66 | $12.37 | [Log](outputs/logs/session_2026_09_18.txt) |
| 30 | 2026-09-21 | $99,931.88 | $357.61 | $-303.05 | $563.75 | [Log](outputs/logs/session_2026_09_21.txt) |
| 31 | 2026-09-22 | $99,730.01 | $5.67 | $-297.38 | $-201.87 | [Log](outputs/logs/session_2026_09_22.txt) |
| 32 | 2026-09-23 | $99,637.15 | $-62.63 | $-360.01 | $-92.86 | [Log](outputs/logs/session_2026_09_23.txt) |
| 33 | 2026-09-24 | $99,752.52 | $114.78 | $-245.23 | $115.37 | [Log](outputs/logs/session_2026_09_24.txt) |
| 34 | 2026-09-25 | $99,671.92 | $-65.87 | $-311.10 | $-80.60 | [Log](outputs/logs/session_2026_09_25.txt) |
| 35 | 2026-09-28 | $99,659.89 | $0.00 | $-311.10 | $-12.03 | [Log](outputs/logs/session_2026_09_28.txt) |
| 36 | 2026-09-29 | $99,631.71 | $-46.27 | $-357.37 | $-28.18 | [Log](outputs/logs/session_2026_09_29.txt) |
| 37 | 2026-09-30 | $99,631.71 | $0.00 | $-357.37 | $0.00 | [Log](outputs/logs/session_2026_09_30.txt) |
| 38 | 2026-10-01 | $99,448.51 | $-182.31 | $-539.68 | $-183.20 | [Log](outputs/logs/session_2026_10_01.txt) |
| 39 | 2026-10-02 | $99,368.26 | $-79.55 | $-619.23 | $-80.25 | [Log](outputs/logs/session_2026_10_02.txt) |
| 40 | 2026-10-05 | $99,570.30 | $166.87 | $-452.36 | $202.04 | [Log](outputs/logs/session_2026_10_05.txt) |
| 41 | 2026-10-06 | $99,811.65 | $278.29 | $-174.07 | $241.35 | [Log](outputs/logs/session_2026_10_06.txt) |
| 42 | 2026-10-07 | $99,968.05 | $157.10 | $-16.97 | $156.40 | [Log](outputs/logs/session_2026_10_07.txt) |
| 43 | 2026-10-08 | $99,896.56 | $-71.02 | $-87.99 | $-71.49 | [Log](outputs/logs/session_2026_10_08.txt) |
| 44 | 2026-10-09 | $100,006.19 | $110.39 | $22.40 | $109.63 | [Log](outputs/logs/session_2026_10_09.txt) |
| 45 | 2026-10-12 | $100,015.93 | $0.00 | $22.40 | $9.74 | [Log](outputs/logs/session_2026_10_12.txt) |
| 46 | 2026-10-13 | $100,163.21 | $254.64 | $277.04 | $147.28 | [Log](outputs/logs/session_2026_10_13.txt) |
| 47 | 2026-10-14 | $99,939.87 | $-319.54 | $-42.50 | $-223.34 | [Log](outputs/logs/session_2026_10_14.txt) |
| 48 | 2026-10-15 | $99,865.37 | $-74.20 | $-116.70 | $-74.50 | [Log](outputs/logs/session_2026_10_15.txt) |
| 49 | 2026-10-16 | $99,612.27 | $-252.44 | $-369.14 | $-253.10 | [Log](outputs/logs/session_2026_10_16.txt) |
| 50 | 2026-10-19 | $99,671.00 | $59.21 | $-309.93 | $58.73 | [Log](outputs/logs/session_2026_10_19.txt) |
| 51 | 2026-10-20 | $99,724.53 | $53.84 | $-256.09 | $53.53 | [Log](outputs/logs/session_2026_10_20.txt) |
| 52 | 2026-10-21 | $99,747.20 | $-31.39 | $-287.48 | $22.67 | [Log](outputs/logs/session_2026_10_21.txt) |
| 53 | 2026-10-22 | $99,466.38 | $-226.11 | $-513.59 | $-280.82 | [Log](outputs/logs/session_2026_10_22.txt) |
| 54 | 2026-10-23 | $99,253.69 | $-212.09 | $-725.68 | $-212.69 | [Log](outputs/logs/session_2026_10_23.txt) |
| 55 | 2026-10-26 | $99,312.16 | $58.77 | $-666.91 | $58.47 | [Log](outputs/logs/session_2026_10_26.txt) |
| 56 | 2026-10-27 | $99,388.49 | $76.75 | $-590.16 | $76.33 | [Log](outputs/logs/session_2026_10_27.txt) |
| 57 | 2026-10-28 | $99,323.95 | $-63.95 | $-654.11 | $-64.54 | [Log](outputs/logs/session_2026_10_28.txt) |
| 58 | 2026-10-29 | $99,245.10 | $-78.43 | $-732.54 | $-78.85 | [Log](outputs/logs/session_2026_10_29.txt) |
| 59 | 2026-10-30 | $99,155.54 | $-89.14 | $-821.68 | $-89.56 | [Log](outputs/logs/session_2026_10_30.txt) |
| 60 | 2026-11-02 | $99,155.54 | $0.00 | $-821.68 | $0.00 | [Log](outputs/logs/session_2026_11_02.txt) |
| 61 | 2026-11-03 | $99,166.43 | $11.31 | $-810.37 | $10.89 | [Log](outputs/logs/session_2026_11_03.txt) |
| 62 | 2026-11-04 | $99,120.76 | $-44.96 | $-855.33 | $-45.67 | [Log](outputs/logs/session_2026_11_04.txt) |
| 63 | 2026-11-05 | $98,285.09 | $-834.58 | $-1,689.91 | $-835.67 | [Log](outputs/logs/session_2026_11_05.txt) |
| 64 | 2026-11-06 | $98,231.54 | $-53.43 | $-1,743.34 | $-53.55 | [Log](outputs/logs/session_2026_11_06.txt) |
| 65 | 2026-11-09 | $98,529.27 | $298.15 | $-1,445.19 | $297.73 | [Log](outputs/logs/session_2026_11_09.txt) |
| 66 | 2026-11-10 | $98,641.11 | $112.31 | $-1,332.88 | $111.84 | [Log](outputs/logs/session_2026_11_10.txt) |
| 67 | 2026-11-11 | $98,897.40 | $257.07 | $-1,075.81 | $256.29 | Not archived |
| 68 | 2026-11-12 | $98,869.71 | $-115.24 | $-1,191.05 | $-27.69 | [Log](outputs/logs/session_2026_11_12.txt) |
| 69 | 2026-11-13 | $99,003.88 | $222.68 | $-968.37 | $134.17 | [Log](outputs/logs/session_2026_11_13.txt) |
| 70 | 2026-11-16 | $98,865.09 | $-138.44 | $-1,106.81 | $-138.79 | [Log](outputs/logs/session_2026_11_16.txt) |
| 71 | 2026-11-17 | $98,865.09 | $0.00 | $-1,106.81 | $0.00 | [Log](outputs/logs/session_2026_11_17.txt) |
| 72 | 2026-11-18 | $98,871.12 | $-123.38 | $-1,230.19 | $6.03 | [Log](outputs/logs/session_2026_11_18.txt) |
| 73 | 2026-11-19 | $98,455.71 | $-285.30 | $-1,515.49 | $-415.41 | [Log](outputs/logs/session_2026_11_19.txt) |
| 74 | 2026-11-20 | $98,455.71 | $0.00 | $-1,515.49 | $0.00 | [Log](outputs/logs/session_2026_11_20.txt) |
| 75 | 2026-11-23 | $98,455.71 | $0.00 | $-1,515.49 | $0.00 | Not archived |
| 76 | 2026-11-24 | $98,455.71 | $0.00 | $-1,515.49 | $0.00 | [Log](outputs/logs/session_2026_11_24.txt) |
| 77 | 2026-11-25 | $98,455.71 | $0.00 | $-1,515.49 | $0.00 | [Log](outputs/logs/session_2026_11_25.txt) |
| 78 | 2026-11-27 | $98,455.71 | $0.00 | $-1,515.49 | $0.00 | [Log](outputs/logs/session_2026_11_27.txt) |

[Archived legacy table — unverified](docs/LEGACY_SESSION_TABLE.md). Missing equity is never estimated from the current account snapshot.

</details>

---

## System Architecture

```mermaid
flowchart TD
    subgraph Ingestion ["Data Ingestion & Feed Layer"]
        A1[Yahoo Finance API / yfinance] --> B[Data Fetcher & Cleaner]
        A2[Alpaca Markets Live Feed] --> B
    end

    subgraph IndicatorEngine ["Technical Indicator Engine"]
        B --> C1[CPU Vectorized Engine - Pandas / NumPy]
        B --> C2[GPU CUDA Engine - CuPy Parallel Matrix]
    end

    subgraph SignalAndRisk ["Strategy & Pre-Trade Risk Gate"]
        C1 & C2 --> D[Multi-Timeframe Signal Generator]
        SPY[Market Regime Filter - SPY 200-SMA] --> D
        D --> E{Pre-Trade Risk Gate - RiskManager}
        E -- "Pass: Within Risk Limits" --> F[Order Routing & Sizing Engine]
        E -- "Reject: Circuit Breaker Active" --> G[Trading Halted / Cooldown]
    end

    subgraph Execution ["Broker & Execution Layer"]
        F --> H1[Local Paper Broker - SQLite Persistence]
        F --> H2[Alpaca API Paper Broker - Bracket Orders]
    end

    subgraph AnalyticsReporting ["Analytics, Reporting & Monitoring"]
        H1 & H2 --> I[PerformanceEngine - Sharpe, Sortino, Drawdown, Slippage]
        I --> J1[outputs/performance_summary.json]
        I --> J2[outputs/portfolio_trading_results.xlsx Multi-Tab]
        I --> J3[outputs/trade_history.csv]
    end
```

---

## Key Features

- **Multi-Timeframe Signal Analysis**: Blends intraday price bars (5m/1h) with daily trend filters and broad-market regime filters (SPY 200-day Simple Moving Average).
- **GPU-Accelerated Indicator Engine**: Computes technical indicators across multi-ticker matrices concurrently using NVIDIA CUDA via CuPy, with automatic CPU NumPy/Pandas fallback.
- **Dynamic ATR Position Sizing**: Automatically adjusts position size per trade based on current asset volatility (Average True Range), equity percentage limits, and absolute dollar caps.
- **Institutional Pre-Trade Risk Management**:
  - Daily portfolio loss circuit breaker (e.g., maximum 5% daily drawdown).
  - Per-trade stop-loss triggers with automated cooldown timers (e.g., 15–30 minutes).
  - Portfolio heat limit (e.g., maximum 60% total long equity exposure).
- **Automated Bracket & Trailing Orders**: Employs Alpaca bracket orders with ATR-calibrated stop-loss and take-profit targets (2:1 reward-to-risk ratio) and dynamic trailing stop escalation.
- **Walk-Forward Validation Engine**: Evaluates out-of-sample performance over rolling train/test windows (e.g., 6 months train, 3 months test) to eliminate look-ahead bias and curve-fitting.
- **Institutional Analytics Engine**: Computes annualized Sharpe ratio, Sortino ratio, max drawdown and duration, win rate, trade expectancy, profit factor, execution latency (ms), and fill slippage (%).
- **Multi-Tab Excel Dashboard Exporter**: Live-generates `portfolio_trading_results.xlsx` featuring a master portfolio overview tab and individual ticker log sheets.

---

## Quantitative Strategy & Signal Engine

The trading engine evaluates technical indicators across price windows using rigorous mathematical formulations:

### 1. Indicators Calculated
- **Simple Moving Average (SMA)**: Rolling arithmetic mean over $n$ periods (default $n=20$ and $n=200$).
- **Exponential Moving Average (EMA)**: Exponentially weighted moving average with smoothing factor $\alpha = \frac{2}{n + 1}$.
- **Relative Strength Index (RSI)**: Calculated using **Wilder's exponential smoothing method** over 14 periods:
  $$\text{RSI} = 100 - \left(\frac{100}{1 + \frac{\text{EMA}(\text{Gain}, 14)}{\text{EMA}(\text{Loss}, 14)}}\right)$$
- **Moving Average Convergence Divergence (MACD)**: Fast EMA (12) minus Slow EMA (26), evaluated against a 9-period Signal EMA line and Histogram.
- **Bollinger Bands**: 20-period baseline with $\pm 2.0$ rolling standard deviations.
- **Average True Range (ATR)**: 14-period smoothed true range reflecting actual market volatility:
  $$\text{TR} = \max\Big(\text{High} - \text{Low}, |\text{High} - \text{Close}_{\text{prev}}|, |\text{Low} - \text{Close}_{\text{prev}}|\Big)$$

### 2. Signal Generation Matrix (Dual-Path Entry)

| Signal | Conditions Evaluated | Confirmation / Weight |
|---|---|---|
| **BUY (Path 1: Dip Entry)** | 1. RSI oversold ($< 45.0$)<br>2. MACD Bullish ($\text{MACD} > \text{Signal}$)<br>3. Price above 20-period SMA ($\text{Close} > \text{SMA}_{20}$)<br>4. Price above lower Bollinger Band ($\text{Close} > \text{BB}_{\text{Lower}}$) | Requires $\ge 75\%$ confidence (3 of 4 conditions met) + SPY above 200-SMA |
| **BUY (Path 2: Momentum)** | 1. MACD Bullish Crossover ($\text{MACD}_{\text{now}} > \text{Signal}_{\text{now}}$ and $\text{MACD}_{\text{prev}} \le \text{Signal}_{\text{prev}}$)<br>2. Price above 20-period SMA ($\text{Close} > \text{SMA}_{20}$)<br>3. RSI between 45.0 and 65.0 | High-conviction momentum entry (catches post-earnings pumps) + SPY above 200-SMA |
| **SELL** | 1. RSI overbought ($> 70.0$)<br>2. MACD Bearish crossover ($\text{MACD} < \text{Signal}$)<br>3. Price breaks below lower Bollinger Band ($\text{Close} < \text{BB}_{\text{Lower}}$)<br>4. Risk manager circuit breaker or stop-loss trigger ($-4.0\%$) | Liquidates open position immediately |
| **HOLD** | Insufficient confirmation or risk blocks active | No action |

### Strategy Evolution Log

| Phase | Dates | Change | Reason |
|---|---|---|---|
| Week 1 | Aug 11–15 | RSI dip-buying, strict (RSI < 30, all 4 confirm) | Baseline validation |
| Week 2 | Aug 18–26 | Simplified + cleanup, require_confirmation=False | Too strict, 0 clean trades |
| Week 3 (Aug 27) | Aug 27–28 | Dual-path: Dip + MACD Momentum crossover | Catch post-earnings moves |
| Week 3 (Aug 28) | Aug 28 | Position size $2k → $5k | Returns too small |
| Week 4 | Sep 1+ | 60-min minimum hold filter added | Whipsaw on Aug 28 caused 2 losing trades in 30 mins |
| Week 5 | Sep 2 | RSI oversold threshold raised 40 → 45 | Sep 1 NVDA dip at RSI ~47 missed entry; wider window needed |
| Week 5 (Sep 2) | Sep 2 | High-conviction BUY (44 shares NVDA @ $224.74) | Momentum crossover confirmed with multi-timeframe filter |
| Week 7 | Sep 17 | LightGBM Meta-Labeling + Bayesian Opt + 20 Tickers | Filters false positives (P >= 0.65), lifts Sharpe 1.38 → 2.02, diversifies universe |

> Every change above was driven by real live trading data, 
> not theory. Whipsaw behavior detected Aug 28 — 
> momentum crossover on daily candles is unstable at 
> 15-minute scan intervals without a minimum hold period.

---

## Machine Learning Meta-Labeling & Optimization Subsystem

The repository contains an experimental LightGBM meta-labeling subsystem, documented in [`docs/ML_ARCHITECTURE.md`](docs/ML_ARCHITECTURE.md). **It is disabled in the live signal path** (`_META_AVAILABLE = False` in `strategy/signals.py`), so it does not approve or reject current live trades. The main-branch GitHub Actions workflow is now limited to wake checks and post-session reporting; it does not retrain or promote models. Historical optimizer metrics in this section of the project are research outputs, not evidence of live profitability.

---

## Risk Management & Circuit Breakers

The system enforces strict pre-trade rules via the `RiskManager` module:

### Dynamic ATR Position Sizing Formula
$$\text{Shares} = \left\lfloor \frac{\text{Equity} \times \text{RiskPctPerTrade}}{\text{ATR} \times k} \right\rfloor$$
*Capped by:* $\min(\text{MaxPositionDollars}, \text{Equity} \times \text{MaxPositionPct})$

### Risk Controls Summary
- **Daily Loss Circuit Breaker**: If total portfolio equity drops by more than `max_daily_loss_pct` (e.g., 5%) from the start-of-day balance, all trading is halted for the rest of the day.
- **Per-Trade Stop-Loss & Cooldown**: If an open trade drops below `max_trade_loss_pct` (e.g., 4%), the position is liquidated and a cooldown timer (e.g., 15 minutes) prevents immediate re-entry.
- **Portfolio Heat Filter**: Total market value of all long positions cannot exceed `max_portfolio_heat_pct` (e.g., 60% of equity).
- **Market Regime Gate**: If the benchmark ETF (SPY) trades below its 200-day moving average, all BUY signals are blocked.

---

## Execution Layer

### 1. Live Alpaca Paper Broker (`broker/alpaca.py`)
- Official integration with `alpaca-py`.
- Submits **Bracket Orders** combining Entry, Take-Profit ($+3.0 \times \text{ATR}$), and Stop-Loss ($-1.5 \times \text{ATR}$).
- Implements trailing stop-loss management once the asset achieves $+1.5 \times \text{ATR}$ gain.
- Verifies market clock status and tracks live buying power, cash, equity, and order fills.

### 2. Local Paper Broker (`broker/paper.py`)
- Self-contained, zero-dependency paper broker.
- Persists all executions, timestamps, prices, quantities, cash balances, and realized PnL in a local SQLite database (`trades.db`).
- Supports in-memory simulation (`:memory:`) for rapid backtesting.

---

## Performance Analytics & Metrics

The `PerformanceEngine` in `analytics/metrics.py` evaluates trading performance across both trade histories and equity curves:

| Metric | Formula / Description |
|---|---|
| **Sharpe Ratio** | Annualized risk-adjusted return relative to risk-free rate ($R_f = 4\%$):<br>$$\text{Sharpe} = \frac{\bar{R} - R_f}{\sigma_R} \times \sqrt{252}$$ |
| **Sortino Ratio** | Annualized return penalizing downside deviation only:<br>$$\text{Sortino} = \frac{\bar{R} - R_f}{\sigma_{\text{downside}}} \times \sqrt{252}$$ |
| **Max Drawdown (MDD)** | Peak-to-trough maximum percentage drop of the equity curve along with consecutive duration periods. |
| **Expectancy ($E$)** | Average dollar expected per trade:<br>$$E = (\text{WinRate} \times \text{AvgGain}) - ((1 - \text{WinRate}) \times |\text{AvgLoss}|)$$ |
| **Profit Factor** | Ratio of gross profits to gross losses: $\frac{\sum \text{Gains}}{\sum |\text{Losses}|}$. |
| **Order Slippage (%)** | Difference between signal price and filled average price: $\left|\frac{\text{FillPrice} - \text{SignalPrice}}{\text{SignalPrice}}\right| \times 100$. |
| **Execution Latency (ms)** | Time elapsed between order submission and order fill confirmation in milliseconds. |

---

## Walk-Forward Validation

To prevent statistical overfitting and curve-fitting, the `WalkForwardBacktester` (`backtest/walk_forward.py`) implements a rolling walk-forward framework:

```
Full History: [============================================================]
Window 1:     [--- Train (6mo) ---][ Test (3mo) ]
Window 2:             [--- Train (6mo) ---][ Test (3mo) ]
Window 3:                     [--- Train (6mo) ---][ Test (3mo) ]
```

- Each test window is preceded by a warmup period to prime indicator states.
- Generates a **Consistency Score** (% of profitable out-of-sample windows), average return per window, best/worst window returns, and worst-case drawdown.

---

## Project Directory Structure

```
Autonomous-Stock-Trading-System/
├── analytics/
│   ├── __init__.py
│   └── metrics.py                  # Quantitative performance engine (Sharpe, Sortino, MDD, Expectancy)
├── backtest/
│   ├── __init__.py
│   └── walk_forward.py             # Rolling walk-forward backtesting framework
├── broker/
│   ├── __init__.py
│   ├── alpaca.py                   # Live Alpaca Markets paper broker (bracket orders, clock, positions)
│   └── paper.py                    # Local paper broker with SQLite persistence
├── data/
│   ├── __init__.py
│   ├── excel_exporter.py           # Multi-tab Excel workbook generator (openpyxl)
│   └── fetcher.py                  # Robust market data fetcher with exponential backoff retries
├── outputs/
│   ├── alpaca_equity_history.csv   # Historical daily equity and P&L dataset from Alpaca API
│   ├── backtest_results.csv        # Historical backtest trade records
│   ├── daily_pnl_chart.png         # Dual-panel daily P&L equity curve and bar chart
│   ├── logs/                       # Date-stamped live session log archives
│   ├── paper_results.csv           # Local paper trading trade records
│   ├── performance_summary.json    # JSON report of quantitative performance metrics
│   ├── portfolio_trading_results.xlsx # Multi-tab Excel workbook (master summary + ticker sheets)
│   ├── project_status.py           # Quick CLI status overview & diagnostic tool
│   ├── session_all_orders.csv      # Detailed log of all Alpaca orders
│   ├── trade_history.csv           # Aggregate session metrics
│   └── walkforward_results.csv     # Per-window walk-forward validation results
├── risk/
│   ├── __init__.py
│   └── manager.py                  # Pre-trade circuit breaker, ATR position sizing, cooldowns
├── scripts/
│   ├── cleanup_positions.py        # Utility to cancel pending orders and liquidate non-monitored tickers
│   ├── diag_orders.py              # Diagnostic inspector for order legs (TP/SL) and fills
│   ├── fetch_alpaca_equity.py      # Direct Alpaca Portfolio History API fetcher
│   ├── generate_pnl_chart.py       # High-resolution dark-mode daily P&L chart generator
│   ├── generate_session_report.py  # Generates end-of-session performance summary from Alpaca
│   ├── run_live_logger.py          # Process wrapper for background live logging
│   └── session_analysis.py         # Multi-session trend assessment and ASCII equity curve
├── strategy/
│   ├── __init__.py
│   ├── gpu_indicators.py           # CUDA CuPy-accelerated technical indicator matrix engine
│   ├── indicators.py               # Vectorized indicator calculations (SMA, EMA, RSI, MACD, BB, ATR)
│   └── signals.py                  # Multi-indicator signal generator with risk gating
├── .env.example                    # Environment variable configuration template
├── .gitignore                      # Git ignore patterns
├── config.py                       # Centralized configuration source of truth
├── main.py                         # Master entry point CLI
├── README.md                       # Comprehensive system documentation
└── requirements.txt                # Python package dependencies
```

---

## Installation & Setup

### 1. Prerequisites
- Python **3.10+** (Python 3.11 or 3.12 recommended)
- Git
- (Optional) NVIDIA GPU with CUDA Toolkit installed if using GPU indicator acceleration.

### 2. Clone the Repository
```bash
git clone https://github.com/Shashwat-911/Autonomous-Stock-Trading-System.git
cd Autonomous-Stock-Trading-System
```

### 3. Create and Activate a Virtual Environment
- **Windows (PowerShell):**
  ```powershell
  python -m venv venv
  .\venv\Scripts\Activate.ps1
  ```
- **macOS / Linux:**
  ```bash
  python3 -m venv venv
  source venv/bin/activate
  ```

### 4. Install Dependencies
```bash
pip install -r requirements.txt
```

*(Optional GPU Support)* If you have an NVIDIA GPU and CUDA 12.x installed:
```bash
pip install cupy-cuda12x
```

### 5. Configure API Credentials
Create a `.env` file in the root directory (or copy from `.env.example`):
```bash
cp .env.example .env
```
Edit `.env` with your Alpaca Paper Trading API keys:
```ini
ALPACA_API_KEY=your_alpaca_api_key_here
ALPACA_SECRET_KEY=your_alpaca_secret_key_here
ALPACA_BASE_URL=https://paper-api.alpaca.markets
ALPACA_FEED=iex
```

---

## Configuration Reference

All settings can be customized in `config.py`:

```python
# Trading & Universe Settings
TRADING = {
    "ticker": "NVDA",                                  # Primary asset / default fallback
    "tickers": ["NVDA", "TSLA", "META", "MSFT", "AAPL"], # 5-stock high-momentum universe
    "interval": "1h",                                  # Bar interval for live monitoring
    "interval_daily": "1d",                            # Daily bar interval for multi-timeframe check
    "initial_balance": 100000.0,                       # Starting capital ($)
    "min_confidence": 0.75,                            # Minimum confidence score for BUY execution
    "lookback_days": 60,                               # Historical lookback (days)
    "lookback_days_intraday": 30,                      # 5-minute lookback (days)
}

# Signal Parameters
SIGNAL = {
    "rsi_oversold": 45.0,                              # RSI threshold for oversold dip entry
    "rsi_overbought": 65.0,                            # RSI threshold for overbought exit
    "require_confirmation": False,                     # Requires >= 75% indicator consensus
}

# Pre-Trade Risk Limits
RISK = {
    "max_daily_loss_pct": 0.05,                        # 5% max portfolio daily drawdown
    "max_trade_loss_pct": 0.04,                        # 4% per-trade stop-loss
    "max_position_pct": 0.10,                          # 10% max portfolio allocation per asset
    "max_position_dollars": 5000.0,                    # $5,000 hard dollar cap per position
    "cooldown_minutes": 15,                            # Cooldown after stop-loss event
    "max_portfolio_heat_pct": 0.60,                    # Max 60% of equity in long positions
    "atr_period": 14,                                  # ATR smoothing window
    "atr_multiplier_k": 2.0,                           # ATR sizing divisor
    "risk_pct_per_trade": 0.01,                        # Risk 1% of total equity per trade
}

# Bracket Order Configuration
BRACKET = {
    "stop_loss_atr_mult": 2.5,                         # Stop-loss at entry - 2.5×ATR
    "take_profit_atr_mult": 2.0,                       # Take-profit at entry + 2.0×ATR
    "trailing_activation_atr": 1.0,                    # Activate trailing stop after +1.0×ATR gain
    "trailing_stop_atr_mult": 1.0,                     # Trailing stop distance once active
}

# Broad Market Regime Filter
MARKET_REGIME = {
    "ticker": "SPY",                                   # Market benchmark
    "sma_period": 200,                                 # 200-day simple moving average
}
```

---

## Usage & Execution Modes

The master entry point is `main.py`. Choose from several execution modes:

### 1. Historical Backtest Mode
Simulates the strategy over a historical date range and outputs full trade logs and summary metrics:
```bash
python main.py backtest
```

### 2. Walk-Forward Backtest Mode
Runs rolling walk-forward out-of-sample validation to measure strategy consistency:
```bash
python main.py walkforward
```

### 3. Local Paper Trading Mode
Runs a local, self-contained real-time paper trading loop with SQLite trade recording:
```bash
python main.py paper
```

### 4. Live Alpaca Paper Trading Mode
Connects directly to your Alpaca paper account to execute real-time multi-ticker scans, submit bracket orders, and manage positions:
```bash
python main.py live
```

### 5. View Logs & Diagnostics
- **Live Stream Logs (Cloud):** [autonomous-stock-trader.onrender.com/logs](https://autonomous-stock-trader.onrender.com/logs)
- **Live Service Endpoint (Cloud):** [autonomous-stock-trader.onrender.com](https://autonomous-stock-trader.onrender.com/)
- **Local Logs CLI:**
  ```bash
  python main.py logs
  ```
- **Project Diagnostics & Alpaca Status:**
  ```bash
  python outputs/project_status.py
  ```

### 6. Utility Scripts
- **Generate Daily P&L Performance Chart:**
  ```bash
  python scripts/generate_pnl_chart.py
  ```
- **Generate End-of-Session Performance Report:**
  ```bash
  python scripts/generate_session_report.py
  ```
- **Multi-Session Strategy Trend Analysis & ASCII Equity Curve:**
  ```bash
  python scripts/session_analysis.py
  ```
- **Inspect Order Legs, TP/SL Brackets & Execution Types:**
  ```bash
  python scripts/diag_orders.py
  ```
- **Fetch Raw Alpaca Portfolio History Snapshots:**
  ```bash
  python scripts/fetch_alpaca_equity.py
  ```
- **Cleanup / Liquidate Orphaned Positions & Cancel Pending Orders:**
  ```bash
  python scripts/cleanup_positions.py
  ```

---

## Outputs & Reporting

All results and runtime artifacts are written to the `outputs/` directory:

- **`outputs/daily_pnl_chart.png`**: High-resolution dark-mode performance chart with cumulative equity curve and daily P&L bars.
- **`outputs/alpaca_equity_history.csv`**: Daily equity snapshots and profit/loss history directly synced from Alpaca Portfolio API.
- **`outputs/performance_summary.json`**: Machine-readable JSON summary of quantitative session metrics (Sharpe ratio, Sortino ratio, max drawdown, win rate, expectancy, profit factor, latency, slippage).
- **`outputs/logs/`**: Archive of date-stamped live session execution logs (e.g. `session_YYYY_MM_DD.txt`).
- **`outputs/portfolio_trading_results.xlsx`**: Multi-tab Excel workbook featuring:
  - *Portfolio Summary Tab*: Real-time overview of all monitored assets, active positions, unrealized P&L, and latest signals.
  - *Individual Ticker Tabs*: Tick-by-tick indicator states, prices, and execution history.
- **`outputs/backtest_results.csv`**: Record of all simulated trades from historical backtests.
- **`outputs/walkforward_results.csv`**: Window-by-window performance breakdown from walk-forward testing.
- **`outputs/trade_history.csv`**: Cumulative session statistics table.

---

## Disclaimer

This software is for educational, research, and paper-trading purposes only. Quantitative trading in financial markets involves substantial risk of loss. Past performance, backtest results, and simulated trading do not guarantee future returns. Always test strategies extensively in paper-trading environments before risking actual capital.

---

## License

This project is licensed under the [MIT License](LICENSE).
