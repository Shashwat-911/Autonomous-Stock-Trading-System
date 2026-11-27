"""Immutable daily shadow observations; no broker orders or live account positions."""
import json
import hashlib
from pathlib import Path
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import pandas as pd
import yfinance as yf
from scripts.reconcile_paper_account import PaperReader
from research.simulator import simulate, validate_bars, Costs
from research.strategies import trend
from research.gates import evaluate


def advance(folder, now=None, protocol_path="research/protocol.json"):
    now=now or datetime.now(timezone.utc)
    protocol=json.loads(Path(protocol_path).read_text())
    start=protocol["prospective_holdout"][0]
    day=now.astimezone(ZoneInfo('America/New_York')).date()
    root=Path(folder); root.mkdir(parents=True,exist_ok=True)
    calendar=PaperReader().get('/v2/calendar',{'start':(day-timedelta(days=100)).isoformat(),'end':day.isoformat()})
    completed=[r for r in calendar if datetime.fromisoformat(r['date']+'T'+r['close']).replace(tzinfo=ZoneInfo('America/New_York')) < now]
    if not completed: return
    session=completed[-1]['date']
    if session < start:
        (root/'status.json').write_text(json.dumps({'status':'WAITING_FOR_START','start':start})); return
    identity=hashlib.sha256(b''.join(Path(p).read_bytes() for p in [protocol_path,'research/strategies.py','research/simulator.py','research/shadow.py'])).hexdigest()
    previous=json.loads((root/'state.json').read_text()) if (root/'state.json').exists() else None
    if previous and previous.get('identity') != identity:
        raise ValueError('Experiment code or protocol changed; explicit new registration required')
    if previous and previous['last_session']==session: return
    if previous and (len(completed)<2 or completed[-2]['date'] != previous['last_session']):
        raise ValueError('Missed shadow observation; refusing retrospective backfill')
    if not previous and session != start:
        raise ValueError('Missed initial session; requires explicitly registered new experiment')
    frames={}
    for symbol in protocol['universe']:
        path=(root/previous['last_session']/(symbol+'.csv')) if previous else root/(symbol+'.csv')
        fresh=yf.Ticker(symbol).history(start=(day-timedelta(days=100)).isoformat(),end=(day+timedelta(days=1)).isoformat(),auto_adjust=False)
        by_date={t.date().isoformat():row for t,row in fresh.iterrows()}
        wanted=[completed[-1]] if previous else completed[-61:]
        rows=[]; times=[]
        for item in wanted:
            row=by_date[item['date']]
            if row.get('Stock Splits',0): raise ValueError('Corporate action requires review')
            rows.append(row[['Open','High','Low','Close','Volume']])
            times.append(datetime.fromisoformat(item['date']+'T'+item['close']).replace(tzinfo=ZoneInfo('America/New_York')))
        new=pd.DataFrame(rows,index=pd.DatetimeIndex(times))
        if previous:
            old=pd.read_csv(path,index_col=0); old.index=pd.to_datetime(old.index,utc=True)
            new.index=new.index.tz_convert('UTC'); new=pd.concat([old,new])
        validate_bars(new); frames[symbol]=new
    results={}
    for symbol,frame in frames.items():
        candidate=trend(entry=protocol['candidate']['entry_days'],exit=protocol['candidate']['exit_days'],cap=.95)
        def decision(prefix,qty,equity):
            if prefix.index[-1].date().isoformat() < start: return None
            return candidate(prefix,qty,equity)
        results[symbol]=simulate(frame,decision,initial=100000/len(protocol['universe']),costs=Costs(**protocol['costs']))
    # Write new generation first; state pointer is the final commit marker.
    import tempfile, os
    generation=Path(tempfile.mkdtemp(prefix='.pending-',dir=root))
    for symbol,frame in frames.items(): frame.to_csv(generation/(symbol+'.csv'))
    summary={'last_session':session,'kind':'SIMULATED_PRICE_ONLY_SHADOW','dividends':'not included',
             'equity':sum(r['final_equity'] for r in results.values()),'results':results,
             'promotion':evaluate({},cannot_promote_before=protocol['cannot_promote_before'])}
    (generation/'result.json').write_text(json.dumps(summary,indent=2,default=lambda v: v.item()))
    destination=root/session
    if destination.exists():
        # A prior crash may have completed the generation but not its pointer.
        if (destination/'result.json').read_bytes() != (generation/'result.json').read_bytes():
            raise ValueError('Existing generation differs; manual recovery required')
    else:
        os.replace(generation,destination)
    pointer=root/'state.pending.json'
    pointer.write_text(json.dumps({'last_session':session,'identity':identity},indent=2))
    os.replace(pointer,root/'state.json')
    (root/'status.json').write_text(json.dumps({k:v for k,v in summary.items() if k!='results'},indent=2,default=lambda v: v.item()))

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--protocol',default='research/protocol.json')
    a=p.parse_args();advance(a.output,protocol_path=a.protocol)
