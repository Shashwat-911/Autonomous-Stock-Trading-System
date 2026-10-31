"""Run a reproducible daily comparison from explicit local OHLCV files.
CSV index must be timezone-aware bar CLOSE timestamps. No missing-bar filling.
Daily candidate and passive allocations use separate equal capital sleeves.
Hourly strategy is blocked until point-in-time replay inputs are supplied.
"""
import argparse
import hashlib
import json
from pathlib import Path
import pandas as pd
from research.simulator import simulate, Costs
from research.strategies import cash, passive, trend


def compare(directory, start, end):
    protocol = json.loads(Path('research/protocol.json').read_text())
    if start > end or end >= protocol['prospective_holdout'][0]:
        raise ValueError('Invalid period or reserved holdout access refused')
    sources, frames = {}, {}
    for symbol in protocol['universe']:
        path = Path(directory) / (symbol + '.csv')
        sources[symbol] = hashlib.sha256(path.read_bytes()).hexdigest()
        df = pd.read_csv(path, index_col=0)
        if any(pd.Timestamp(value).tzinfo is None for value in df.index):
            raise ValueError('Naive bar timestamp')
        df.index = pd.to_datetime(df.index, utc=True, errors='raise')
        df = df.loc[start:end]
        frames[symbol] = df
    reference = next(iter(frames.values())).index
    if any(not df.index.equals(reference) for df in frames.values()):
        raise ValueError('Unaligned calendars; resolve missing sessions explicitly')
    output = {'status':'RESEARCH_ONLY', 'source_sha256':sources, 'protocol_sha256':hashlib.sha256(Path('research/protocol.json').read_bytes()).hexdigest(), 'period':[start,end],
              'hourly_baseline': {'status':'BLOCKED_MISSING_LIVE_PARITY_REPLAY'}, 'runs':[]}
    for multiplier in (1, 2, 4):
        costs = Costs(**{k:v*multiplier for k,v in protocol['costs'].items()})
        for name, factory in [('cash',lambda:cash), ('passive',lambda:passive),
                               ('trend_20_10',lambda:trend(cap=.95)),
                               ('sensitivity_15_8',lambda:trend(15,8,cap=.95)),
                               ('sensitivity_25_12',lambda:trend(25,12,cap=.95))]:
            results={symbol:simulate(df,factory(),initial=20000,costs=costs) for symbol,df in frames.items()}
            equity=pd.Series([sum(r['curve'][i]['equity'] for r in results.values()) for i in range(len(reference))])
            equity=pd.concat([pd.Series([100000.]),equity],ignore_index=True)
            output['runs'].append({'candidate':name,'cost_multiplier':multiplier,
                'net_pnl':float(equity.iloc[-1]-100000),
                'max_drawdown_pct':float(100*(equity/equity.cummax()-1).min()),
                'mean_exposure':sum(r['mean_exposure'] for r in results.values())/len(results),
                'completed_episodes':sum(len(r['episodes']) for r in results.values()),
                'calendar_year_net_pnl':{str(year):float(equity.iloc[[i+1 for i,t in enumerate(reference) if t.year==year][-1]]-equity.iloc[[i for i,t in enumerate(reference) if t.year==year][0]]) for year in sorted(set(reference.year))},
                'open_positions':sum(r['open_qty']>0 for r in results.values()),
                'symbol_net_pnl':{s:r['final_equity']-20000 for s,r in results.items()}})
    output['promotion']={'eligible':False,'reasons':['Prospective holdout incomplete',
        'Hourly replay parity unverified','Historical data provenance requires review',
        'Research risk limits have not been approved for live use']}
    return output

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data',required=True)
    p.add_argument('--start',required=True)
    p.add_argument('--end',required=True)
    p.add_argument('--output',required=True)
    a=p.parse_args()
    result=compare(a.data,a.start,a.end)
    Path(a.output).write_text(json.dumps(result,indent=2))
