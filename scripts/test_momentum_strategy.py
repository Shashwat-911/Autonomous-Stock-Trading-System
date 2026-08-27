import sys, os
sys.path.insert(0, os.path.abspath('.'))
import pandas as pd
import numpy as np
from data.fetcher import get_historical_data
from strategy.indicators import add_all_indicators
import logging
logging.disable(logging.CRITICAL)

def test_momentum_strategy(ticker, start, end, 
                           initial_balance=100000):
    df = get_historical_data(ticker, start, end, '1d')
    df = add_all_indicators(df)
    df = df.dropna()
    
    cash = initial_balance
    shares = 0
    entry_price = 0
    trades = []
    
    for i in range(1, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i-1]
        price = float(row['Close'])
        date = df.index[i].strftime('%Y-%m-%d')
        
        # BUY conditions
        macd_cross_up = (float(row['MACD']) > float(row['MACD_Signal']) and 
                         float(prev['MACD']) <= float(prev['MACD_Signal']))
        above_sma = float(row['Close']) > float(row['SMA_20'])
        rsi_ok = 40 <= float(row['RSI_14']) <= 65
        
        # SELL conditions  
        macd_cross_down = (float(row['MACD']) < float(row['MACD_Signal']) and 
                           float(prev['MACD']) >= float(prev['MACD_Signal']))
        rsi_overbought = float(row['RSI_14']) > 70
        stop_loss = shares > 0 and price < entry_price * 0.96
        
        if shares == 0 and macd_cross_up and above_sma and rsi_ok:
            # BUY
            max_spend = min(cash * 0.10, 2000)
            shares = int(max_spend / price)
            if shares > 0:
                cost = shares * price
                cash -= cost
                entry_price = price
                trades.append({
                    'date': date, 'action': 'BUY',
                    'price': price, 'shares': shares,
                    'portfolio': cash + shares * price
                })
        
        elif shares > 0 and (macd_cross_down or rsi_overbought or stop_loss):
            # SELL
            revenue = shares * price
            pnl = (price - entry_price) * shares
            cash += revenue
            trades.append({
                'date': date, 'action': 'SELL',
                'price': price, 'shares': shares,
                'pnl': pnl,
                'portfolio': cash,
                'reason': 'stop_loss' if stop_loss else 
                          'rsi_high' if rsi_overbought else 'macd_cross'
            })
            shares = 0
            entry_price = 0
    
    # Close any open position
    if shares > 0:
        final_price = float(df.iloc[-1]['Close'])
        revenue = shares * final_price
        pnl = (final_price - entry_price) * shares
        cash += revenue
        trades.append({
            'date': df.index[-1].strftime('%Y-%m-%d'),
            'action': 'SELL (end)',
            'price': final_price, 'shares': shares,
            'pnl': pnl, 'portfolio': cash,
            'reason': 'end_of_period'
        })
    
    total_return = ((cash - initial_balance) / initial_balance) * 100
    wins = [t for t in trades if t.get('pnl', 0) > 0]
    losses = [t for t in trades if t.get('pnl', 0) < 0]
    sell_trades = [t for t in trades if 'SELL' in t['action']]
    
    return {
        'ticker': ticker,
        'period': f'{start} to {end}',
        'total_return': round(total_return, 2),
        'final_equity': round(cash, 2),
        'total_trades': len(sell_trades),
        'wins': len(wins),
        'losses': len(losses),
        'win_rate': round(len(wins)/len(sell_trades)*100, 1) 
                   if sell_trades else 0,
        'trades': trades
    }

# Test on multiple tickers and periods
print("=" * 60)
print("MOMENTUM STRATEGY WALK-FORWARD VALIDATION")
print("Buy: MACD cross up + above SMA + RSI 40-65")
print("Sell: MACD cross down OR RSI > 70 OR stop-loss -4%")
print("=" * 60)

test_cases = [
    ("NVDA", "2023-01-01", "2024-01-01"),
    ("NVDA", "2024-01-01", "2025-01-01"),
    ("NVDA", "2025-01-01", "2026-01-01"),
    ("AAPL", "2023-01-01", "2024-01-01"),
    ("MSFT", "2023-01-01", "2024-01-01"),
]

all_results = []
for ticker, start, end in test_cases:
    result = test_momentum_strategy(ticker, start, end)
    all_results.append(result)
    print(f"\n{ticker} | {result['period']}")
    print(f"  Return:     {result['total_return']:+.2f}%")
    print(f"  Trades:     {result['total_trades']}")
    print(f"  Win rate:   {result['win_rate']:.1f}%")
    print(f"  Wins/Loss:  {result['wins']}/{result['losses']}")
    
    if result['trades']:
        print("  Trade log:")
        for t in result['trades'][-6:]:
            pnl = t.get('pnl', 0)
            reason = t.get('reason', '')
            print(f"    {t['date']} {t['action']:8} @ "
                  f"${t['price']:.2f} | "
                  f"PnL: ${pnl:+.2f} | {reason}")

print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
profitable = [r for r in all_results if r['total_return'] > 0]
print(f"Profitable periods: {len(profitable)}/{len(all_results)}")
avg_return = sum(r['total_return'] for r in all_results) / len(all_results)
print(f"Average return:     {avg_return:+.2f}%")
total_trades = sum(r['total_trades'] for r in all_results)
print(f"Total trades:       {total_trades}")
