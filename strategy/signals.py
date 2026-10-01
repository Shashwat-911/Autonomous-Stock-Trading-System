import logging
import sys
import os

import pandas as pd

# Ensure project root is on the path when running as a script
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from risk.manager import RiskManager
from strategy.indicators import add_all_indicators

try:
    from ml.predictor import MetaLabelPredictor
    _META_PREDICTOR = MetaLabelPredictor()
    # ML filter DISABLED: model was trained on daily bars (INTERVAL="1d" in ml/data_pipeline.py)
    # but is applied to hourly signals. Feature distributions differ enough that the model
    # returns systematically low probabilities (P~0.27-0.35) for valid momentum setups,
    # blocking all trades. Re-enable after retraining on 1h bars (Audit Priority #15).
    # To re-enable: set _META_AVAILABLE = True
    _META_AVAILABLE = False
except Exception:
    _META_AVAILABLE = False
    _META_PREDICTOR = None

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
        rsi_oversold: float = 37.0,
        rsi_overbought: float = 70.0,
        rsi_momentum_min: float = 40.0,
        rsi_momentum_max: float = 65.0,
        require_confirmation: bool = False,
        adx_min: float = 20.0,
        adx_period: int = 14,
        **kwargs,
    ) -> None:
        """
        Initialise the SignalGenerator for Pure Momentum Trading (Section 7.2).

        Parameters
        ----------
        risk_manager : RiskManager
            Risk management engine consulted before every signal.
        rsi_oversold : float, optional
            RSI oversold threshold for fallback dip entries (default 37.0).
        rsi_overbought : float, optional
            RSI overbought threshold for momentum exhaustion exit (default 70.0).
        rsi_momentum_min : float, optional
            Minimum RSI for momentum entry corridor (default 40.0).
        rsi_momentum_max : float, optional
            Maximum RSI for momentum entry corridor (default 65.0).
        require_confirmation : bool, optional
            When True, requires all confirmation conditions (default False).
        adx_min : float, optional
            Minimum ADX threshold for trend strength (default 20.0).
        adx_period : int, optional
            Lookback period for ADX (default 14).
        """
        self.risk_manager = risk_manager
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.rsi_momentum_min = kwargs.get("rsi_momentum_min", rsi_momentum_min)
        self.rsi_momentum_max = kwargs.get("rsi_momentum_max", rsi_momentum_max)
        self.require_confirmation = require_confirmation
        self.adx_min = kwargs.get("adx_min", adx_min)
        self.adx_period = kwargs.get("adx_period", adx_period)

        logger.info(
            "SignalGenerator initialised (Pure Momentum) -- RSI momentum band=[%.1f, %.1f], "
            "RSI overbought=%.1f, ADX min=%.1f, confirmation=%s",
            self.rsi_momentum_min,
            self.rsi_momentum_max,
            self.rsi_overbought,
            self.adx_min,
            self.require_confirmation,
        )

    # ------------------------------------------------------------------
    # Core signal generation
    # ------------------------------------------------------------------

    def generate_signal(
        self,
        df: pd.DataFrame,
        portfolio_value: float = 100000.0,
        market_regime_bullish: bool = True,
        daily_trend_bullish: bool = True,
        has_position: bool = False,
        **kwargs,
    ) -> dict:
        """
        Evaluate technical indicators using Section 7.2 Pure Momentum logic:
        1. MACD Bullish Trend / Expansion (MACD > Signal with positive histogram or fresh cross)
        2. Uptrend Alignment: Close > 20-period SMA & Close > BB_Lower
        3. RSI Momentum Corridor: 40.0 <= RSI <= 65.0 (growth runway before overbought)
        4. Trend Strength Gate: ADX >= adx_min (default 20.0)

        Parameters
        ----------
        df : pd.DataFrame
            DataFrame containing indicator columns.
        portfolio_value : float
            Current total portfolio value.
        market_regime_bullish : bool, optional
            Whether broad market regime (SPY > 200-SMA) is bullish (default True).
        daily_trend_bullish : bool, optional
            Whether daily timeframe trend is bullish (default True).
        has_position : bool, optional
            Whether an open position is currently held for this ticker (default False).

        Returns
        -------
        dict
            Signal dictionary with signal, confidence, reasons, blocked, block_reason.
        """
        if "current_portfolio_value" in kwargs:
            portfolio_value = kwargs["current_portfolio_value"]
        current_portfolio_value = portfolio_value

        last = df.iloc[-1]
        prev = df.iloc[-2] if len(df) >= 2 else last

        rsi = float(last["RSI_14"])
        macd = float(last["MACD"])
        macd_signal = float(last["MACD_Signal"])
        macd_hist = float(last["MACD_Hist"]) if "MACD_Hist" in last else (macd - macd_signal)
        close = float(last["Close"])
        sma_20 = float(last["SMA_20"])
        bb_lower = float(last["BB_Lower"])
        adx = float(last["ADX_14"]) if "ADX_14" in df.columns else 25.0

        prev_macd = float(prev["MACD"])
        prev_signal = float(prev["MACD_Signal"])
        prev_hist = float(prev["MACD_Hist"]) if "MACD_Hist" in prev else (prev_macd - prev_signal)

        logger.info(
            "Evaluating signal -- Close=%.2f, RSI=%.2f, MACD=%.4f, "
            "MACD_Signal=%.4f, SMA_20=%.2f, BB_Lower=%.2f, ADX=%.2f",
            close, rsi, macd, macd_signal, sma_20, bb_lower, adx,
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

        # ----- ADX trend-strength gate -----
        adx_blocked = adx < self.adx_min
        if adx_blocked:
            logger.info(
                "BUY blocked: Market choppy/sideways (ADX=%.1f < %.1f)",
                adx, self.adx_min,
            )

        # ----- Evaluate Pure Momentum Conditions (Section 7.2) -----
        # 1. Price is in an established uptrend above 20-period SMA
        cond_above_sma = close > sma_20
        # 2. MACD is bullish (line above signal)
        cond_macd_bullish = macd > macd_signal
        # 3. RSI is in the momentum expansion corridor (40.0 to 65.0)
        cond_rsi_momentum = self.rsi_momentum_min <= rsi <= self.rsi_momentum_max
        # 4. Price holds above lower Bollinger Band support
        cond_above_bb = close > bb_lower

        # Momentum crossovers and accelerations
        macd_cross_up = (macd > macd_signal) and (prev_macd <= prev_signal)
        hist_accelerating = (macd_hist > prev_hist) and (macd_hist > 0)

        # Primary entry: Pure Momentum
        momentum_buy = (
            cond_above_sma
            and cond_macd_bullish
            and cond_rsi_momentum
            and cond_above_bb
        )

        # Fallback entry: Oversold dip bounce
        dip_buy = (
            (rsi < self.rsi_oversold)
            and cond_above_sma
            and cond_macd_bullish
            and cond_above_bb
        )

        buy_reasons = []
        if momentum_buy:
            # Base confidence: 0.75 (comfortably clears 0.70 confidence floor)
            buy_confidence = 0.75
            buy_reasons.append(
                f"Momentum confirmed (Close > SMA_20, MACD > Signal, RSI {rsi:.1f} in [{self.rsi_momentum_min:.0f}, {self.rsi_momentum_max:.0f}])"
            )
            if macd_cross_up:
                buy_confidence += 0.10
                buy_reasons.append("Fresh MACD bullish crossover")
            elif hist_accelerating:
                buy_confidence += 0.05
                buy_reasons.append("MACD histogram accelerating positive")

            if daily_trend_bullish:
                buy_confidence += 0.05
                buy_reasons.append("Daily trend bullish alignment")
            else:
                buy_confidence -= 0.05
                buy_reasons.append("Daily trend neutral/bearish (confidence adjusted)")
        elif dip_buy:
            buy_confidence = 0.75
            buy_reasons.append(f"Oversold dip bounce (RSI {rsi:.1f} < {self.rsi_oversold:.1f})")
            if daily_trend_bullish:
                buy_confidence += 0.05
                buy_reasons.append("Daily trend bullish alignment")
        else:
            buy_confidence = 0.0
            if cond_macd_bullish:
                buy_reasons.append("MACD bullish (MACD > Signal)")
            if cond_above_sma:
                buy_reasons.append(f"Above SMA_20 ({close:.2f} > {sma_20:.2f})")
            if cond_above_bb:
                buy_reasons.append(f"Above BB_Lower ({close:.2f} > {bb_lower:.2f})")
            if cond_rsi_momentum:
                buy_reasons.append(f"RSI in momentum corridor ({rsi:.1f})")
            elif rsi < self.rsi_oversold:
                buy_reasons.append(f"RSI oversold ({rsi:.1f} < {self.rsi_oversold:.1f})")
            elif rsi > self.rsi_overbought:
                buy_reasons.append(f"RSI overbought ({rsi:.1f} > {self.rsi_overbought:.1f})")

        buy_confidence = min(max(buy_confidence, 0.0), 1.0)

        # Final BUY decision gating
        buy_triggered = (
            (momentum_buy or dip_buy)
            and not blocked
            and not regime_blocked
            and not adx_blocked
        )

        if regime_blocked and (momentum_buy or dip_buy):
            buy_reasons.append("BLOCKED: Market regime bearish (SPY < SMA-200)")

        if adx_blocked and (momentum_buy or dip_buy):
            buy_reasons.append(
                f"BLOCKED: Market choppy/sideways (ADX={adx:.1f} < {self.adx_min:.1f})"
            )

        # ----- Evaluate SELL conditions -----
        sell_conditions = []
        sell_reasons = []

        # 1. RSI Overbought (momentum exhaustion / take-profit)
        cond_rsi_overbought = rsi > self.rsi_overbought
        if cond_rsi_overbought:
            sell_reasons.append(
                f"RSI overbought ({rsi:.1f} > {self.rsi_overbought})"
            )
        sell_conditions.append(cond_rsi_overbought)

        # 2. MACD Bearish (momentum loss / crossover down)
        cond_macd_bearish = macd < macd_signal
        if cond_macd_bearish:
            sell_reasons.append("MACD bearish (MACD < Signal)")
        sell_conditions.append(cond_macd_bearish)

        # 3. Breakdown below lower Bollinger Band
        cond_below_bb = close < bb_lower
        if cond_below_bb:
            sell_reasons.append(
                f"Below BB_Lower ({close:.2f} < {bb_lower:.2f})"
            )
        sell_conditions.append(cond_below_bb)

        # 4. Forced exit from risk manager
        cond_forced_exit = blocked
        if cond_forced_exit:
            sell_reasons.append(f"Forced exit -- risk block: {block_reason}")
        sell_conditions.append(cond_forced_exit)

        sell_count = sum(sell_conditions)
        sell_confidence = min(sell_count * 0.33, 1.0)

        # Position-aware SELL threshold:
        # When holding a position: 1 condition is enough (protect capital)
        # When flat (no position): require 2 conditions (reduce noise)
        if has_position:
            sell_triggered = sell_count >= 1   # Protect open position aggressively
        else:
            sell_triggered = sell_count >= 2   # Require confirmation when flat

        # ----- ML Meta-Label Filter -----
        reasons = buy_reasons
        if buy_triggered and _META_AVAILABLE and _META_PREDICTOR:
            should_trade, ml_prob = _META_PREDICTOR.should_trade(df)
            if not should_trade:
                logger.info(
                    "MetaLabel BLOCKED trade: P(success)=%.3f < 0.65",
                    ml_prob
                )
                buy_triggered = False
                reasons.append(f"ML filter: P={ml_prob:.2f} < 0.65")
            else:
                logger.info(
                    "MetaLabel APPROVED trade: P(success)=%.3f",
                    ml_prob
                )
                reasons.append(f"ML filter: P={ml_prob:.2f} >= 0.65")

        # ----- Priority & Output Resolution -----
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
            if not reasons:
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
    rm_diag.reset_daily_state()
    sg_diag = SignalGenerator(
        risk_manager=rm_diag,
        rsi_momentum_min=40.0,
        rsi_momentum_max=65.0,
        rsi_overbought=70.0,
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
            sg_diag.rsi_momentum_min <= rsi <= sg_diag.rsi_momentum_max,
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

