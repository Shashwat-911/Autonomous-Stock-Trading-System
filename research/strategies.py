"""Predeclared candidates; no optimizer or automatic deployment."""
import math
from strategy.indicators import add_all_indicators


def cash(prefix, qty, equity):
    return None


def passive(prefix, qty, equity):
    return {'target_qty': int(equity * .95 / prefix.Close.iloc[-1])} if not qty else None


def trend(entry=20, exit=10, risk=.0025, cap=.20):
    def decide(prefix, qty, equity):
        if len(prefix) < max(entry, exit, 15) + 1:
            return None
        last = prefix.iloc[-1]
        previous = prefix.iloc[:-1]
        if qty:
            return {'target_qty': 0} if last.Close < previous.Low.tail(exit).min() else None
        if last.Close <= previous.High.tail(entry).max():
            return None
        tr = prefix.High-prefix.Low
        tr = __import__('pandas').concat([tr, (prefix.High-prefix.Close.shift()).abs(),
                                         (prefix.Low-prefix.Close.shift()).abs()], axis=1).max(axis=1)
        atr = tr.tail(14).mean()
        size = int(min(equity*risk/(2*atr), equity*cap/last.Close))
        return {'target_qty': size, 'stop_distance': 2*atr}
    return decide


def hourly_signal_adapter(generator, regime, daily_trend, max_dollars=3000):
    """Experimental adapter, NOT certified live execution parity.

    regime/daily_trend must be point-in-time callables, never future daily closes.
    The shared signal class is used; broker cooldown/scan timing still require
    separately captured replay inputs before this can establish a live baseline.
    """
    def decide(prefix, qty, equity):
        if len(prefix) < 60:
            return None
        enriched = add_all_indicators(prefix.copy())
        atr = float(enriched.ATR_14.iloc[-1])
        if not math.isfinite(atr) or atr <= 0:
            return None
        signal = generator.generate_signal(enriched, portfolio_value=equity,
                    has_position=qty > 0, market_regime_bullish=regime(prefix.index[-1]),
                    daily_trend_bullish=daily_trend(prefix.index[-1]))
        if signal['signal'] == 'SELL' and qty:
            return {'target_qty': 0}
        if signal['signal'] == 'BUY' and signal['confidence'] >= .70 and not qty:
            price = prefix.Close.iloc[-1]
            return {'target_qty': int(min(equity*.01/(2*atr), equity*.05/price, max_dollars/price)),
                    'stop_distance': 2*atr, 'target_distance': 2.5*atr}
        return None
    return decide
