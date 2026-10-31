"""Offline signal replay. Never places orders; requires matching code revision."""
import argparse,gzip,io,json,subprocess
import pandas as pd
from strategy.signals import SignalGenerator

def replay(payload):
    revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    if payload['revision'] != revision:
        return {'status':'BLOCKED_REVISION_MISMATCH'}
    observed=payload['observed']
    if observed.get('can_trade') is None or not observed.get('signal'):
        return {'status':'INSUFFICIENT_RISK_OR_SIGNAL_EVIDENCE'}
    class RecordedRisk:
        def can_trade(self,*args,**kwargs):
            return observed['can_trade'], 'recorded risk block'
    frame=pd.read_csv(io.StringIO(payload['bars_csv']),index_col=0)
    context=payload['context']
    generator=SignalGenerator(RecordedRisk(),**payload['config']['SIGNAL'])
    signal=generator.generate_signal(frame,has_position=bool(observed.get('position')),
                  market_regime_bullish=context['market_regime_bullish'],
                  daily_trend_bullish=context['daily_trend_bullish'])
    return {'status':'MATCH' if signal['signal']==observed['signal'] and signal['confidence']==observed['confidence'] else 'MISMATCH',
            'replayed':signal,'scope':'signal_only_no_execution_parity_claim'}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('bundle');a=p.parse_args()
    print(json.dumps(replay(json.loads(gzip.decompress(open(a.bundle,'rb').read()))),indent=2))
