"""Append-only experiment provenance, retaining unsuccessful evaluations."""
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def record(path, specification, outcome):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    item={'recorded_at':datetime.now(timezone.utc).isoformat(),
          'revision':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
          'specification':specification,'outcome':outcome}
    item['specification_sha256']=hashlib.sha256(json.dumps(specification,sort_keys=True).encode()).hexdigest()
    with path.open('a',encoding='utf-8') as stream: stream.write(json.dumps(item,sort_keys=True)+'\n')
    return item
