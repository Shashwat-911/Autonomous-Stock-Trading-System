"""
main.py -- Entry point for the quantitative trading bot.

Usage:
    python main.py backtest      Run a historical backtest
    python main.py paper         Run live paper trading (Ctrl+C to stop)
    python main.py walkforward   Run walk-forward validation
    python main.py live          Run live Alpaca paper trading
    python main.py               Defaults to backtest
"""

import warnings
warnings.filterwarnings("ignore", message="CUDA path could not be detected")

import logging
import os
import sys
import time
from datetime import date, datetime, timedelta

import pandas as pd

# ---------------------------------------------------------------------------
# Project imports
# ---------------------------------------------------------------------------
import config
from data.fetcher import (
    get_historical_data, get_batch_historical_data, get_latest_price,
    get_intraday_data, get_market_regime_data, get_latest_bar,
)
from strategy.indicators import add_all_indicators
from strategy.signals import SignalGenerator
from risk.manager import RiskManager
from broker.paper import LocalPaperBroker
from backtest.walk_forward import WalkForwardBacktester
from analytics.metrics import PerformanceEngine

# ---------------------------------------------------------------------------
# Logging (module-level, for errors and diagnostics only)
# ---------------------------------------------------------------------------
logger = logging.getLogger("main")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUTS_DIR = os.path.join(PROJECT_ROOT, "outputs")


# ======================================================================
# Component factory -- builds every object from config.py
# ======================================================================

def build_components(db_path: str = None) -> tuple:
    """
    Construct RiskManager, SignalGenerator, and LocalPaperBroker
    from the central ``config`` module.

    Parameters
    ----------
    db_path : str or None
        Override for the SQLite database file path.

    Returns
    -------
    tuple
        (risk_manager, signal_generator, broker)
    """
    rm = RiskManager(
        initial_balance=config.TRADING["initial_balance"],
        max_daily_loss_pct=config.RISK["max_daily_loss_pct"],
        max_trade_loss_pct=config.RISK["max_trade_loss_pct"],
        max_position_pct=config.RISK["max_position_pct"],
        cooldown_minutes=config.RISK["cooldown_minutes"],
    )

    sg = SignalGenerator(
        risk_manager=rm,
        rsi_oversold=config.SIGNAL["rsi_oversold"],
        rsi_overbought=config.SIGNAL["rsi_overbought"],
        require_confirmation=config.SIGNAL["require_confirmation"],
    )

    broker = LocalPaperBroker(
        initial_balance=config.TRADING["initial_balance"],
        ticker=config.TRADING["ticker"],
        risk_manager=rm,
        signal_generator=sg,
        min_confidence=config.TRADING["min_confidence"],
        db_path=db_path,
    )

    return rm, sg, broker


# ======================================================================
# BACKTEST MODE
# ======================================================================

def run_backtest() -> None:
    """
    Execute a full historical backtest using dates from ``config.BACKTEST``
    and save results to ``outputs/backtest_results.csv``.
    """
    ticker = config.TRADING["ticker"]
    start = config.BACKTEST["start_date"]
    end = config.BACKTEST["end_date"]

    print("=" * 72)
    print("  BACKTEST MODE")
    print("=" * 72)
    print(f"  Ticker:    {ticker}")
    print(f"  Period:    {start}  ->  {end}")
    print(f"  Interval:  {config.TRADING['interval']}")
    print(f"  Balance:   {config.TRADING['initial_balance']:.2f}")
    print("=" * 72)

    # ---- 1. Fetch data ----
    print("\n[1/5] Fetching historical data...")
    raw_df = get_historical_data(
        ticker, start, end, interval=config.TRADING["interval"]
    )
    print(f"      Rows fetched: {len(raw_df)}")

    # ---- 2. Indicators ----
    print("[2/5] Computing technical indicators...")
    df = add_all_indicators(raw_df)

    # ---- 3. Build components (use a dedicated backtest DB) ----
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    bt_db = os.path.join(OUTPUTS_DIR, "backtest_trades.db")
    if os.path.exists(bt_db):
        os.remove(bt_db)

    rm, sg, broker = build_components(db_path=bt_db)

    # ---- 4. Simulate ----
    print(f"[3/5] Running backtest over {len(df)} bars...\n")

    n = len(df)
    header = (
        f"{'Bar':>5}  {'Date':>12}  {'Close':>10}  {'Action':>18}  "
        f"{'Shares':>7}  {'Cash':>10}  {'Portfolio':>10}"
    )
    print(header)
    print("-" * len(header))

    for i in range(n):
        window = df.iloc[: i + 1]
        result = broker.run_tick(window)

        # Print progress every bar (compact line)
        print(
            f"{i + 1:>5}  "
            f"{str(result['timestamp'])[:10]:>12}  "
            f"{result['price']:>10.2f}  "
            f"{result['action']:>18}  "
            f"{result['shares']:>7}  "
            f"{result['cash']:>10.2f}  "
            f"{result['portfolio_value']:>10.2f}"
        )

    # ---- 5. Results ----
    print(f"\n{'=' * 72}")
    print("  TRADE HISTORY")
    print(f"{'=' * 72}")

    history = broker.get_trade_history()
    if history.empty:
        print("  No trades were executed during the backtest.")
    else:
        display_cols = [
            "timestamp", "action", "ticker", "price",
            "quantity", "cash_after", "pnl", "reason",
        ]
        hist_display = history[display_cols].copy()
        hist_display["reason"] = hist_display["reason"].str[:55]
        print(hist_display.to_string(index=False))

    # Save CSV
    csv_path = os.path.join(OUTPUTS_DIR, "backtest_results.csv")
    history.to_csv(csv_path, index=False)
    print(f"\n  Trade history saved to: {csv_path}")

    # Performance summary
    last_price = float(df.iloc[-1]["Close"])
    summary = broker.get_performance_summary(current_price=last_price)

    print(f"\n{'=' * 72}")
    print("  PERFORMANCE SUMMARY")
    print(f"{'=' * 72}")
    for k, v in summary.items():
        label = k.replace("_", " ").title()
        if "pct" in k.lower():
            print(f"  {label}: {v}%")
        elif isinstance(v, float):
            print(f"  {label}: {v:.2f}")
        else:
            print(f"  {label}: {v}")
    print(f"{'=' * 72}\n")

    # Clean up backtest DB
    if os.path.exists(bt_db):
        os.remove(bt_db)


# ======================================================================
# PAPER TRADING MODE
# ======================================================================

def run_paper() -> None:
    """
    Run a live paper-trading loop that polls market data every 60
    seconds and executes trades through ``LocalPaperBroker``.

    Press **Ctrl+C** to stop gracefully.
    """
    ticker = config.TRADING["ticker"]
    lookback = config.TRADING["lookback_days"]
    interval = config.TRADING["interval"]

    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    paper_db = os.path.join(OUTPUTS_DIR, "paper_trades.db")

    rm, sg, broker = build_components(db_path=paper_db)

    print("=" * 72)
    print("  PAPER TRADING MODE")
    print("=" * 72)
    print(f"  Ticker:    {ticker}")
    print(f"  Balance:   {config.TRADING['initial_balance']:.2f}")
    print(f"  Lookback:  {lookback} days")
    print(f"  Interval:  {interval}")
    print(f"  DB:        {paper_db}")
    print("=" * 72)
    print("\n  Paper trading started. Press Ctrl+C to stop.\n")

    tick_count = 0

    try:
        while True:
            tick_count += 1
            try:
                # (a) Fetch recent history
                end_date = date.today()
                start_date = end_date - timedelta(days=lookback)
                raw_df = get_historical_data(
                    ticker, str(start_date), str(end_date), interval=interval
                )

                # (b) Compute indicators
                df = add_all_indicators(raw_df)

                # (c) Run one tick
                result = broker.run_tick(df)

                # (d) Print status line
                now_str = datetime.now().strftime("%H:%M:%S")
                action = result["action"]
                price = result["price"]
                portfolio = result["portfolio_value"]
                shares = result["shares"]

                print(
                    f"  [{now_str}] {ticker} | "
                    f"Price: ${price:.2f} | "
                    f"Portfolio: ${portfolio:.2f} | "
                    f"Shares: {shares} | "
                    f"Signal: {action}"
                )

            except Exception as e:
                logger.error("Error during tick %d: %s", tick_count, e)
                print(f"  [ERROR] Tick {tick_count} failed: {e}")

            # (e) Sleep
            time.sleep(60)

    except KeyboardInterrupt:
        print("\n\n  Ctrl+C received -- shutting down gracefully.\n")

    # Final summary on exit
    try:
        last_price = get_latest_price(ticker)
    except Exception:
        last_price = None

    summary = broker.get_performance_summary(current_price=last_price)

    print(f"{'=' * 72}")
    print("  FINAL PERFORMANCE SUMMARY")
    print(f"{'=' * 72}")
    for k, v in summary.items():
        label = k.replace("_", " ").title()
        if "pct" in k.lower():
            print(f"  {label}: {v}%")
        elif isinstance(v, float):
            print(f"  {label}: {v:.2f}")
        else:
            print(f"  {label}: {v}")

    history = broker.get_trade_history()
    if not history.empty:
        csv_path = os.path.join(OUTPUTS_DIR, "paper_results.csv")
        history.to_csv(csv_path, index=False)
        print(f"\n  Trade history saved to: {csv_path}")

    print(f"{'=' * 72}\n")


# ======================================================================
# WALK-FORWARD MODE
# ======================================================================

def run_walkforward() -> None:
    """
    Run a walk-forward backtest using dates and window sizes from
    ``config.WALK_FORWARD`` and save per-window results to
    ``outputs/walkforward_results.csv``.
    """
    wf_cfg = config.WALK_FORWARD
    ticker = config.TRADING["ticker"]

    wf = WalkForwardBacktester(
        ticker=ticker,
        start_date=wf_cfg["start_date"],
        end_date=wf_cfg["end_date"],
        train_months=wf_cfg["train_months"],
        test_months=wf_cfg["test_months"],
        initial_balance=config.TRADING["initial_balance"],
    )

    results = wf.run()
    wf.print_report(results)

    # Save per-window results to CSV
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    if results["windows"]:
        csv_path = os.path.join(OUTPUTS_DIR, "walkforward_results.csv")
        pd.DataFrame(results["windows"]).to_csv(csv_path, index=False)
        print(f"  Results saved to: {csv_path}\n")


# ======================================================================
# LIVE TRADING MODE (ALPACA)
# ======================================================================

def run_live():
    import time
    import subprocess
    from datetime import datetime, timedelta
    import config
    from broker.alpaca import AlpacaPaperBroker
    from data.fetcher import get_intraday_data, get_market_regime_data, get_historical_data
    from strategy.indicators import add_all_indicators
    from risk.manager import RiskManager
    from strategy.signals import SignalGenerator
    from analytics.metrics import PerformanceEngine

    # Suppress per-indicator log spam during live scans
    for noisy_logger in ["strategy.indicators", "data.fetcher"]:
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)

    rm = RiskManager(
        initial_balance=config.TRADING["initial_balance"],
        max_daily_loss_pct=config.RISK["max_daily_loss_pct"],
        max_trade_loss_pct=config.RISK["max_trade_loss_pct"],
        max_position_pct=config.RISK["max_position_pct"],
        cooldown_minutes=config.RISK["cooldown_minutes"],
        max_position_dollars=config.RISK.get("max_position_dollars", 2000.0),
        max_portfolio_heat_pct=config.RISK.get("max_portfolio_heat_pct", 0.60),
        atr_period=config.RISK.get("atr_period", 14),
        atr_multiplier_k=config.RISK.get("atr_multiplier_k", 2.0),
        risk_pct_per_trade=config.RISK.get("risk_pct_per_trade", 0.01),
    )
    sg = SignalGenerator(
        rm,
        rsi_oversold=config.SIGNAL["rsi_oversold"],
        rsi_overbought=config.SIGNAL["rsi_overbought"],
        require_confirmation=config.SIGNAL["require_confirmation"],
    )

    tickers = config.TRADING["tickers"]
    interval = config.TRADING.get("interval", "5m")
    lookback_intraday = config.TRADING.get("lookback_days_intraday", 30)
    brokers = {}
    for ticker in tickers:
        brokers[ticker] = AlpacaPaperBroker(
            api_key=config.ALPACA["api_key"],
            secret_key=config.ALPACA["secret_key"],
            base_url=config.ALPACA["base_url"],
            ticker=ticker,
            risk_manager=rm,
            signal_generator=sg,
            min_confidence=config.TRADING["min_confidence"],
            feed=config.ALPACA["feed"],
        )

    scan_interval_mins = config.TRADING.get("scan_interval_minutes", 15)
    scan_interval_secs = scan_interval_mins * 60

    print("=" * 60)
    print(f"  LIVE PAPER TRADING — {len(tickers)} tickers")
    print(f"  {', '.join(tickers)}")
    print(f"  Interval: {interval} | Confidence floor: {config.TRADING['min_confidence']}")
    print(f"  ATR sizing: k={config.RISK.get('atr_multiplier_k', 2.0)}, "
          f"risk/trade={config.RISK.get('risk_pct_per_trade', 0.01):.1%}")
    print(f"  Portfolio heat cap: {config.RISK.get('max_portfolio_heat_pct', 0.60):.0%}")
    print(f"  Bracket orders: SL={config.BRACKET.get('stop_loss_atr_mult', 1.5)}×ATR, "
          f"TP={config.BRACKET.get('take_profit_atr_mult', 3.0)}×ATR")
    print(f"  Checking every {scan_interval_mins} minutes")
    print("  Press Ctrl+C to stop")
    print("=" * 60)

    first_broker = brokers[tickers[0]]
    account = first_broker.get_account_info()
    print(f"  Equity:       ${account['equity']:,.2f}")
    print(f"  Buying power: ${account['buying_power']:,.2f}\n")

    # Performance engine for session wrap-up
    perf_engine = PerformanceEngine()

    try:
        while True:
            now = datetime.now().strftime("%H:%M:%S")

            # --- Market regime check (SPY SMA-200) ---
            regime_cfg = getattr(config, "MARKET_REGIME", {})
            regime = get_market_regime_data(
                ticker=regime_cfg.get("ticker", "SPY"),
                sma_period=regime_cfg.get("sma_period", 200),
            )
            regime_str = "BULL" if regime["is_bullish"] else "BEAR"

            print(f"\n[{now}] Scanning {len(tickers)} tickers... "
                  f"| SPY regime: {regime_str} "
                  f"(${regime['price']:.2f} vs SMA-200 ${regime['sma']:.2f})")
            print(f"  {'Ticker':<8} {'Price':>8} {'Signal':<6} "
                  f"{'Conf':>5} {'ATR':>8} {'Position':>12}")
            print(f"  {'-'*55}")

            action_alerts = []

            for ticker in tickers:
                try:
                    # Fetch 5-minute intraday bars
                    df = get_intraday_data(
                        ticker, lookback_intraday, interval
                    )
                    df = add_all_indicators(df)

                    # Multi-timeframe: check daily trend
                    daily_trend_bullish = True
                    try:
                        daily_df = get_historical_data(
                            ticker,
                            (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
                            datetime.now().strftime("%Y-%m-%d"),
                            "1d",
                        )
                        if len(daily_df) >= 20:
                            daily_sma = daily_df["Close"].rolling(20).mean().iloc[-1]
                            daily_close = daily_df["Close"].iloc[-1]
                            daily_trend_bullish = daily_close > daily_sma
                    except Exception:
                        pass  # default to bullish if daily fetch fails

                    tick = brokers[ticker].run_tick(
                        df,
                        market_regime_bullish=regime["is_bullish"],
                        daily_trend_bullish=daily_trend_bullish,
                    )

                    price = tick.get("price", 0)
                    signal = tick.get("signal", "HOLD")
                    confidence = tick.get("confidence", 0)
                    position = tick.get("position")
                    pos_str = (f"{position['shares']:.0f}sh"
                                if position else "none")

                    # ATR value for display
                    atr_val = float(df["ATR_14"].iloc[-1]) if "ATR_14" in df.columns else 0.0

                    print(f"  {ticker:<8} ${price:>7.2f} "
                          f"{signal:<6} {confidence:>5.2f} "
                          f"${atr_val:>7.2f} "
                          f"{pos_str:>12}")

                    if signal in ("BUY", "SELL"):
                        action_alerts.append(
                            f"{ticker}:{signal}@${price:.2f}"
                        )

                except Exception as e:
                    print(f"  {ticker:<8} ERROR: {e}")
                    continue

            # Portfolio summary
            try:
                account = first_broker.get_account_info()
                all_pos = first_broker.get_all_positions()
                long_exposure = sum(
                    p["shares"] * p["current_price"] for p in all_pos.values()
                )
                heat_pct = (long_exposure / account["equity"] * 100
                            if account["equity"] > 0 else 0)
                print(f"\n  Equity: ${account['equity']:,.2f} | "
                      f"Long exposure: ${long_exposure:,.0f} ({heat_pct:.1f}%) | "
                      f"Cash: ${account['cash']:,.2f}")
            except Exception:
                pass

            # Market close countdown
            close = datetime.now().replace(
                hour=1, minute=30, second=0, microsecond=0)
            if datetime.now().hour > 9:
                close = close + timedelta(days=1)
            mins_left = int(
                (close - datetime.now()).total_seconds() / 60)

            print(f"  Market closes in: {mins_left} mins")
            print(f"  Next scan:        in {scan_interval_mins} minutes")

            # Windows popup for any BUY/SELL
            if action_alerts:
                alert_text = ' | '.join(action_alerts)
                cmd_str = f'Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show("{alert_text}", "AutoTrader Alert")'
                subprocess.Popen(['powershell', '-command', cmd_str])

            time.sleep(scan_interval_secs)

    except KeyboardInterrupt:
        print("\n" + "=" * 60)
        print("  SHUTTING DOWN")
        account = first_broker.get_account_info()
        print(f"  Final equity: ${account['equity']:,.2f}")

        # Generate performance metrics
        try:
            all_trades = []
            for ticker in tickers:
                trade_df = brokers[ticker].get_trade_history()
                if not trade_df.empty:
                    all_trades.append(trade_df)

            if all_trades:
                combined = pd.concat(all_trades, ignore_index=True)
                metrics = perf_engine.compute_from_trades(
                    combined,
                    starting_equity=config.TRADING["initial_balance"],
                )
                perf_engine.save_summary(
                    os.path.join(OUTPUTS_DIR, "performance_summary.json")
                )
                perf_engine.append_session_stats(
                    os.path.join(OUTPUTS_DIR, "trade_history.csv")
                )
                print(perf_engine.get_summary_string())
            else:
                print("  No trades to analyze.")
        except Exception as e:
            print(f"  Performance metrics error: {e}")

        print("=" * 60)


def view_logs() -> None:
    """
    Display recent live trading logs from outputs/trader.log.
    """
    log_file_path = os.path.join(OUTPUTS_DIR, "trader.log")
    if not os.path.exists(log_file_path):
        print("\n  [INFO] No trader.log file found in outputs directory yet.\n")
        return

    with open(log_file_path, "r", encoding="utf-8") as f:
        content = f.read()

    print("\n" + "=" * 60)
    print("  LIVE TRADING LOGS (outputs/trader.log)")
    print("=" * 60)
    # Print the last ~50 lines or full content
    lines = content.strip().split("\n")
    recent = lines[-60:] if len(lines) > 60 else lines
    print("\n".join(recent))
    print("=" * 60 + "\n")


# ======================================================================
# Entry point
# ======================================================================

def main() -> None:
    """
    Parse the command-line mode argument and dispatch to the
    appropriate runner.
    """
    mode = sys.argv[1].lower() if len(sys.argv) > 1 else "backtest"

    if mode == "backtest":
        run_backtest()
    elif mode == "paper":
        run_paper()
    elif mode == "walkforward":
        run_walkforward()
    elif mode == "live":
        run_live()
    elif mode in ("status", "logs"):
        view_logs()
    else:
        print(f"Unknown mode: '{mode}'")
        print("Usage: python main.py [backtest|paper|walkforward|live|logs]")
        sys.exit(1)


if __name__ == "__main__":
    main()

