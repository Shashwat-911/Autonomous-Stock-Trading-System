import logging
import sys
import os

import pandas as pd

# Ensure project root is on the path when running as a script
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from risk.manager import RiskManager
from strategy.indicators import add_all_indicators

# Configure logger for signal generator module
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


class SignalGenerator:
    """
    Generates BUY / SELL / HOLD trading signals by evaluating multiple
    technical indicators against configurable thresholds.

    The generator enforces a *confirmation requirement* by default:
    a BUY signal is only emitted when **all** indicator conditions agree,
    preventing whipsaw trades based on a single noisy signal.

    Every signal evaluation is gated by a ``RiskManager`` circuit-breaker
    check (``can_trade()``) which must pass before any BUY order can
    proceed.

    Parameters
    ----------
    risk_manager : RiskManager
        Pre-trade risk management instance.
    rsi_oversold : float, optional
        RSI threshold below which the asset is considered oversold
        (default 30.0).
    rsi_overbought : float, optional
        RSI threshold above which the asset is considered overbought
        (default 70.0).
    require_confirmation : bool, optional
        When True, ALL indicator conditions must agree for a BUY signal.
        When False, at least 2 conditions must agree (default True).
    """

    def __init__(
        self,
        risk_manager: RiskManager,
        rsi_oversold: float = 30.0,
        rsi_overbought: float = 70.0,
        require_confirmation: bool = True,
    ) -> None:
        """
        Initialise the SignalGenerator.

        Parameters
        ----------
        risk_manager : RiskManager
            Risk management engine consulted before every signal.
        rsi_oversold : float, optional
            RSI oversold threshold (default 30.0).
        rsi_overbought : float, optional
            RSI overbought threshold (default 70.0).
        require_confirmation : bool, optional
            Require all indicators to confirm before issuing a BUY
            (default True).
        """
        self.risk_manager = risk_manager
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.require_confirmation = require_confirmation

        logger.info(
            "SignalGenerator initialised -- RSI oversold=%.1f, "
            "overbought=%.1f, confirmation=%s",
            rsi_oversold,
            rsi_overbought,
            require_confirmation,
        )

    # ------------------------------------------------------------------
    # Core signal generation
    # ------------------------------------------------------------------

    def generate_signal(
        self,
        df: pd.DataFrame,
        current_portfolio_value: float,
        market_regime_bullish: bool = True,
        daily_trend_bullish: bool = True,
    ) -> dict:
        """
        Evaluate the latest row of indicator data and produce a trading
        signal dictionary.

        Parameters
        ----------
        df : pd.DataFrame
            DataFrame that **must** already contain indicator columns
            (SMA_20, EMA_20, RSI_14, MACD, MACD_Signal, MACD_Hist,
            BB_Upper, BB_Middle, BB_Lower).
        current_portfolio_value : float
            Current total portfolio value passed to the risk manager.
        market_regime_bullish : bool, optional
            Whether the broad market (SPY) is above its 200-SMA.
            When False, all BUY signals are blocked (default True).
        daily_trend_bullish : bool, optional
            Whether the daily-timeframe trend supports a long entry.
            When False, buy confidence is reduced (default True).

        Returns
        -------
        dict
            A signal dictionary with keys:
            ``signal``, ``confidence``, ``reasons``, ``blocked``,
            ``block_reason``.
        """
        # Use the LAST row for all evaluations
        last = df.iloc[-1]

        rsi = last["RSI_14"]
        macd = last["MACD"]
        macd_signal = last["MACD_Signal"]
        close = last["Close"]
        sma_20 = last["SMA_20"]
        bb_lower = last["BB_Lower"]

        logger.info(
            "Evaluating signal -- Close=%.2f, RSI=%.2f, MACD=%.4f, "
            "MACD_Signal=%.4f, SMA_20=%.2f, BB_Lower=%.2f",
            close, rsi, macd, macd_signal, sma_20, bb_lower,
        )

        # ----- Risk gate (checked FIRST) -----
        can_trade, block_reason = self.risk_manager.can_trade(
            current_portfolio_value
        )
        blocked = not can_trade

        if blocked:
            logger.warning("Risk manager blocked trading: %s", block_reason)

        # ----- Market regime filter -----
        regime_blocked = False
        if not market_regime_bullish:
            regime_blocked = True
            logger.info("Market regime BEARISH (SPY < SMA-200) -- BUY signals blocked.")

        # ----- Evaluate BUY conditions -----
        buy_conditions = []
        buy_reasons = []

        cond_rsi_oversold = rsi < self.rsi_oversold
        if cond_rsi_oversold:
            buy_reasons.append(f"RSI oversold ({rsi:.1f} < {self.rsi_oversold})")
        buy_conditions.append(cond_rsi_oversold)

        cond_macd_bullish = macd > macd_signal
        if cond_macd_bullish:
            buy_reasons.append("MACD bullish (MACD > Signal)")
        buy_conditions.append(cond_macd_bullish)

        cond_above_sma = close > sma_20
        if cond_above_sma:
            buy_reasons.append(f"Above SMA_20 ({close:.2f} > {sma_20:.2f})")
        buy_conditions.append(cond_above_sma)

        cond_above_bb = close > bb_lower
        if cond_above_bb:
            buy_reasons.append(f"Above BB_Lower ({close:.2f} > {bb_lower:.2f})")
        buy_conditions.append(cond_above_bb)

        buy_count = sum(buy_conditions)
        buy_confidence = min(buy_count * 0.25, 1.0)

        # Daily trend penalty: reduce confidence if daily trend is bearish
        if not daily_trend_bullish and buy_count >= 2:
            buy_confidence = max(0.0, buy_confidence - 0.25)
            buy_reasons.append("Daily trend bearish (confidence reduced)")

        # ----- Evaluate SELL conditions -----
        sell_conditions = []
        sell_reasons = []

        cond_rsi_overbought = rsi > self.rsi_overbought
        if cond_rsi_overbought:
            sell_reasons.append(
                f"RSI overbought ({rsi:.1f} > {self.rsi_overbought})"
            )
        sell_conditions.append(cond_rsi_overbought)

        cond_macd_bearish = macd < macd_signal
        if cond_macd_bearish:
            sell_reasons.append("MACD bearish (MACD < Signal)")
        sell_conditions.append(cond_macd_bearish)

        cond_below_bb = close < bb_lower
        if cond_below_bb:
            sell_reasons.append(
                f"Below BB_Lower ({close:.2f} < {bb_lower:.2f})"
            )
        sell_conditions.append(cond_below_bb)

        cond_forced_exit = blocked
        if cond_forced_exit:
            sell_reasons.append(f"Forced exit -- risk block: {block_reason}")
        sell_conditions.append(cond_forced_exit)

        sell_count = sum(sell_conditions)
        sell_confidence = min(sell_count * 0.33, 1.0)

        # ----- Determine final signal -----
        if self.require_confirmation:
            # ALL 4 conditions must be true (original strict mode)
            buy_triggered = (buy_count == len(buy_conditions)) and not blocked and not regime_blocked
        else:
            # At least 3 out of 4 conditions must agree (raised from 2 -> ensures 0.75 floor)
            buy_conditions_met = sum(buy_conditions)
            buy_triggered = (buy_conditions_met >= 3) and not blocked and not regime_blocked

        # Block buy if market regime is bearish
        if regime_blocked and buy_count >= 2:
            buy_reasons.append("BLOCKED: Market regime bearish (SPY < SMA-200)")

        sell_triggered = sell_count >= 1

        if buy_triggered:
            signal = "BUY"
            confidence = buy_confidence
            reasons = buy_reasons
            logger.info(
                "BUY signal generated (confidence=%.2f) -- %s",
                confidence,
                "; ".join(reasons),
            )
        elif sell_triggered:
            signal = "SELL"
            confidence = sell_confidence
            reasons = sell_reasons
            logger.info(
                "SELL signal generated (confidence=%.2f) -- %s",
                confidence,
                "; ".join(reasons),
            )
        else:
            signal = "HOLD"
            confidence = 0.0
            reasons = ["No clear BUY or SELL conditions met"]
            logger.info("HOLD signal -- no actionable conditions detected.")

        result = {
            "signal": signal,
            "confidence": round(float(confidence), 2),
            "reasons": reasons,
            "blocked": blocked,
            "block_reason": block_reason if blocked else "",
        }

        logger.info("Signal result: %s", result)
        return result

    # ------------------------------------------------------------------
    # Human-readable summary
    # ------------------------------------------------------------------

    def get_signal_summary(self, signal_dict: dict) -> str:
        """
        Return a concise, one-line human-readable summary of a signal dict.

        Parameters
        ----------
        signal_dict : dict
            Signal dictionary as returned by ``generate_signal()``.

        Returns
        -------
        str
            Formatted summary string, e.g.
            ``"[BUY] Confidence: 0.75 | RSI oversold, MACD bullish, Above SMA"``.
        """
        sig = signal_dict["signal"]
        conf = signal_dict["confidence"]
        reasons = ", ".join(signal_dict["reasons"])

        if signal_dict["blocked"]:
            summary = (
                f"[{sig}] BLOCKED | {signal_dict['block_reason']} | {reasons}"
            )
        else:
            summary = f"[{sig}] Confidence: {conf:.2f} | {reasons}"

        return summary


# ======================================================================
# Self-test / demonstration
# ======================================================================
if __name__ == "__main__":
    from data.fetcher import get_historical_data
    from datetime import date, timedelta

    BALANCE = 5000.0

    print("=" * 70)
    print("  SignalGenerator -- Self-Test")
    print("=" * 70)

    # ------------------------------------------------------------------
    # Step 1: Fetch one year of MSFT data and compute indicators
    # ------------------------------------------------------------------
    end_date = date.today()
    start_date = end_date - timedelta(days=365)

    print(f"\nFetching MSFT data from {start_date} to {end_date}...")
    raw_df = get_historical_data("MSFT", str(start_date), str(end_date))
    df = add_all_indicators(raw_df)

    print(f"Rows: {len(df)}  |  Indicator columns present: "
          f"{[c for c in df.columns if c not in raw_df.columns]}")

    # ------------------------------------------------------------------
    # Step 2: Normal signal generation (no risk blocks)
    # ------------------------------------------------------------------
    print("\n--- Scenario 1: Normal signal generation ---")
    rm = RiskManager(initial_balance=BALANCE)
    sg = SignalGenerator(risk_manager=rm)

    signal = sg.generate_signal(df, current_portfolio_value=BALANCE)

    print("\nFull signal dict:")
    for k, v in signal.items():
        print(f"  {k}: {v}")

    summary = sg.get_signal_summary(signal)
    print(f"\nSummary: {summary}")

    # ------------------------------------------------------------------
    # Step 3: Simulate stop-loss -> signal should be BLOCKED / forced SELL
    # ------------------------------------------------------------------
    print("\n--- Scenario 2: Stop-loss triggers -> cooldown blocks trading ---")

    rm2 = RiskManager(initial_balance=BALANCE, cooldown_minutes=30)
    # Trigger stop-loss: entry=100, price dropped to 97 (3% > 2% limit)
    rm2.check_stop_loss(entry_price=100.0, current_price=97.0)

    sg2 = SignalGenerator(risk_manager=rm2)
    blocked_signal = sg2.generate_signal(df, current_portfolio_value=BALANCE)

    print("\nFull signal dict (after stop-loss):")
    for k, v in blocked_signal.items():
        print(f"  {k}: {v}")

    summary2 = sg2.get_signal_summary(blocked_signal)
    print(f"\nSummary: {summary2}")

    is_blocked = blocked_signal["blocked"]
    result = "[PASS]" if is_blocked else "[FAIL]"
    print(f"\nBlocked after stop-loss: {result}")

    is_sell_or_hold = blocked_signal["signal"] in ("SELL", "HOLD")
    result = "[PASS]" if is_sell_or_hold else "[FAIL]"
    print(f"Signal is SELL or HOLD (not BUY): {result}")

    # ------------------------------------------------------------------
    # Step 4: Daily loss breach -> forced exit
    # ------------------------------------------------------------------
    print("\n--- Scenario 3: Daily loss breach -> forced SELL ---")

    rm3 = RiskManager(initial_balance=BALANCE, max_daily_loss_pct=0.05)
    depleted = BALANCE * 0.93  # 7% loss

    sg3 = SignalGenerator(risk_manager=rm3)
    breach_signal = sg3.generate_signal(df, current_portfolio_value=depleted)

    print("\nFull signal dict (daily loss breach):")
    for k, v in breach_signal.items():
        print(f"  {k}: {v}")

    summary3 = sg3.get_signal_summary(breach_signal)
    print(f"\nSummary: {summary3}")

    forced_sell = breach_signal["signal"] == "SELL" and breach_signal["blocked"]
    result = "[PASS]" if forced_sell else "[FAIL]"
    print(f"Forced SELL on daily breach: {result}")

    has_forced_reason = any("Forced exit" in r for r in breach_signal["reasons"])
    result = "[PASS]" if has_forced_reason else "[FAIL]"
    print(f"Reasons include forced exit: {result}")

    # ------------------------------------------------------------------
    # Step 5: Diagnostic check across dataset
    # ------------------------------------------------------------------
    print("\n--- Scenario 4: Diagnostic Check Across Dataset ---")
    rm_diag = RiskManager(initial_balance=BALANCE)
    sg_diag = SignalGenerator(
        risk_manager=rm_diag,
        rsi_oversold=45.0,
        rsi_overbought=60.0,
        require_confirmation=False,
    )

    c1, c2, c3, c4 = 0, 0, 0, 0
    buy_triggered_rows = []

    for idx in range(len(df)):
        sub_df = df.iloc[: idx + 1]
        last_row = sub_df.iloc[-1]
        rsi = last_row["RSI_14"]
        macd = last_row["MACD"]
        macd_sig = last_row["MACD_Signal"]
        close = last_row["Close"]
        sma20 = last_row["SMA_20"]
        bb_low = last_row["BB_Lower"]

        b_conds = [
            rsi < sg_diag.rsi_oversold,
            macd > macd_sig,
            close > sma20,
            close > bb_low,
        ]
        b_count = sum(b_conds)

        if b_count >= 1:
            c1 += 1
        if b_count >= 2:
            c2 += 1
        if b_count >= 3:
            c3 += 1
        if b_count >= 4:
            c4 += 1

        res = sg_diag.generate_signal(sub_df, current_portfolio_value=BALANCE)
        if res["signal"] == "BUY":
            buy_triggered_rows.append(
                (str(sub_df.index[-1])[:10], res["confidence"], res["reasons"])
            )

    print(f"Rows meeting >= 1 BUY condition: {c1}")
    print(f"Rows meeting >= 2 BUY conditions: {c2}")
    print(f"Rows meeting >= 3 BUY conditions: {c3}")
    print(f"Rows meeting >= 4 BUY conditions: {c4}")
    print(f"\nFirst 5 rows where buy_triggered = True:")
    for b_row in buy_triggered_rows[:5]:
        print(f"  Date: {b_row[0]} | Confidence: {b_row[1]} | Reasons: {b_row[2]}")
    print(f"BUY signals generated count: {len(buy_triggered_rows)}")

    has_buys = len(buy_triggered_rows) > 0
    result = "[PASS]" if has_buys else "[FAIL]"
    print(f"Confirmed BUY signals generated: {result}")

    print("\n" + "=" * 70)
    print("  Self-test complete.")
    print("=" * 70)

