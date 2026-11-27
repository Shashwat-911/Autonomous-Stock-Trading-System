"""Predeclared random-entry control for the daily trend candidate.

Same data, capital, ATR sizing, stop and channel exit; permute breakout entry
opportunities within calendar year. Realized trade counts/exposure can differ
because positions overlap. This is not a matched hourly live-strategy control.
"""
import random
import pandas as pd
from research.strategies import trend
from research.simulator import simulate, Costs


def opportunity_mask(frame, entry=20):
    return frame.Close > frame.High.shift(1).rolling(entry).max()


def randomized_trend(frame, seed, risk=.0025, cap=.95):
    mask=opportunity_mask(frame)
    rng=random.Random(seed); selected=set()
    for year in sorted(set(frame.index.year)):
        eligible=[i for i,t in enumerate(frame.index) if t.year==year and i>=20]
        count=sum(bool(mask.iloc[i]) for i in eligible)
        selected.update(rng.sample(eligible,count))
    ordinary=trend(cap=cap,risk=risk)
    def decide(prefix,qty,equity):
        if qty: return ordinary(prefix,qty,equity)
        if len(prefix)-1 not in selected: return None
        tr=pd.concat([prefix.High-prefix.Low,(prefix.High-prefix.Close.shift()).abs(),
                      (prefix.Low-prefix.Close.shift()).abs()],axis=1).max(axis=1)
        atr=tr.tail(14).mean()
        if atr<=0: return None
        return {'target_qty':int(min(equity*risk/(2*atr),equity*cap/prefix.Close.iloc[-1])),
                'stop_distance':2*atr}
    return decide


def compare_random(frames, trials=100, costs=None):
    costs=costs or Costs()
    initial=100000/len(frames)
    def run(factory):
        results=[simulate(df,factory(df),initial=initial,costs=costs) for df in frames.values()]
        return {'net_pnl':sum(r['final_equity']-initial for r in results),
                'completed_episodes':sum(len(r['episodes']) for r in results),
                'mean_exposure':sum(r['mean_exposure'] for r in results)/len(results)}
    candidate=run(lambda df:trend(cap=.95))
    controls=[run(lambda df,seed=seed:randomized_trend(df,seed)) for seed in range(trials)]
    return {'candidate':candidate,'controls':controls,'seeds':list(range(trials)),
        'fraction_controls_at_least_candidate':sum(r['net_pnl']>=candidate['net_pnl'] for r in controls)/trials,
        'scope':'daily_candidate_year_stratified_entry_opportunities',
        'limitations':['Retrospective randomized control, not an online tradable policy',
                      'Opportunity counts matched; realized exposure and episodes may differ',
                      'Not a significance or promotion verdict; daily market observations are dependent'],
        'automatic_promotion':False}
