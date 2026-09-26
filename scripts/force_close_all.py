"""
One-time script: force-close ALL open positions regardless of universe membership.
Run this ONCE before Monday's session to start clean.
After running, verify Long Market Value = $0.00 in the output.
"""
import os
import time
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import QueryOrderStatus

load_dotenv()
api_key = os.getenv("ALPACA_API_KEY")
secret_key = os.getenv("ALPACA_SECRET_KEY")

if not api_key or not secret_key:
    raise ValueError("Missing ALPACA_API_KEY or ALPACA_SECRET_KEY in environment.")

client = TradingClient(api_key, secret_key, paper=True)

print("\n--- Step 1: Cancel all open orders ---")
try:
    cancel_responses = client.cancel_orders()
    print(f"  Cancelled {len(cancel_responses)} open orders.")
except Exception as e:
    print(f"  Order cancel failed: {e}")

time.sleep(1)

print("\n--- Step 2: Close ALL positions ---")
try:
    positions = client.get_all_positions()
    if not positions:
        print("  No open positions found.")
    else:
        for p in positions:
            try:
                client.close_position(p.symbol)
                print(f"  Closed: {p.qty}sh {p.symbol} @ ~${float(p.current_price):.2f}")
            except Exception as e:
                print(f"  Failed to close {p.symbol}: {e}")
except Exception as e:
    print(f"  Failed to fetch positions: {e}")

time.sleep(2)

print("\n--- Final account status ---")
account = client.get_account()
print(f"  Equity:            ${float(account.equity):,.2f}")
print(f"  Cash:              ${float(account.cash):,.2f}")
print(f"  Long market value: ${float(account.long_market_value):,.2f}")
print(f"\n  {'OK — ready for Monday.' if float(account.long_market_value) < 1.0 else 'WARNING — positions still open. Run again.'}")
