import pandas as pd
import numpy as np
import yfinance as yf
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from strategy.indicators import add_all_indicators
import logging
logging.disable(logging.CRITICAL)

TICKERS = ["NVDA", "TSLA", "META", "MSFT", "AAPL"]
START = "2019-01-01"
END   = "2026-09-15"
# yfinance caps 1h data at 730 days, so we use daily bars
# for the full 5-year training window (more market regimes).
INTERVAL = "1d"

def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute ML features from indicator-enriched DataFrame.
    Returns feature matrix with no lookahead bias.
    Works with both daily and hourly DataFrames.
    """
    f = pd.DataFrame(index=df.index)
    
    # Price-based features
    f["rsi"] = df["RSI_14"]
    f["rsi_slope"] = df["RSI_14"].diff(3)
    f["macd"] = df["MACD"]
    f["macd_signal"] = df["MACD_Signal"]
    f["macd_hist"] = df["MACD_Hist"]
    f["macd_hist_slope"] = df["MACD_Hist"].diff(3)
    f["bb_pct"] = (df["Close"] - df["BB_Lower"]) / (
        df["BB_Upper"] - df["BB_Lower"]).replace(0, np.nan)
    f["close_vs_sma"] = (df["Close"] - df["SMA_20"]) / df["SMA_20"]
    f["close_vs_ema"] = (df["Close"] - df["EMA_20"]) / df["EMA_20"]
    
    # Volatility features
    f["atr_pct"] = (df["High"] - df["Low"]) / df["Close"]
    f["atr_pct_5"] = f["atr_pct"].rolling(5).mean()
    f["volatility_ratio"] = f["atr_pct"] / f["atr_pct_5"].replace(0, np.nan)
    
    # Volume features  
    f["volume_ratio"] = df["Volume"] / df["Volume"].rolling(20).mean()
    f["volume_spike"] = (f["volume_ratio"] > 2.0).astype(int)
    
    # ADX features
    if "ADX_14" in df.columns:
        f["adx"] = df["ADX_14"]
        f["adx_trending"] = (df["ADX_14"] > 22).astype(int)
        if "DI_plus_14" in df.columns:
            f["di_diff"] = df["DI_plus_14"] - df["DI_minus_14"]
    
    # Momentum features (bar-relative, works for any timeframe)
    f["return_1h"] = df["Close"].pct_change(1)
    f["return_3h"] = df["Close"].pct_change(3)
    f["return_6h"] = df["Close"].pct_change(6)
    f["return_24h"] = df["Close"].pct_change(24)
    
    # Time features (no lookahead)
    if hasattr(df.index, 'hour'):
        f["hour"] = df.index.hour
    else:
        f["hour"] = 12  # default for daily bars
    if hasattr(df.index, 'dayofweek'):
        f["day_of_week"] = df.index.dayofweek
    else:
        f["day_of_week"] = 2
    f["is_morning"] = (f["hour"] <= 11).astype(int)
    f["is_afternoon"] = (f["hour"] >= 14).astype(int)
    
    return f

def generate_labels(df: pd.DataFrame, 
                    tp_pct: float = 0.012,
                    sl_pct: float = 0.008,
                    forward_bars: int = 12) -> pd.Series:
    """
    Binary label: 1 if price hits TP before SL within next N bars.
    This simulates bracket order outcome without lookahead.
    """
    labels = []
    closes = df["Close"].values
    highs = df["High"].values
    lows = df["Low"].values
    
    for i in range(len(closes)):
        entry = closes[i]
        tp = entry * (1 + tp_pct)
        sl = entry * (1 - sl_pct)
        
        label = 0  # default: SL hit or neither
        end = min(i + forward_bars, len(closes))
        
        for j in range(i + 1, end):
            if highs[j] >= tp:
                label = 1  # TP hit first
                break
            if lows[j] <= sl:
                label = 0  # SL hit first
                break
        
        labels.append(label)
    
    return pd.Series(labels, index=df.index)

def build_dataset() -> pd.DataFrame:
    """
    Fetch 5 years of data for all tickers, compute features + labels.
    Returns combined DataFrame ready for training.
    """
    all_dfs = []
    
    for ticker in TICKERS:
        print(f"Fetching {ticker}...")
        try:
            raw = yf.download(
                ticker, start=START, end=END,
                interval=INTERVAL, auto_adjust=True,
                progress=False
            )
            if raw.empty or len(raw) < 100:
                print(f"  Skipping {ticker}: insufficient data ({len(raw)} rows)")
                continue
            
            # Flatten MultiIndex if present
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)
            
            print(f"  {ticker}: fetched {len(raw)} raw bars ({INTERVAL})")
            
            # Add indicators
            df = add_all_indicators(raw)
            df = df.dropna()
            
            # Compute features
            features = compute_features(df)
            
            # Compute labels (no lookahead)
            labels = generate_labels(df, tp_pct=0.012, sl_pct=0.008,
                                     forward_bars=12)
            
            # Combine
            combined = features.copy()
            combined["label"] = labels
            combined["ticker"] = ticker
            combined["close"] = df["Close"]
            
            # Drop rows where features have NaN
            combined = combined.dropna()
            
            print(f"  {ticker}: {len(combined)} samples, "
                  f"win_rate={combined['label'].mean():.1%}")
            all_dfs.append(combined)
            
        except Exception as e:
            print(f"  ERROR {ticker}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    if not all_dfs:
        raise ValueError("No data fetched for any ticker")
    
    combined = pd.concat(all_dfs, axis=0)
    combined = combined.sort_index()
    print(f"\nTotal dataset: {len(combined)} samples")
    print(f"Overall win rate: {combined['label'].mean():.1%}")
    print(f"Feature columns: {[c for c in combined.columns if c not in ['label','ticker','close']]}")
    return combined

if __name__ == "__main__":
    df = build_dataset()
    os.makedirs("ml", exist_ok=True)
    df.to_csv("ml/training_data.csv")
    print(f"\nSaved to ml/training_data.csv")
    print(df.head())
