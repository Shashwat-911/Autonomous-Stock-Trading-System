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
import urllib.error
import logging
import time
import uuid
from datetime import datetime, timezone

REPOSITORY='Shashwat-911/Autonomous-Stock-Trading-Evidence'
ROOT=Path('outputs/reporting_private/replay')
_tasks=queue.Queue()
_started=False
_lock=threading.Lock()


class EvidenceError(RuntimeError):
    """Safe diagnostic: never include response bodies, URLs, or credentials."""
    def __init__(self, code, retry_after=300):
        super().__init__(code)
        self.retry_after = retry_after


def _request(request):
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        delay = 300 if exc.code in (401, 403, 404, 422) else 60
        try:
            delay = max(delay, int(exc.headers.get('Retry-After', 0)))
        except (TypeError, ValueError, AttributeError):
            pass
        raise EvidenceError('github_http_' + str(exc.code), delay) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise EvidenceError('network_unavailable', 60) from None


def check_configuration():
    if not os.environ.get('GIT_TOKEN', '').strip():
        raise EvidenceError('missing_GIT_TOKEN')


def upload(path):
    check_configuration()
    token=os.environ['GIT_TOKEN'].strip()
    headers={'Authorization':'Bearer '+token,'User-Agent':'private-replay','Accept':'application/vnd.github+json'}
    endpoint='https://api.github.com/repos/'+REPOSITORY
    repository=_request(urllib.request.Request(endpoint,headers=headers))
    if repository.get('private') is not True:
        raise EvidenceError('destination_not_private')
    content=path.read_bytes()
    data=json.dumps({'message':'archive replay '+path.stem,
                    'content':base64.b64encode(content).decode()}).encode()
    request=urllib.request.Request(endpoint+'/contents/bundles/'+path.name,data=data,headers=headers,method='PUT')
    try:
        _request(request)
    except EvidenceError as exc:
        if str(exc) not in ('github_http_409', 'github_http_422'):
            raise
        # A response may have been lost after GitHub committed the first PUT.
        # Accept only identical Git blob content; never overwrite a collision.
        existing = _request(urllib.request.Request(request.full_url, headers=headers))
        digest = hashlib.sha1(b'blob '+str(len(content)).encode()+b'\0'+content).hexdigest()
        if existing.get('sha') != digest:
            raise EvidenceError('remote_content_conflict') from None
    path.with_suffix(path.suffix+'.uploaded').touch()


def worker():
    while True:
        path=_tasks.get()
        while True:
            try:
                upload(path); break
            except Exception as exc:
                code = str(exc) if isinstance(exc, EvidenceError) else type(exc).__name__
                delay = exc.retry_after if isinstance(exc, EvidenceError) else 300
                logging.getLogger(__name__).error(
                    'Private replay upload failed [%s]; local evidence retained; retry in %ss', code, delay)
                time.sleep(delay)
        _tasks.task_done()
        time.sleep(1)  # Pace serialized writes; do not burst the GitHub Contents API.


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
