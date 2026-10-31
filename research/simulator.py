"""Long-only event simulator: decisions at close, executions at next open.

OHLC ambiguity uses stop-first. Costs are explicit assumptions, not measured fills.
Partial exits supported through target quantities. No leverage or short inventory.
"""
from dataclasses import dataclass
import math
import pandas as pd


@dataclass(frozen=True)
class Costs:
    spread_bps: float = 2.0
    slippage_bps: float = 3.0
    fee_per_share: float = 0.005

    def __post_init__(self):
        if any(not math.isfinite(v) or v < 0 for v in vars(self).values()):
            raise ValueError('Costs must be finite and nonnegative')

    def price(self, price, buy):
        impact = (self.spread_bps / 2 + self.slippage_bps) / 10000
        return price * (1 + impact if buy else 1 - impact)


def validate_bars(bars):
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError('Timezone-aware bar-close index required')
    if bars.index.has_duplicates or not bars.index.is_monotonic_increasing:
        raise ValueError('Duplicate or unsorted bars')
    if len(bars) < 2:
        raise ValueError('At least two bars required')
    values = bars[['Open', 'High', 'Low', 'Close', 'Volume']]
    if values.isna().any().any() or not values.apply(lambda column: column.map(math.isfinite)).all().all():
        raise ValueError('Nonfinite market data')
    if (values[['Open','High','Low','Close']] <= 0).any().any() or (values.Volume < 0).any():
        raise ValueError('Invalid prices or volume')
    if ((values.High < values[['Open','Close','Low']].max(axis=1)) |
        (values.Low > values[['Open','Close','High']].min(axis=1))).any():
        raise ValueError('Inconsistent OHLC')


def simulate(bars, decide, initial=100000., costs=None, flat_daily=False):
    """decide(prefix, qty, equity) returns target_qty/stop_distance/target_distance.

    Decisions only receive completed prefixes. Last-bar decisions remain unfilled.
    Intraday input must include is_session_end from an exchange calendar; all
    bars must carry their close timestamp. EOD exits model a scheduled close fill.
    """
    validate_bars(bars)
    if not math.isfinite(initial) or initial <= 0:
        raise ValueError('Invalid initial capital')
    if flat_daily and 'is_session_end' not in bars:
        raise ValueError('Explicit exchange-calendar session ends required')
    costs = costs or Costs()
    cash, qty, basis, fees = initial, 0, 0., 0.
    stop = target = pending = episode = None
    fills, episodes, curve = [], [], []

    def execute(wanted, raw, when, reason):
        nonlocal cash, qty, basis, fees, stop, target, episode
        delta = wanted - qty
        if not delta:
            return
        buy = delta > 0
        price = costs.price(raw, buy)
        count = abs(delta)
        if buy:
            count = min(count, int(cash / (price + costs.fee_per_share)))
        if not count:
            return
        fee = count * costs.fee_per_share
        if buy:
            if qty == 0:
                episode = {'entry_time': str(when), 'gross_pnl': 0., 'fees': 0.}
            basis = (basis * qty + price * count) / (qty + count)
            cash -= price * count + fee
            qty += count
        else:
            episode['gross_pnl'] += (price - basis) * count
            cash += price * count - fee
            qty -= count
        fees += fee
        episode['fees'] += fee
        fills.append(dict(bar_close_time=str(when), execution_phase='open' if reason == 'signal_next_open' else 'close' if reason == 'scheduled_session_close' else 'intrabar_or_gap', side='buy' if buy else 'sell',
                          qty=count, price=price, fee=fee, reason=reason))
        if qty == 0:
            episode.update(exit_time=str(when), net_pnl=episode['gross_pnl']-episode['fees'])
            episodes.append(episode)
            episode = stop = target = None
            basis = 0.

    for i, (when, row) in enumerate(bars.iterrows()):
        if pending is not None:
            old = qty
            execute(pending['target_qty'], row.Open, when, 'signal_next_open')
            if qty and old == 0:
                sd, td = pending.get('stop_distance'), pending.get('target_distance')
                stop = basis - sd if sd else None
                target = basis + td if td else None
            pending = None
        if qty:
            if stop is not None and row.Low <= stop:
                execute(0, min(row.Open, stop), when, 'stop')
            elif target is not None and row.High >= target:
                execute(0, max(row.Open, target), when, 'target')
        if flat_daily and row.is_session_end:
            execute(0, row.Close, when, 'scheduled_session_close')
        equity = cash + qty * row.Close
        curve.append(dict(time=str(when), cash=cash, qty=qty, equity=equity,
                          exposure=qty*row.Close/equity, unrealized=qty*(row.Close-basis)))
        decision = decide(bars.iloc[:i+1].copy(), qty, equity)
        if decision is not None:
            wanted = decision.get('target_qty')
            if not isinstance(wanted, int) or wanted < 0:
                raise ValueError('Target must be a nonnegative integer')
            for key in ('stop_distance','target_distance'):
                value = decision.get(key)
                if value is not None and (not math.isfinite(value) or value <= 0):
                    raise ValueError('Invalid protective distance')
            if not (flat_daily and row.is_session_end):
                pending = decision
    equities = pd.Series([initial] + [r['equity'] for r in curve])
    return dict(curve=curve, fills=fills, episodes=episodes, fees=fees,
                final_equity=curve[-1]['equity'], open_qty=qty,
                return_pct=100*(curve[-1]['equity']/initial-1),
                max_drawdown_pct=float(100*(equities/equities.cummax()-1).min()),
                mean_exposure=sum(r['exposure'] for r in curve)/len(curve),
                pending_unfilled=pending is not None)
