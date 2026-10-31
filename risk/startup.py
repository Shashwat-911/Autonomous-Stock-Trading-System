"""Live startup boundary shared by the runner and restart integration tests."""
def initialize_live_risk(manager, broker, account):
    clock = broker.get_clock()
    if clock is None:
        raise RuntimeError('Broker clock unavailable; cannot initialize session risk')
    manager.begin_live_session(account['last_equity'], clock.timestamp)
