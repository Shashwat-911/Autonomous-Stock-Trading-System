"""Sanitized decision events for the existing durable stdout archive."""
import hashlib
import json
import os
from datetime import datetime,timezone
import config

def decision_event(symbol, frame, tick, entry_allowed):
    settings={name:getattr(config,name) for name in ('TRADING','SIGNAL','RISK','BRACKET','MARKET_REGIME')}
    return {'event':'decision_v1','observed_at':datetime.now(timezone.utc).isoformat(),
            'revision':os.getenv('RENDER_GIT_COMMIT') or os.getenv('GITHUB_SHA','unknown'),
            'config_sha256':hashlib.sha256(json.dumps(settings,sort_keys=True).encode()).hexdigest(),
            'input_sha256':hashlib.sha256(frame.to_csv().encode()).hexdigest(),
            'last_bar_label':str(frame.index[-1]),'ticker':symbol,
            'signal':tick.get('signal'),'action':tick.get('action'),
            'entry_allowed':bool(entry_allowed),'confidence':tick.get('confidence'),
            'replay_status':'INPUT_HASH_ONLY_NOT_FULL_EXECUTION_REPLAY'}
