"""
analytics/metrics.py -- Quantitative performance analytics engine.

Computes Sharpe Ratio, Sortino Ratio, Max Drawdown, Expectancy,
Profit Factor, and order slippage/latency from trade history.
"""

import json
import logging
import os
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# Annualization factor for daily returns
TRADING_DAYS_PER_YEAR = 252
RISK_FREE_ANNUAL = 0.04  # 4% risk-free rate


class PerformanceEngine:
    """
    Quantitative analytics engine that computes key performance metrics
    from trade history and equity curves.

    Metrics computed:
    - Sharpe Ratio (annualized)
    - Sortino Ratio (annualized, downside deviation)
    - Max Drawdown (%) and peak-to-trough duration
    - Expectancy (E = W×avg_gain - (1-W)×avg_loss)
    - Profit Factor (gross gains / gross losses)
    - Order Slippage (signal price vs fill price)
    - Execution Latency (order submission to fill time)
    """

    def __init__(self, risk_free_rate: float = RISK_FREE_ANNUAL) -> None:
        self.risk_free_rate = risk_free_rate
        self._daily_rf = risk_free_rate / TRADING_DAYS_PER_YEAR
        self._metrics: dict = {}

    def compute_from_trades(
        self,
        trades_df: pd.DataFrame,
        equity_curve: Optional[pd.Series] = None,
        starting_equity: float = 100000.0,
        live_equity: Optional[float] = None,
    ) -> dict:
        """
        Compute all performance metrics from trade history.

        Parameters
        ----------
        trades_df : pd.DataFrame
            Trade history with columns: timestamp, action, ticker, price,
            quantity, filled_avg_price, status, pnl (optional).
        equity_curve : pd.Series, optional
            Time-indexed equity values. If None, will be estimated from
            trades and starting equity.
        starting_equity : float, optional
            Starting portfolio value (default 100000).
        live_equity : float, optional
            Actual live portfolio equity balance from broker.

        Returns
        -------
        dict
            Dictionary containing all computed metrics.
        """
        metrics = {
            "session_timestamp": datetime.now().isoformat(),
            "starting_equity": starting_equity,
        }

        # --- Build equity curve if not provided ---
        if equity_curve is None and not trades_df.empty:
            equity_curve = self._estimate_equity_curve(
                trades_df, starting_equity
            )

        # --- Return-based metrics ---
        if equity_curve is not None and len(equity_curve) > 1:
            returns = equity_curve.pct_change().dropna()

            metrics["ending_equity"] = live_equity if live_equity is not None else float(equity_curve.iloc[-1])
            metrics["total_return_pct"] = round(
                ((metrics["ending_equity"] / starting_equity) - 1) * 100, 4
            )
            metrics["sharpe_ratio"] = self._sharpe_ratio(returns)
            metrics["sortino_ratio"] = self._sortino_ratio(returns)

            dd_pct, dd_duration = self._max_drawdown(equity_curve)
            metrics["max_drawdown_pct"] = dd_pct
            metrics["max_drawdown_duration_days"] = dd_duration
        else:
            metrics["ending_equity"] = live_equity if live_equity is not None else starting_equity
            metrics["total_return_pct"] = round(
                ((metrics["ending_equity"] / starting_equity) - 1) * 100, 4
            )
            metrics["sharpe_ratio"] = 0.0
            metrics["sortino_ratio"] = 0.0
            metrics["max_drawdown_pct"] = 0.0
            metrics["max_drawdown_duration_days"] = 0

        # --- Trade-based metrics ---
        if not trades_df.empty:
            trade_metrics = self._trade_metrics(trades_df)
            metrics.update(trade_metrics)
        else:
            metrics.update({
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.0,
                "expectancy": 0.0,
                "profit_factor": 0.0,
                "avg_gain": 0.0,
                "avg_loss": 0.0,
            })

        # --- Slippage & Latency ---
        if not trades_df.empty:
            slippage = self._compute_slippage(trades_df)
            metrics.update(slippage)
        else:
            metrics["avg_slippage_pct"] = 0.0
            metrics["avg_execution_latency_ms"] = 0.0

        self._metrics = metrics
        logger.info("Performance metrics computed: %s", metrics)
        return metrics

    # ------------------------------------------------------------------
    # Metric calculations
    # ------------------------------------------------------------------

    def _sharpe_ratio(self, returns: pd.Series) -> float:
        """Annualized Sharpe Ratio."""
        if returns.std() == 0:
            return 0.0
        excess = returns.mean() - self._daily_rf
        sharpe = (excess / returns.std()) * np.sqrt(TRADING_DAYS_PER_YEAR)
        return round(float(sharpe), 4)

    def _sortino_ratio(self, returns: pd.Series) -> float:
        """
        Sortino ratio using correct downside deviation.
        Downside deviation: std of all returns where positive returns are replaced with 0.
        Annualised assuming daily returns (252 trading days).
        """
        if returns.empty or returns.std() == 0:
            return 0.0

        mar = self._daily_rf  # Minimum acceptable return (daily risk-free rate)

        # Correct downside deviation: use all returns, floor at MAR
        downside_returns = returns.copy()
        downside_returns[downside_returns > mar] = 0.0
        downside_deviation = np.sqrt(np.mean(downside_returns ** 2))

        if downside_deviation == 0:
            return 0.0

        excess = returns.mean() - mar
        sortino = (excess / downside_deviation) * np.sqrt(252)
        return round(float(sortino), 4)

    def _max_drawdown(self, equity_curve: pd.Series) -> tuple[float, int]:
        """
        Max drawdown percentage and duration in data points.

        Returns
        -------
        tuple[float, int]
            (max_drawdown_pct, duration_in_points)
        """
        peak = equity_curve.expanding().max()
        drawdown = (equity_curve - peak) / peak
        max_dd = float(drawdown.min()) * 100  # as negative percentage

        # Duration: longest consecutive drawdown period
        is_dd = drawdown < 0
        if is_dd.any():
            # Find the longest streak of drawdown
            groups = (is_dd != is_dd.shift()).cumsum()
            dd_groups = is_dd.groupby(groups)
            durations = [g.sum() for _, g in dd_groups if g.any()]
            max_duration = max(durations) if durations else 0
        else:
            max_duration = 0

        return round(max_dd, 4), int(max_duration)

    def _trade_metrics(self, trades_df: pd.DataFrame) -> dict:
        """Compute win rate, expectancy, profit factor from round-trip trades."""
        empty = {
            "total_trades": 0, "winning_trades": 0, "losing_trades": 0,
            "win_rate": 0.0, "expectancy": 0.0, "profit_factor": 0.0,
            "avg_gain": 0.0, "avg_loss": 0.0,
        }

        if trades_df.empty or "pnl" not in trades_df.columns:
            return empty

        # Drop rows with NaN pnl
        trades = trades_df.dropna(subset=["pnl"]).copy()
        if trades.empty:
            return empty

        wins = trades[trades["pnl"] > 0]["pnl"]
        losses = trades[trades["pnl"] < 0]["pnl"]
        total = len(trades)
        n_wins = len(wins)
        n_losses = len(losses)

        win_rate = n_wins / total if total > 0 else 0.0
        avg_gain = float(wins.mean()) if n_wins > 0 else 0.0
        avg_loss = float(losses.mean()) if n_losses > 0 else 0.0

        gross_gains = float(wins.sum()) if n_wins > 0 else 0.0
        gross_losses = abs(float(losses.sum())) if n_losses > 0 else 0.0
        profit_factor = (gross_gains / gross_losses) if gross_losses > 0 else 0.0

        expectancy = (win_rate * avg_gain) + ((1 - win_rate) * avg_loss)

        return {
            "total_trades": total,
            "winning_trades": n_wins,
            "losing_trades": n_losses,
            "win_rate": round(win_rate, 4),
            "expectancy": round(expectancy, 4),
            "profit_factor": round(profit_factor, 4),
            "avg_gain": round(avg_gain, 4),
            "avg_loss": round(avg_loss, 4),
        }

    def _compute_slippage(self, trades_df: pd.DataFrame) -> dict:
        """
        Compute slippage metrics. Uses round-trip trade data when available
        (entry_price vs exit_price relative to SMA or intended price).
        Falls back to limit/stop price comparison for bracket legs.
        """
        result = {"avg_slippage_pct": 0.0, "avg_execution_latency_ms": 0.0}

        if trades_df.empty:
            return result

        slippage_samples = []

        # Path 1: Round-trip trades — use hold_duration as execution quality proxy
        if "entry_price" in trades_df.columns and "exit_price" in trades_df.columns:
            rt = trades_df.dropna(subset=["entry_price", "exit_price"])
            if not rt.empty and "hold_duration_minutes" in rt.columns:
                # Latency proxy: avg hold duration in ms (for market orders, fill is near-instant)
                short_trades = rt[rt["hold_duration_minutes"] < 5]
                if not short_trades.empty:
                    avg_latency = float(short_trades["hold_duration_minutes"].mean() * 60000)
                    result["avg_execution_latency_ms"] = round(avg_latency, 2)

        # Path 2: Bracket leg slippage (limit/stop orders with known price)
        if "filled_avg_price" in trades_df.columns and "price" in trades_df.columns:
            bracket_legs = trades_df[
                (trades_df["price"].notna()) & 
                (trades_df["price"] > 0) &
                (trades_df["filled_avg_price"].notna()) &
                (trades_df["filled_avg_price"] > 0)
            ].copy()

            if not bracket_legs.empty:
                bracket_legs["slippage_pct"] = (
                    (bracket_legs["filled_avg_price"] - bracket_legs["price"]).abs()
                    / bracket_legs["price"] * 100
                )
                # Cap at 2% to exclude stale/erroneous data
                bracket_legs = bracket_legs[bracket_legs["slippage_pct"] < 2.0]
                if not bracket_legs.empty:
                    slippage_samples.extend(bracket_legs["slippage_pct"].tolist())

        # Path 3: Market orders with intended_price
        if "filled_avg_price" in trades_df.columns and "intended_price" in trades_df.columns:
            mkt_orders = trades_df[
                (trades_df["intended_price"].notna()) &
                (trades_df["intended_price"] > 0) &
                (trades_df["filled_avg_price"].notna()) &
                (trades_df["filled_avg_price"] > 0)
            ].copy()
            if not mkt_orders.empty:
                mkt_orders["slippage_pct"] = (
                    (mkt_orders["filled_avg_price"] - mkt_orders["intended_price"]).abs()
                    / mkt_orders["intended_price"] * 100
                )
                mkt_orders = mkt_orders[mkt_orders["slippage_pct"] < 2.0]
                if not mkt_orders.empty:
                    slippage_samples.extend(mkt_orders["slippage_pct"].tolist())

        # Path 4: Fallback to timestamp latency if proxy wasn't triggered
        if result["avg_execution_latency_ms"] == 0.0:
            sub_col = "submitted_at" if "submitted_at" in trades_df.columns else None
            fill_col = "filled_at" if "filled_at" in trades_df.columns else None
            if sub_col and fill_col:
                timed = trades_df[trades_df[fill_col].notnull() & trades_df[sub_col].notnull()].copy()
                if not timed.empty:
                    try:
                        submitted = pd.to_datetime(timed[sub_col], utc=True, errors="coerce")
                        filled_ts = pd.to_datetime(timed[fill_col], utc=True, errors="coerce")
                        valid_mask = submitted.notnull() & filled_ts.notnull()
                        if valid_mask.any():
                            latency_ms = (filled_ts[valid_mask] - submitted[valid_mask]).dt.total_seconds() * 1000
                            sane = latency_ms[latency_ms <= 60_000]
                            if not sane.empty:
                                result["avg_execution_latency_ms"] = round(float(sane.mean()), 2)
                    except Exception as e:
                        logger.warning("Error computing execution latency: %s", e)

        if slippage_samples:
            result["avg_slippage_pct"] = round(float(np.mean(slippage_samples)), 6)

        return result

    def _estimate_equity_curve(
        self, trades_df: pd.DataFrame, starting_equity: float
    ) -> pd.Series:
        """Estimate a simple equity curve from trade PnLs."""
        equity = [starting_equity]

        if "pnl" in trades_df.columns:
            for pnl in trades_df["pnl"].fillna(0).astype(float):
                equity.append(equity[-1] + pnl)

        return pd.Series(equity)

    # ------------------------------------------------------------------
    # Output methods
    # ------------------------------------------------------------------

    def save_summary(
        self,
        filepath: str = "outputs/performance_summary.json",
    ) -> None:
        """
        Save performance metrics to a JSON file.

        Parameters
        ----------
        filepath : str
            Output file path.
        """
        if not self._metrics:
            logger.warning("No metrics to save. Run compute_from_trades first.")
            return

        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        # Handle special float values for JSON serialization
        clean_metrics = {}
        for k, v in self._metrics.items():
            if isinstance(v, float) and (np.isinf(v) or np.isnan(v)):
                clean_metrics[k] = str(v)
            else:
                clean_metrics[k] = v

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(clean_metrics, f, indent=2, default=str)

        logger.info("Performance summary saved to %s", filepath)

    def _build_session_row(self) -> dict:
        """Return a copy of the current session metrics as a row dict."""
        return dict(self._metrics)

    def append_session_stats(
        self,
        filepath: str = "outputs/trade_history.csv",
    ) -> None:
        """Append session stats to CSV, deduplicating by date."""
        if not self._metrics:
            logger.warning("No metrics to append. Run compute_from_trades first.")
            return

        import os
        from datetime import date

        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        today_str = date.today().isoformat()
        new_row = self._build_session_row()
        new_row["date"] = today_str

        if os.path.exists(filepath):
            try:
                existing = pd.read_csv(filepath)
            except Exception:
                existing = pd.DataFrame()

            if not existing.empty:
                # Add date column if not present, backfilling from session_timestamp
                if "date" not in existing.columns:
                    if "session_timestamp" in existing.columns:
                        existing["date"] = existing["session_timestamp"].astype(str).str[:10]
                    else:
                        existing["date"] = ""

                # Remove any existing rows for today (overwrite with latest)
                existing = existing[existing["date"] != today_str]
                updated = pd.concat(
                    [existing, pd.DataFrame([new_row])],
                    ignore_index=True
                )
            else:
                updated = pd.DataFrame([new_row])
        else:
            updated = pd.DataFrame([new_row])

        updated.to_csv(filepath, index=False)
        logger.info(f"Session stats saved to {filepath} (date: {today_str})")

    def get_summary_string(self) -> str:
        """Return a formatted string summary of the metrics."""
        if not self._metrics:
            return "No metrics computed."

        m = self._metrics
        lines = [
            "=" * 60,
            "  QUANTITATIVE PERFORMANCE SUMMARY",
            "=" * 60,
            f"  Total Return:       {m.get('total_return_pct', 0):.2f}%",
            f"  Sharpe Ratio:       {m.get('sharpe_ratio', 0):.4f}",
            f"  Sortino Ratio:      {m.get('sortino_ratio', 0):.4f}",
            f"  Max Drawdown:       {m.get('max_drawdown_pct', 0):.2f}%",
            f"  Drawdown Duration:  {m.get('max_drawdown_duration_days', 0)} periods",
            f"  Win Rate:           {m.get('win_rate', 0):.1%}",
            f"  Expectancy:         ${m.get('expectancy', 0):.2f}",
            f"  Profit Factor:      {m.get('profit_factor', 0):.2f}",
            f"  Avg Slippage:       {m.get('avg_slippage_pct', 0):.4f}%",
            f"  Avg Latency:        {m.get('avg_execution_latency_ms', 0):.0f}ms",
            f"  Total Trades:       {m.get('total_trades', 0)}",
            "=" * 60,
        ]
        return "\n".join(lines)
