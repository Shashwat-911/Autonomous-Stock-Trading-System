"""Exchange-calendar-aware validation for Yahoo start-labelled bars.

Unknown evidence blocks entries; it must never become a bullish observation.
Calendar rows come from Alpaca, including holidays and shortened sessions.
"""
import math
import pandas as pd


def daily_trend(frame, expected_session=None):
    if frame is None or len(frame) < 20 or 'Close' not in frame:
        return None
    try:
        if expected_session is not None and pd.Timestamp(frame.index[-1]).date().isoformat()!=expected_session:
            return None
        values = frame.Close.tail(20).astype(float)
        if not all(math.isfinite(v) and v > 0 for v in values):
            return None
        return bool(values.iloc[-1] > values.mean())
    except (TypeError, ValueError):
        return None


def completed_bars(frame, calendar, now, interval='1h', grace_seconds=120):
    """Return completed regular-session bars and explicit freshness status.

    No interpolation. A missing expected bar, duplicate, naive timestamp, invalid
    OHLCV or unknown calendar blocks entries. The final bar can be shorter.
    """
    empty = frame.iloc[:0].copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    if frame is None or frame.empty or not calendar:
        return empty, 'UNKNOWN'
    now = pd.Timestamp(now)
    if now.tzinfo is None or not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        return empty, 'UNKNOWN'
    if frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        return empty, 'INVALID'
    duration = pd.Timedelta(interval)
    if duration <= pd.Timedelta(0):
        return empty, 'INVALID'
    expected = []
    closes = {}
    for row in calendar:
        start, end = pd.Timestamp(row['open']), pd.Timestamp(row['close'])
        if start.tzinfo is None or end.tzinfo is None or end <= start:
            return empty, 'UNKNOWN'
        for label in pd.date_range(start, end, freq=duration, inclusive='left'):
            close = min(label + duration, end)
            closes[label] = close
            if close <= now - pd.Timedelta(seconds=grace_seconds):
                expected.append(label)
    if not expected:
        return empty, 'UNKNOWN'
    selected = frame.loc[[t for t in frame.index if t in closes and closes[t] <= now]].copy()
    try:
        values = selected[['Open','High','Low','Close','Volume']].astype(float)
        if selected.empty or not values.map(math.isfinite).all().all():
            return empty, 'INVALID'
        if (values[['Open','High','Low','Close']] <= 0).any().any() or (values.Volume < 0).any():
            return empty, 'INVALID'
        if ((values.High < values[['Open','Low','Close']].max(axis=1)) | (values.Low > values[['Open','High','Close']].min(axis=1))).any():
            return empty, 'INVALID'
    except (KeyError, TypeError, ValueError):
        return empty, 'INVALID'
    required = [t for t in expected if t >= frame.index[0]]
    status = 'FRESH' if required and all(t in selected.index for t in required) else 'STALE'
    return selected, status
