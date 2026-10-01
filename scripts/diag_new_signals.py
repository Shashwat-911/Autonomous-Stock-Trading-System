import pandas as pd, numpy as np
from strategy.signals import SignalGenerator
from risk.manager import RiskManager
from strategy.indicators import add_all_indicators
import yfinance as yf

tickers_to_test = ["NVDA", "GOOGL", "AAPL", "META", "MSFT"]

rm = RiskManager(initial_balance=100000.0)
sg = SignalGenerator(rm)

for ticker in tickers_to_test:
    df = yf.Ticker(ticker).history(period="30d", interval="1h")
    df = add_all_indicators(df)
    result = sg.generate_signal(df, 100000.0)

    last = df.iloc[-1]
    print(f"\n{'='*60}")
    print(f"  {ticker}")
    print(f"{'='*60}")
    print(f"  Signal:     {result['signal']} (conf={result['confidence']:.2f})")
    print(f"  Close:      {float(last['Close']):.2f}")
    print(f"  SMA_20:     {float(last['SMA_20']):.2f}  | above: {float(last['Close']) > float(last['SMA_20'])}")
    print(f"  RSI_14:     {float(last['RSI_14']):.2f}  | in [40,65]: {40.0 <= float(last['RSI_14']) <= 65.0}")
    print(f"  MACD:       {float(last['MACD']):.4f}  | > Signal: {float(last['MACD']) > float(last['MACD_Signal'])}")
    print(f"  MACD_Sig:   {float(last['MACD_Signal']):.4f}")
    print(f"  BB_Lower:   {float(last['BB_Lower']):.2f}  | above: {float(last['Close']) > float(last['BB_Lower'])}")
    print(f"  ADX_14:     {float(last['ADX_14']):.2f}  | >= 20: {float(last['ADX_14']) >= 20.0}")
    print(f"  All 4 conds: {float(last['Close']) > float(last['SMA_20']) and float(last['MACD']) > float(last['MACD_Signal']) and 40.0 <= float(last['RSI_14']) <= 65.0 and float(last['Close']) > float(last['BB_Lower'])}")
    print(f"  Reasons:    {result['reasons']}")
