"""Read-only daily research download with broker calendar and source manifest."""
import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import yfinance as yf
from scripts.reconcile_paper_account import PaperReader
from research.simulator import validate_bars


def download(output, start='2015-01-01', end='2025-12-31'):
    output=Path(output); output.mkdir(parents=True,exist_ok=False)
    protocol=json.loads(Path('research/protocol.json').read_text())
    if end >= protocol['prospective_holdout'][0]:
        raise ValueError('Reserved holdout cannot be downloaded by research command')
    calendar=PaperReader().get('/v2/calendar',{'start':start,'end':end})
    expected=[r['date'] for r in calendar]
    for symbol in protocol['universe']:
        df=yf.Ticker(symbol).history(start=start,end='2026-01-01',interval='1d',auto_adjust=True)
        dates=[t.date().isoformat() for t in df.index]
        if dates != expected:
            raise ValueError(f'{symbol}: calendar mismatch; refusing incomplete data')
        df.index=__import__('pandas').DatetimeIndex([datetime.fromisoformat(r['date']+'T'+r['close']).replace(tzinfo=ZoneInfo('America/New_York')) for r in calendar])
        validate_bars(df)
        df.to_csv(output/(symbol+'.csv'))
    (output/'manifest.json').write_text(json.dumps({'source':'yfinance adjusted OHLCV',
        'calendar':'Alpaca calendar', 'retrieved_at':datetime.now().astimezone().isoformat(),
        'limitations':['Retrospectively adjusted history, not point-in-time archived data',
                        'No intraday bid/ask quotes; execution costs are assumptions'],
        'period':[start,end]},indent=2))

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(); p.add_argument('--output',required=True)
    a=p.parse_args(); download(a.output)
