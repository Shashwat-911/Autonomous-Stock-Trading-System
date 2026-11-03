"""Live startup boundary shared by the runner and restart integration tests."""
import logging

def initialize_live_risk(manager, broker, account):
    clock = broker.get_clock()
    if clock is None:
        raise RuntimeError('Broker clock unavailable; cannot initialize session risk')
    manager.begin_live_session(account['last_equity'], clock.timestamp)
    logging.getLogger(__name__).warning(
        'Session risk readiness: date=%s entries_ready=%s; missing state remains fail-closed',
        manager._session_date, manager.entries_ready)
