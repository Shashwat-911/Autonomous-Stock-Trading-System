"""
walk_forward.py -- Walk-forward backtesting engine.

Splits historical data into rolling train/test windows so the
strategy is always evaluated on truly unseen data, preventing
overfitting.
"""

import logging
import os
import sys
from datetime import date

import pandas as pd
from dateutil.relativedelta import relativedelta

# Ensure project root is on path when running as a script
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config
from data.fetcher import get_historical_data
from strategy.indicators import add_all_indicators
from strategy.signals import SignalGenerator
from risk.manager import RiskManager
from broker.paper import LocalPaperBroker

# Configure logger
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# Number of trailing train rows kept for indicator warmup
_WARMUP_ROWS = 50


class WalkForwardBacktester:
    """
    Rolling walk-forward backtesting engine that evaluates a trading
    strategy across multiple non-overlapping test windows, each
    preceded by a training warmup period.

    This avoids the look-ahead bias inherent in a single full-period
    backtest and produces a *consistency score* that reflects how
    reliably the strategy performs on unseen data.

    Parameters
    ----------
    ticker : str
        Ticker symbol to backtest.
    start_date : str
        Overall start date (ISO format, e.g. ``'2023-01-01'``).
    end_date : str
        Overall end date (ISO format).
    train_months : int, optional
        Length of each training window in months (default 6).
    test_months : int, optional
        Length of each test window in months (default 3).
    initial_balance : float, optional
        Starting cash balance for each window (default 5000.0).
    """

    def __init__(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        train_months: int = 6,
        test_months: int = 3,
        initial_balance: float = 5000.0,
    ) -> None:
        """
        Initialise the walk-forward backtester.

        Parameters
        ----------
        ticker : str
            Ticker symbol.
        start_date : str
            Overall backtest start (ISO format).
        end_date : str
            Overall backtest end (ISO format).
        train_months : int, optional
            Training window length in months (default 6).
        test_months : int, optional
            Test window length in months (default 3).
        initial_balance : float, optional
            Fresh balance for each window (default 5000.0).
        """
        self.ticker = ticker
        self.start_date = date.fromisoformat(start_date)
        self.end_date = date.fromisoformat(end_date)
        self.train_months = train_months
        self.test_months = test_months
        self.initial_balance = initial_balance

        logger.info(
            "WalkForwardBacktester initialised -- ticker=%s, "
            "period=%s to %s, train=%dmo, test=%dmo, balance=%.2f",
            ticker,
            start_date,
            end_date,
            train_months,
            test_months,
            initial_balance,
        )

    # ------------------------------------------------------------------
    # Window generation
    # ------------------------------------------------------------------

    def _generate_windows(self) -> list[dict]:
        """
        Generate all rolling train/test windows between start_date
        and end_date.

        Returns
        -------
        list[dict]
            Each dict has keys: train_start, train_end, test_start,
            test_end (all ``datetime.date``).
        """
        windows = []
        cursor = self.start_date

        while True:
            train_start = cursor
            train_end = cursor + relativedelta(months=self.train_months)
            test_start = train_end
            test_end = test_start + relativedelta(months=self.test_months)

            if test_end > self.end_date:
                break

            windows.append(
                {
                    "train_start": train_start,
                    "train_end": train_end,
                    "test_start": test_start,
                    "test_end": test_end,
                }
            )
            cursor += relativedelta(months=self.test_months)

        logger.info("Generated %d walk-forward windows.", len(windows))
        return windows

    # ------------------------------------------------------------------
    # Max drawdown helper
    # ------------------------------------------------------------------

    @staticmethod
    def _calculate_max_drawdown(
        broker: LocalPaperBroker, price_series: pd.Series
    ) -> float:
        """
        Calculate the maximum peak-to-trough portfolio drawdown over
        a price series.

        Parameters
        ----------
        broker : LocalPaperBroker
            Broker instance used to derive portfolio values.
        price_series : pd.Series
            Series of portfolio values recorded at each bar during
            the test window (passed via ``price_series`` parameter
            for interface consistency).

        Returns
        -------
        float
            Maximum drawdown as a negative percentage (e.g. -4.2
            means the portfolio dropped 4.2% from its peak).
        """
        if price_series.empty or len(price_series) < 2:
            return 0.0

        values = price_series.values
        peak = values[0]
        max_dd = 0.0

        for pv in values:
            if pv > peak:
                peak = pv
            if peak > 0:
                dd = (peak - pv) / peak * 100.0
                if dd > max_dd:
                    max_dd = dd

        return round(-max_dd, 2)

    # ------------------------------------------------------------------
    # Period label helper
    # ------------------------------------------------------------------

    @staticmethod
    def _period_label(d_start: date, d_end: date) -> str:
        """
        Format a date range as a human-readable label.

        Examples: ``'Jan-Jun 2023'``, ``'Jul-Sep 2023'``.

        Parameters
        ----------
        d_start : date
            Period start.
        d_end : date
            Period end (exclusive -- label uses the prior month).

        Returns
        -------
        str
            Formatted period string.
        """
        month_abbr = [
            "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
        ]
        # end is exclusive, so show the month *before* d_end
        end_display = d_end - relativedelta(months=1)
        s = f"{month_abbr[d_start.month]} {d_start.year}"
        e = f"{month_abbr[end_display.month]} {end_display.year}"
        return f"{s} - {e}"

    # ------------------------------------------------------------------
    # Core run method
    # ------------------------------------------------------------------

    def run(self) -> dict:
        """
        Execute the full walk-forward backtest across all generated
        windows.

        Returns
        -------
        dict
            Dictionary with keys:
            - ``windows``: list of per-window result dicts.
            - ``summary``: aggregate statistics dict.
        """
        windows = self._generate_windows()

        if not windows:
            logger.warning("No valid windows could be generated.")
            return {"windows": [], "summary": {}}

        logger.info(
            "Starting walk-forward backtest: %d windows, ticker=%s",
            len(windows),
            self.ticker,
        )

        window_results = []

        for idx, win in enumerate(windows, start=1):
            train_label = self._period_label(win["train_start"], win["train_end"])
            test_label = self._period_label(win["test_start"], win["test_end"])

            logger.info(
                "Window %d/%d -- Train: %s | Test: %s",
                idx,
                len(windows),
                train_label,
                test_label,
            )

            # (a) Fetch train data (only need tail for warmup)
            try:
                train_df = get_historical_data(
                    self.ticker,
                    str(win["train_start"]),
                    str(win["train_end"]),
                    interval=config.TRADING["interval"],
                )
            except Exception as e:
                logger.error("Failed to fetch train data for window %d: %s", idx, e)
                continue

            # (b) Fetch test data
            try:
                test_df = get_historical_data(
                    self.ticker,
                    str(win["test_start"]),
                    str(win["test_end"]),
                    interval=config.TRADING["interval"],
                )
            except Exception as e:
                logger.error("Failed to fetch test data for window %d: %s", idx, e)
                continue

            if test_df.empty:
                logger.warning("No test data for window %d -- skipping.", idx)
                continue

            # (c) Combine: last N warmup rows of train + full test
            warmup = train_df.tail(_WARMUP_ROWS)
            combined = pd.concat([warmup, test_df])
            # Remove duplicates (overlapping dates between train tail and test start)
            combined = combined[~combined.index.duplicated(keep="last")]

            # (d) Compute indicators on combined data
            combined = add_all_indicators(combined)

            # (e) Slice back to test-period rows only
            test_start_ts = test_df.index[0]
            test_only = combined.loc[test_start_ts:]

            if test_only.empty or len(test_only) < 2:
                logger.warning(
                    "Insufficient test rows for window %d after indicator "
                    "warmup -- skipping.",
                    idx,
                )
                continue

            # (f) Fresh components for this window (in-memory SQLite)
            rm = RiskManager(
                initial_balance=self.initial_balance,
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
                initial_balance=self.initial_balance,
                ticker=self.ticker,
                risk_manager=rm,
                signal_generator=sg,
                min_confidence=config.TRADING["min_confidence"],
                db_path=":memory:",
            )

            # (g) Simulate: loop through test rows
            portfolio_values = []
            n_test = len(test_only)

            for i in range(n_test):
                slice_df = test_only.iloc[: i + 1]
                result = broker.run_tick(slice_df)
                portfolio_values.append(result["portfolio_value"])

            # (h) Collect results
            last_price = float(test_only.iloc[-1]["Close"])
            summary = broker.get_performance_summary(current_price=last_price)
            pv_series = pd.Series(portfolio_values)
            max_dd = self._calculate_max_drawdown(broker, pv_series)

            return_pct = (
                (portfolio_values[-1] - self.initial_balance)
                / self.initial_balance
                * 100.0
            )

            win_result = {
                "window": idx,
                "train_period": train_label,
                "test_period": test_label,
                "trades": summary["total_trades"],
                "pnl": summary["total_pnl"],
                "return_pct": round(return_pct, 2),
                "win_rate": summary["win_rate"],
                "max_drawdown": max_dd,
            }

            window_results.append(win_result)
            logger.info("Window %d result: %s", idx, win_result)

        # ------------------------------------------------------------------
        # Aggregate summary
        # ------------------------------------------------------------------
        total_windows = len(window_results)

        if total_windows == 0:
            agg = {
                "total_windows": 0,
                "profitable_windows": 0,
                "win_rate_across_windows": 0.0,
                "avg_return_pct": 0.0,
                "best_window_return": 0.0,
                "worst_window_return": 0.0,
                "avg_trades_per_window": 0.0,
                "consistency_score": 0.0,
            }
        else:
            returns = [w["return_pct"] for w in window_results]
            trades = [w["trades"] for w in window_results]
            profitable = sum(1 for r in returns if r > 0)

            agg = {
                "total_windows": total_windows,
                "profitable_windows": profitable,
                "win_rate_across_windows": round(
                    profitable / total_windows * 100.0, 2
                ),
                "avg_return_pct": round(sum(returns) / total_windows, 2),
                "best_window_return": round(max(returns), 2),
                "worst_window_return": round(min(returns), 2),
                "avg_trades_per_window": round(
                    sum(trades) / total_windows, 2
                ),
                "consistency_score": round(profitable / total_windows, 2),
            }

        logger.info("Walk-forward aggregate summary: %s", agg)

        return {"windows": window_results, "summary": agg}

    # ------------------------------------------------------------------
    # Report printer
    # ------------------------------------------------------------------

    def print_report(self, results: dict) -> None:
        """
        Print a clean ASCII report of the walk-forward backtest results.

        Parameters
        ----------
        results : dict
            The dict returned by ``run()``, containing ``windows``
            and ``summary`` keys.
        """
        windows = results.get("windows", [])
        summary = results.get("summary", {})

        print()
        print("=" * 72)
        print("  WALK-FORWARD BACKTEST REPORT")
        print(f"  Ticker: {self.ticker}  |  "
              f"Train: {self.train_months}mo  |  "
              f"Test: {self.test_months}mo  |  "
              f"Balance: {self.initial_balance:.0f}")
        print("=" * 72)

        if not windows:
            print("\n  No windows were evaluated.\n")
            print("=" * 72)
            return

        for w in windows:
            pnl = w["pnl"]
            pnl_sign = "+" if pnl >= 0 else ""
            ret = w["return_pct"]
            ret_sign = "+" if ret >= 0 else ""

            print(
                f"\n  Window {w['window']} | "
                f"Train: {w['train_period']} | "
                f"Test: {w['test_period']}"
            )
            print(
                f"    Trades: {w['trades']:>3}  |  "
                f"PnL: {pnl_sign}{pnl:.2f}  |  "
                f"Return: {ret_sign}{ret:.2f}%  |  "
                f"Win Rate: {w['win_rate']:.0f}%  |  "
                f"Max DD: {w['max_drawdown']:.2f}%"
            )

        # Aggregate summary
        print(f"\n{'=' * 72}")
        print("  SUMMARY")
        print(f"{'=' * 72}")

        tw = summary.get("total_windows", 0)
        pw = summary.get("profitable_windows", 0)
        cs = summary.get("consistency_score", 0)
        ar = summary.get("avg_return_pct", 0)
        bw = summary.get("best_window_return", 0)
        ww = summary.get("worst_window_return", 0)
        at = summary.get("avg_trades_per_window", 0)

        bw_sign = "+" if bw >= 0 else ""
        ww_sign = "+" if ww >= 0 else ""
        ar_sign = "+" if ar >= 0 else ""

        print(f"  Consistent profit in {pw}/{tw} windows ({cs * 100:.0f}%)")
        print(f"  Avg return per window: {ar_sign}{ar:.2f}%")
        print(f"  Best: {bw_sign}{bw:.2f}%  |  Worst: {ww_sign}{ww:.2f}%")
        print(f"  Avg trades per window: {at:.1f}")
        print(f"{'=' * 72}\n")


# ======================================================================
# Self-test
# ======================================================================
if __name__ == "__main__":
    TICKER = "AAPL"
    START = "2023-01-01"
    END = "2025-01-01"

    print("Starting walk-forward backtest...")
    wf = WalkForwardBacktester(
        ticker=TICKER,
        start_date=START,
        end_date=END,
        train_months=6,
        test_months=3,
        initial_balance=5000.0,
    )

    results = wf.run()
    wf.print_report(results)
