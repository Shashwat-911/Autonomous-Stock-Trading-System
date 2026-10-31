"""Attribute episodes from private execution evidence; never infer missing causes."""
from analytics.measurement import position_episodes, day_of as ny_date
from scripts.reconciliation import flatten_orders, timestamp


def attribute(snapshot, start='2026-10-19', end='2026-10-30'):
    episodes, unfinished = position_episodes(snapshot['activities'])
    orders = {o['id']: o for o in flatten_orders(snapshot['orders'])}
    result = []
    for ep in episodes:
        if not start <= ny_date(ep['exit_time']) <= end:
            continue
        fills = [f for f in snapshot['activities'] if f.get('activity_type') == 'FILL'
                 and f['symbol'] == ep['ticker']
                 and timestamp(ep['entry_time']) <= timestamp(f['transaction_time']) <= timestamp(ep['exit_time'])]
        exits = [f for f in fills if f['side'].lower() in ('sell','sell_short')]
        reasons = set()
        for f in exits:
            order = orders.get(f['order_id'], {})
            kind = order.get('type', '')
            client = order.get('client_order_id', '').lower()
            if kind in ('stop','stop_limit','trailing_stop'):
                reasons.add('broker_stop')
            elif kind == 'limit' and order.get('parent_order_id'):
                reasons.add('bracket_limit_target')
            elif 'eod' in client:
                reasons.add('eod_client_id')
            else:
                reasons.add('unknown')
        result.append(dict(**ep, overnight=ny_date(ep['entry_time']) != ny_date(ep['exit_time']),
                           exit_evidence=sorted(reasons), entry_version='unknown',
                           entry_signal='unknown', quote_slippage='unknown',
                           evidence_scope='order_type_or_explicit_client_id_only',
                           order_ids=sorted({f['order_id'] for f in fills})))
    return result, unfinished

if __name__ == '__main__':
    import argparse
    import json
    from pathlib import Path
    from collections import Counter
    from decimal import Decimal
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot',required=True)
    parser.add_argument('--private-output',required=True)
    parser.add_argument('--summary',required=True)
    args=parser.parse_args()
    rows,unfinished=attribute(json.loads(Path(args.snapshot).read_text()))
    Path(args.private_output).write_text(json.dumps(rows,indent=2))
    summary={'episodes':len(rows),'gross_pnl':str(sum((Decimal(r['pnl']) for r in rows),Decimal(0))),
      'overnight_episodes':sum(r['overnight'] for r in rows),
      'exit_evidence':dict(Counter('+'.join(r['exit_evidence']) for r in rows)),
      'unknown_entry_versions':sum(r['entry_version']=='unknown' for r in rows),
      'limitations':['Order type establishes mechanism, not full causal attribution.',
                     'Historical quotes and order-linked decision/version traces unavailable.'],
      'account_mutations':0}
    Path(args.summary).write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))
