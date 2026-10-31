"""Private replay bundles. Upload only to a verified private repository."""
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
import queue
import threading
import urllib.request
import uuid
from datetime import datetime, timezone

REPOSITORY='Shashwat-911/Autonomous-Stock-Trading-Evidence'
ROOT=Path('outputs/reporting_private/replay')
_tasks=queue.Queue()
_started=False
_lock=threading.Lock()


def upload(path):
    token=os.environ.get('GIT_TOKEN')
    if not token: raise RuntimeError('Private evidence token unavailable')
    headers={'Authorization':'Bearer '+token,'User-Agent':'private-replay','Accept':'application/vnd.github+json'}
    endpoint='https://api.github.com/repos/'+REPOSITORY
    with urllib.request.urlopen(urllib.request.Request(endpoint,headers=headers),timeout=20) as response:
        repository=json.load(response)
    if repository.get('private') is not True:
        raise RuntimeError('Evidence destination is not private')
    content=path.read_bytes()
    data=json.dumps({'message':'archive replay '+path.stem,
                    'content':base64.b64encode(content).decode()}).encode()
    request=urllib.request.Request(endpoint+'/contents/bundles/'+path.name,data=data,headers=headers,method='PUT')
    with urllib.request.urlopen(request,timeout=30) as response:
        if response.status not in (200,201): raise RuntimeError('Evidence upload failed')
    path.with_suffix(path.suffix+'.uploaded').touch()


def worker():
    import logging,time
    while True:
        path=_tasks.get()
        for attempt in range(3):
            try:
                upload(path); break
            except Exception:
                logging.getLogger(__name__).error('Private replay upload failed; local evidence retained')
                time.sleep(2**attempt)
        _tasks.task_done()


def archive(symbol, frame, tick, context):
    global _started
    import config
    ROOT.mkdir(parents=True,exist_ok=True)
    payload={'schema':1,'recorded_at':datetime.now(timezone.utc).isoformat(),
        'revision':os.getenv('RENDER_GIT_COMMIT') or os.getenv('GITHUB_SHA','unknown'),
        'symbol':symbol,'bars_csv':frame.to_csv(),'context':context,
        'observed':{k:tick.get(k) for k in ('signal','action','confidence','price','can_trade','position','trade')},
        'config':{k:getattr(config,k) for k in ('SIGNAL','RISK','TRADING','BRACKET','MARKET_REGIME')},
        'scope':'signal_inputs_and_result_not_full_order_lifecycle'}
    raw=json.dumps(payload,default=str,sort_keys=True).encode()
    path=ROOT/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex+'.json.gz')
    path.write_bytes(gzip.compress(raw))
    with _lock:
        if not _started:
            threading.Thread(target=worker,daemon=True).start(); _started=True
            for pending in ROOT.glob('*.json.gz'):
                if not pending.with_suffix(pending.suffix+'.uploaded').exists(): _tasks.put(pending)
        else: _tasks.put(path)
    return hashlib.sha256(raw).hexdigest()
