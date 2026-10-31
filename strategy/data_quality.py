"""Required daily trend evidence. Unknown must not grant entry permission."""
import math

def daily_trend(frame):
    if frame is None or len(frame) < 20 or 'Close' not in frame:
        return None
    values=frame['Close'].tail(20)
    if not all(math.isfinite(float(v)) and float(v)>0 for v in values):
        return None
    return bool(values.iloc[-1] > values.mean())
