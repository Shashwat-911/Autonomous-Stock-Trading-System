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
        """Annualized Sortino Ratio (uses downside deviation only)."""
        downside = returns[returns < 0]
        if downside.empty or downside.std() == 0:
            return 0.0
        excess = returns.mean() - self._daily_rf
        sortino = (excess / downside.std()) * np.sqrt(TRADING_DAYS_PER_YEAR)
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
        """Compute win rate, expectancy, and profit factor from trades."""
        action_col = "action" if "action" in trades_df.columns else ("side" if "side" in trades_df.columns else None)

        # Try to extract PnL from trades
        if "pnl" in trades_df.columns:
            pnls = trades_df["pnl"].dropna().astype(float)
        elif action_col and "filled_avg_price" in trades_df.columns and "price" in trades_df.columns:
            # Estimate PnL from price difference for SELL trades
            sells = trades_df[trades_df[action_col].astype(str).str.upper() == "SELL"].copy()
            if not sells.empty and "filled_avg_price" in sells.columns:
                pnls = sells["filled_avg_price"].astype(float) - sells["price"].astype(float)
            else:
                pnls = pd.Series(dtype=float)
        else:
            pnls = pd.Series(dtype=float)

        total = len(pnls)
        if total == 0:
            return {
                "total_trades": len(trades_df),
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.0,
                "expectancy": 0.0,
                "profit_factor": 0.0,
                "avg_gain": 0.0,
                "avg_loss": 0.0,
            }

        wins = pnls[pnls > 0]
        losses = pnls[pnls < 0]

        win_rate = len(wins) / total if total > 0 else 0.0
        avg_gain = float(wins.mean()) if len(wins) > 0 else 0.0
        avg_loss = float(losses.mean()) if len(losses) > 0 else 0.0

        # Expectancy: E = (W × avg_gain) - ((1-W) × |avg_loss|)
        expectancy = (win_rate * avg_gain) - ((1 - win_rate) * abs(avg_loss))

        # Profit Factor: gross gains / gross losses
        gross_gains = float(wins.sum()) if len(wins) > 0 else 0.0
        gross_losses = abs(float(losses.sum())) if len(losses) > 0 else 0.0
        profit_factor = (
            gross_gains / gross_losses if gross_losses > 0 else float("inf")
        )

        return {
            "total_trades": len(trades_df),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate": round(win_rate, 4),
            "expectancy": round(expectancy, 4),
            "profit_factor": round(profit_factor, 4),
            "avg_gain": round(avg_gain, 4),
            "avg_loss": round(avg_loss, 4),
        }

    def _compute_slippage(self, trades_df: pd.DataFrame) -> dict:
        """Compute average slippage and execution latency."""
        result = {"avg_slippage_pct": 0.0, "avg_execution_latency_ms": 0.0}

        if "filled_avg_price" in trades_df.columns and "price" in trades_df.columns:
            filled = trades_df.dropna(subset=["filled_avg_price"]).copy()
            # Filter out non-zero price rows
            filled = filled[filled["price"] > 0]
            if not filled.empty:
                signal_prices = filled["price"].astype(float)
                fill_prices = filled["filled_avg_price"].astype(float)
                slippage_pct = ((fill_prices - signal_prices) / signal_prices * 100).abs()
                result["avg_slippage_pct"] = round(float(slippage_pct.mean()), 6)

        if "submitted_at" in trades_df.columns and "filled_at" in trades_df.columns:
            timed = trades_df[trades_df["filled_at"].notnull() & trades_df["submitted_at"].notnull()].copy()
            if not timed.empty:
                try:
                    submitted = pd.to_datetime(timed["submitted_at"], utc=True, errors="coerce")
                    filled = pd.to_datetime(timed["filled_at"], utc=True, errors="coerce")
                    valid_mask = submitted.notnull() & filled.notnull()
                    if valid_mask.any():
                        latency_ms = (filled[valid_mask] - submitted[valid_mask]).dt.total_seconds() * 1000
                        result["avg_execution_latency_ms"] = round(float(latency_ms.mean()), 2)
                except Exception as e:
                    logger.warning("Error computing latency: %s", e)

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

    def append_session_stats(
        self,
        filepath: str = "outputs/trade_history.csv",
    ) -> None:
        """
        Append current session metrics as a single row to a CSV file.

        Parameters
        ----------
        filepath : str
            Output CSV file path.
        """
        if not self._metrics:
            logger.warning("No metrics to append. Run compute_from_trades first.")
            return

        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        row_df = pd.DataFrame([self._metrics])

        if os.path.exists(filepath):
            row_df.to_csv(filepath, mode="a", header=False, index=False)
        else:
            row_df.to_csv(filepath, mode="w", header=True, index=False)

        logger.info("Session stats appended to %s", filepath)

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
