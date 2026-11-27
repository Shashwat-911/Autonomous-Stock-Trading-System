"""Independent public watchdog. Health HTTP 200 alone is not a live session."""
from datetime import datetime, timezone
import json
import urllib.request


def validate(status, now=None):
    now=now or datetime.now(timezone.utc)
    if status.get('execution_owner')!='render': raise ValueError('Wrong execution owner')
    stamp=status.get('market_clock_checked_at')
    if not stamp: raise ValueError('No exchange-clock observation')
    age=(now-datetime.fromisoformat(stamp.replace('Z','+00:00'))).total_seconds()
    if not 0<=age<=180: raise ValueError('Stale exchange-clock observation')
    if status.get('market_clock') not in ('open','closed'): raise ValueError('Unknown market clock')
    if status['market_clock']=='open' and status.get('runner_state') not in ('trading_session_running','starting_session','market_open_too_late'):
        raise ValueError('Market open without an active or explicitly late session')
    return True


if __name__=='__main__':
    with urllib.request.urlopen('https://autonomous-stock-trader.onrender.com/status',timeout=30) as response:
        status=json.load(response)
    validate(status)
    print('Runtime exchange-clock and worker state verified')
