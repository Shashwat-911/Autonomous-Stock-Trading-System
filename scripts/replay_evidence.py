"""Read private bundles locally and publish only aggregate replay outcomes."""
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from analytics.decision_trace import replay_tick


def evaluate(folder):
    counts=Counter()
    for path in Path(folder).rglob('*.json.gz'):
        try:
            payload=json.loads(gzip.decompress(path.read_bytes()))
            result=replay_tick(payload) if payload.get('schema')==2 else {'status':'LEGACY_SIGNAL_ONLY'}
            counts[result['status']]+=1
        except Exception:
            counts['INVALID_BUNDLE']+=1
    return {'outcomes':dict(counts),'total':sum(counts.values()),
            'scope':'recorded_decision_parity_only','promotion_eligible':False}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--bundles',required=True);p.add_argument('--output',required=True)
    a=p.parse_args(); result=evaluate(a.bundles)
    Path(a.output).write_text(json.dumps(result,indent=2))
    if result['outcomes'].get('MISMATCH') or result['outcomes'].get('INVALID_BUNDLE'):
        raise SystemExit('Replay mismatch or invalid evidence; review required')
