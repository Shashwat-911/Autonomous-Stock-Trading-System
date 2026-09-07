"""
verify_fixes.py  -- Quick sanity-check for the two pre-golive fixes.
Run: python scripts/verify_fixes.py
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config
import pandas as pd
from analytics.metrics import PerformanceEngine

PASS = "\033[92m OK \033[0m"
FAIL = "\033[91m FAIL \033[0m"

errors = 0

# ── Fix 1: R:R ratio ─────────────────────────────────────────────────────────
print("=" * 60)
print("  FIX 1 — BRACKET Risk:Reward Ratio")
print("=" * 60)
sl = config.BRACKET["stop_loss_atr_mult"]
tp = config.BRACKET["take_profit_atr_mult"]
rr = tp / sl
print(f"  Stop-loss  mult : {sl}x ATR")
print(f"  Take-profit mult: {tp}x ATR")
print(f"  R:R ratio       : 1:{rr:.2f}")

if rr >= 2.0:
    print(f"  {PASS} R:R is 1:{rr:.2f} — meets 2:1 minimum\n")
else:
    print(f"  {FAIL} R:R is still 1:{rr:.2f} — below 2:1 minimum!\n")
    errors += 1

# ── Fix 2: Metrics bugs ───────────────────────────────────────────────────────
print("=" * 60)
print("  FIX 2 — Metrics Calculation Bugs")
print("=" * 60)

pe = PerformanceEngine()

# 2a: Market orders (price=0) must produce slippage=0.0
market_df = pd.DataFrame([
    {"price": 0.0, "filled_avg_price": 224.76},
    {"price": 0.0, "filled_avg_price": 219.56},
])
result = pe._compute_slippage(market_df)
slippage_val = result["avg_slippage_pct"]
latency_val  = result["avg_execution_latency_ms"]
print(f"  Market-order slippage (expect 0.0): {slippage_val}")
if slippage_val == 0.0:
    print(f"  {PASS} Slippage correctly 0.0 for market orders")
else:
    print(f"  {FAIL} Slippage should be 0.0 but got {slippage_val}")
    errors += 1

print(f"  Market-order latency (expect 0.0):  {latency_val}")
if latency_val == 0.0:
    print(f"  {PASS} Latency correctly 0.0 when timestamps missing")
else:
    print(f"  {FAIL} Latency should be 0.0 but got {latency_val}")
    errors += 1

# 2b: Real timestamps → correct latency (sub-second Alpaca fills)
ts_df = pd.DataFrame([
    {
        "price": 0.0,
        "filled_avg_price": 224.76,
        "submitted_at": "2026-09-02 18:41:45.005797+00:00",
        "filled_at":    "2026-09-02 18:41:46.798643+00:00",   # ~1.79s
    },
    {
        "price": 0.0,
        "filled_avg_price": 219.56,
        "submitted_at": "2026-09-01 16:56:22.236798+00:00",
        "filled_at":    "2026-09-01 16:56:22.830755+00:00",   # ~0.59s
    },
])
result2 = pe._compute_slippage(ts_df)
lat2 = result2["avg_execution_latency_ms"]
print(f"\n  Real-timestamp latency (expect 1000-2000 ms): {lat2:.1f} ms")
if 0 < lat2 < 60_000:
    print(f"  {PASS} Latency {lat2:.0f}ms — within sane range")
else:
    print(f"  {FAIL} Latency {lat2}ms — outside expected range!")
    errors += 1

# 2c: Huge stale latency values must be capped to 0.0
stale_df = pd.DataFrame([
    {
        "price": 0.0,
        "filled_avg_price": 224.76,
        "submitted_at": "2026-08-12 01:00:00+00:00",
        "filled_at":    "2026-08-19 07:18:10+00:00",   # 7 days apart — stale data
    },
])
result3 = pe._compute_slippage(stale_df)
lat3 = result3["avg_execution_latency_ms"]
print(f"\n  Stale-timestamp latency (expect 0.0 after cap): {lat3:.1f} ms")
if lat3 == 0.0:
    print(f"  {PASS} Stale outlier correctly discarded (capped at 60s)")
else:
    print(f"  {FAIL} Stale outlier NOT capped! Got {lat3}ms")
    errors += 1

# ── Summary ───────────────────────────────────────────────────────────────────
print()
print("=" * 60)
if errors == 0:
    print(f"  {PASS} ALL CHECKS PASSED — safe to deploy")
else:
    print(f"  {FAIL} {errors} CHECK(S) FAILED — do NOT deploy until fixed")
print("=" * 60)

sys.exit(errors)
