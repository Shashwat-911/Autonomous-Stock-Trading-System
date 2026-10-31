"""Evidence gates: absent evidence is UNKNOWN, never an approval."""
from datetime import date

def evaluate(evidence, today=None):
    today=today or date.today().isoformat()
    required=['live_replay_parity','positive_net_validation','positive_net_stressed_costs',
              'complete_prospective_holdout','acceptable_drawdown','independent_review']
    checks={key:('PASS' if evidence.get(key) is True else 'FAIL' if evidence.get(key) is False else 'UNKNOWN') for key in required}
    if today < '2027-05-01': checks['complete_prospective_holdout']='UNKNOWN'
    return {'checks':checks,'eligible_for_review':all(v=='PASS' for v in checks.values()),
            'automatic_deployment':False}
