"""Read-only scheduled research; public summaries only, no trading imports."""
import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import subprocess
from zoneinfo import ZoneInfo
from scripts.reconcile_paper_account import PaperReader, collect
from research.attribution import attribute
from research.download import download
from research.compare import compare


def run(output, weekly=False):
    output=Path(output); output.mkdir(parents=True,exist_ok=True)
    now=datetime.now(timezone.utc)
    day=now.astimezone(ZoneInfo('America/New_York')).date()
    protocol=Path('research/protocol.json').read_bytes()
    status={'observed_at':now.isoformat(), 'git_sha':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            'protocol_sha256':hashlib.sha256(protocol).hexdigest(), 'promotion_eligible':False,
            'limitations':['Historical entry versions and unknown exit reasons cannot be reconstructed',
                          'Prospective holdout incomplete; no replacement is approved']}
    try:
        reader=PaperReader()
        snapshot=collect(reader,day-timedelta(days=30),day)
        rows,_=attribute(snapshot,'2026-10-19',day.isoformat())
        from collections import Counter
        from decimal import Decimal
        status.update(status='OBSERVED_NOT_VALIDATED_STRATEGY',completed_episodes=len(rows),
            gross_pnl=str(sum((Decimal(r['pnl']) for r in rows),Decimal(0))),
            unknown_entry_versions=sum(r['entry_version']=='unknown' for r in rows),
            exit_evidence=dict(Counter('+'.join(r['exit_evidence']) for r in rows)))
        if weekly:
            private=Path('outputs/private_reconciliation')/now.strftime('research_%Y%m%dT%H%M%SZ')
            download(private)
            comparison=compare(private,'2023-01-01','2025-12-31')
            (output/'comparison.json').write_text(json.dumps(comparison,indent=2))
        (output/'status.json').write_text(json.dumps(status,indent=2))
    except Exception as exc:
        status.update(status='FAILED',error_type=type(exc).__name__)
        (output/'status.json').write_text(json.dumps(status,indent=2))
        raise RuntimeError('Research failed; inspect status.json. No promotion permitted.') from None

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--output',required=True); p.add_argument('--weekly',action='store_true')
    a=p.parse_args(); run(a.output,a.weekly)
