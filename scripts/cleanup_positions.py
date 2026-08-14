import sys
import os

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config
from alpaca.trading.client import TradingClient

def main():
    api_key = config.ALPACA["api_key"]
    secret_key = config.ALPACA["secret_key"]
    
    client = TradingClient(api_key, secret_key, paper=True)
    
    monitored_tickers = set(config.TRADING["tickers"])
    
    print("Fetching open positions from Alpaca Paper Account...")
    all_positions = client.get_all_positions()
    print(f"Total open positions found: {len(all_positions)}")
    
    orphaned_positions = [p for p in all_positions if p.symbol not in monitored_tickers]
    print(f"Orphaned legacy positions to liquidate: {len(orphaned_positions)}")
    
    print("\nCanceling all pending open orders...")
    try:
        client.cancel_orders()
        print("  - Pending orders canceled successfully.")
    except Exception as e:
        print(f"  [ERROR] Error canceling orders: {e}")
        
    print("\nLiquidating orphaned positions...")
    success_count = 0
    for pos in orphaned_positions:
        symbol = pos.symbol
        qty = pos.qty
        market_val = float(pos.market_value)
        print(f"  Closing position: {symbol:<5} | Shares: {qty:<6} | Value: ${market_val:,.2f}")
        try:
            client.close_position(symbol)
            success_count += 1
        except Exception as e:
            print(f"    [ERROR] Error closing {symbol}: {e}")
            
    print(f"\nLiquidation complete: Successfully submitted sell orders for {success_count}/{len(orphaned_positions)} positions.")
    
    account = client.get_account()
    equity = float(account.equity)
    cash = float(account.cash)
    lmv = float(account.long_market_value)
    heat_pct = (lmv / equity) * 100 if equity > 0 else 0.0
    
    print("\n--- Account Status Post-Cleanup ---")
    print(f"Equity:             ${equity:,.2f}")
    print(f"Cash Available:     ${cash:,.2f}")
    print(f"Long Market Value:  ${lmv:,.2f}")
    print(f"Portfolio Heat:     {heat_pct:.1f}% (Limit: {config.RISK.get('max_portfolio_heat_pct', 0.60)*100:.1f}%)")

if __name__ == "__main__":
    main()
