import logging
import numpy as np
import pandas as pd

# Configure logger for indicators module
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def add_sma(df: pd.DataFrame, window: int = 20, column: str = "Close") -> pd.DataFrame:
    """
    Calculate Simple Moving Average (SMA) and return a new DataFrame with the SMA column.

    Parameters
    ----------
    df : pd.DataFrame
        Input DataFrame containing price data.
    window : int, optional
        Rolling window size for SMA calculation (default is 20).
    column : str, optional
        Target column name (default is 'Close').

    Returns
    -------
    pd.DataFrame
        A new DataFrame with added SMA column (e.g., 'SMA_20').
    """
    logger.info(f"Calculating SMA (window={window}) on column '{column}'.")
    res = df.copy()
    col_name = f"SMA_{window}"
    res[col_name] = res[column].rolling(window=window).mean()
    return res


def add_ema(df: pd.DataFrame, window: int = 20, column: str = "Close") -> pd.DataFrame:
    """
    Calculate Exponential Moving Average (EMA) and return a new DataFrame with the EMA column.

    Parameters
    ----------
    df : pd.DataFrame
        Input DataFrame containing price data.
    window : int, optional
        Exponential moving average span (default is 20).
    column : str, optional
        Target column name (default is 'Close').

    Returns
    -------
    pd.DataFrame
        A new DataFrame with added EMA column (e.g., 'EMA_20').
    """
    logger.info(f"Calculating EMA (window={window}) on column '{column}'.")
    res = df.copy()
    col_name = f"EMA_{window}"
    res[col_name] = res[column].ewm(span=window, adjust=False).mean()
    return res


def add_rsi(df: pd.DataFrame, window: int = 14, column: str = "Close") -> pd.DataFrame:
    """
    Calculate Relative Strength Index (RSI) using Wilder's smoothing method
    and return a new DataFrame with the RSI column.

    Parameters
    ----------
    df : pd.DataFrame
        Input DataFrame containing price data.
    window : int, optional
        Lookback period for RSI calculation (default is 14).
    column : str, optional
        Target column name (default is 'Close').

    Returns
    -------
    pd.DataFrame
        A new DataFrame with added RSI column (e.g., 'RSI_14').
    """
    logger.info(f"Calculating RSI (window={window}) on column '{column}' using Wilder's smoothing.")
    res = df.copy()
    delta = res[column].diff()

    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    # Wilder's exponential smoothing method: alpha = 1 / window
    avg_gain = gain.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    # Handle division by zero when avg_loss is 0
    rsi = rsi.where(avg_loss != 0, 100.0)

    col_name = f"RSI_{window}"
    res[col_name] = rsi
    return res


def add_macd(
    df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9, column: str = "Close"
) -> pd.DataFrame:
    """
    Calculate Moving Average Convergence Divergence (MACD), Signal Line, 
    and MACD Histogram, and return a new DataFrame with MACD, MACD_Signal, and MACD_Hist columns.

    Parameters
    ----------
    df : pd.DataFrame
        Input DataFrame containing price data.
    fast : int, optional
        Fast EMA period (default is 12).
    slow : int, optional
        Slow EMA period (default is 26).
    signal : int, optional
        Signal line EMA period (default is 9).
    column : str, optional
        Target column name (default is 'Close').

    Returns
    -------
    pd.DataFrame
        A new DataFrame with added columns 'MACD', 'MACD_Signal', and 'MACD_Hist'.
    """
    logger.info(f"Calculating MACD (fast={fast}, slow={slow}, signal={signal}) on column '{column}'.")
    res = df.copy()

    ema_fast = res[column].ewm(span=fast, adjust=False).mean()
    ema_slow = res[column].ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    macd_hist = macd_line - signal_line

    res["MACD"] = macd_line
    res["MACD_Signal"] = signal_line
    res["MACD_Hist"] = macd_hist
    return res


def add_bollinger_bands(
    df: pd.DataFrame, window: int = 20, num_std: float = 2.0, column: str = "Close"
) -> pd.DataFrame:
    """
    Calculate Bollinger Bands (Upper, Middle, Lower) and return a new DataFrame 
    with BB_Upper, BB_Middle, and BB_Lower columns.

    Parameters
    ----------
    df : pd.DataFrame
        Input DataFrame containing price data.
    window : int, optional
        Moving average lookback period (default is 20).
    num_std : float, optional
        Number of standard deviations for bands (default is 2.0).
    column : str, optional
        Target column name (default is 'Close').

    Returns
    -------
    pd.DataFrame
        A new DataFrame with added columns 'BB_Upper', 'BB_Middle', and 'BB_Lower'.
    """
    logger.info(f"Calculating Bollinger Bands (window={window}, num_std={num_std}) on column '{column}'.")
    res = df.copy()

    middle_band = res[column].rolling(window=window).mean()
    rolling_std = res[column].rolling(window=window).std()

    res["BB_Middle"] = middle_band
    res["BB_Upper"] = middle_band + (num_std * rolling_std)
    res["BB_Lower"] = middle_band - (num_std * rolling_std)
    return res


def add_atr(
    df: pd.DataFrame, window: int = 14
) -> pd.DataFrame:
    """
    Calculate Average True Range (ATR) and return a new DataFrame with the ATR column.

    ATR measures market volatility using the greatest of:
    - Current High - Current Low
    - abs(Current High - Previous Close)
    - abs(Current Low - Previous Close)

    Parameters
    ----------
    df : pd.DataFrame
        Input DataFrame containing 'High', 'Low', and 'Close' columns.
    window : int, optional
        Smoothing period for ATR (default 14).

    Returns
    -------
    pd.DataFrame
        A new DataFrame with added ATR column (e.g., 'ATR_14').
    """
    logger.info(f"Calculating ATR (window={window}) using High/Low/Close.")
    res = df.copy()

    high = res["High"]
    low = res["Low"]
    prev_close = res["Close"].shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    col_name = f"ATR_{window}"
    res[col_name] = true_range.ewm(
        alpha=1.0 / window, min_periods=window, adjust=False
    ).mean()

    return res


def add_adx(df: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    """
    Calculate Average Directional Index (ADX) using Wilder's smoothing.
    Adds columns: ADX_14, DI_plus_14, DI_minus_14
    """
    logger.info(f"Calculating ADX (window={window}).")
    res = df.copy()

    high = res["High"]
    low = res["Low"]
    close = res["Close"]

    # True Range
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Directional Movement
    dm_plus = high - high.shift(1)
    dm_minus = low.shift(1) - low

    dm_plus = dm_plus.where((dm_plus > dm_minus) & (dm_plus > 0), 0.0)
    dm_minus = dm_minus.where((dm_minus > dm_plus) & (dm_minus > 0), 0.0)

    # Wilder's smoothing (alpha = 1/window)
    alpha = 1.0 / window
    atr_w = tr.ewm(alpha=alpha, min_periods=window, adjust=False).mean()
    dmp_w = dm_plus.ewm(alpha=alpha, min_periods=window, adjust=False).mean()
    dmm_w = dm_minus.ewm(alpha=alpha, min_periods=window, adjust=False).mean()

    # Directional Indicators
    di_plus = 100 * dmp_w / atr_w.replace(0, float('nan'))
    di_minus = 100 * dmm_w / atr_w.replace(0, float('nan'))

    # DX and ADX
    dx = 100 * (di_plus - di_minus).abs() / (di_plus + di_minus).replace(0, float('nan'))
    adx = dx.ewm(alpha=alpha, min_periods=window, adjust=False).mean()

    res[f"ADX_{window}"] = adx
    res[f"DI_plus_{window}"] = di_plus
    res[f"DI_minus_{window}"] = di_minus
    return res


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convenience function to calculate and append all technical indicators
    (SMA, EMA, RSI, MACD, Bollinger Bands, ATR, ADX) using default parameters.

    Parameters
    ----------
    df : pd.DataFrame
        Input DataFrame containing historical price data.

    Returns
    -------
    pd.DataFrame
        A new DataFrame with all indicator columns added.
    """
    logger.info("Calculating all technical indicators with default parameters.")
    res = df.copy()
    res = add_sma(res, window=20)
    res = add_ema(res, window=20)
    res = add_rsi(res, window=14)
    res = add_macd(res, fast=12, slow=26, signal=9)
    res = add_bollinger_bands(res, window=20, num_std=2)
    res = add_atr(res, window=14)
    res = add_adx(res, window=14)
    return res


if __name__ == "__main__":
    import os
    import sys

    # Add workspace root directory to Python path
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from data.fetcher import get_historical_data

    ticker = "MSFT"
    start_date = "2024-01-01"
    end_date = "2024-06-01"

    print(f"Fetching historical data for '{ticker}'...")
    raw_df = get_historical_data(ticker=ticker, start_date=start_date, end_date=end_date, interval="1d")

    print("\nCalculating technical indicators...")
    df_with_indicators = add_all_indicators(raw_df)

    indicator_cols = [
        "SMA_20", "EMA_20", "RSI_14", 
        "MACD", "MACD_Signal", "MACD_Hist", 
        "BB_Upper", "BB_Middle", "BB_Lower"
    ]

    print("\n================ Indicator Calculation Summary ================")
    print(f"Total Rows in Dataset: {len(df_with_indicators)}")
    print("\nNon-Null Counts per Indicator Column:")
    print(df_with_indicators[indicator_cols].notnull().sum())

    print("\nSample Output (Last 5 Rows):")
    print(df_with_indicators[["Close"] + indicator_cols].tail())
