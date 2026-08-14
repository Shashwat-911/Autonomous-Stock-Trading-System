import logging
import time
from datetime import date, datetime
from functools import wraps
from typing import Union

import pandas as pd
import yfinance as yf

# Configure logger for data fetcher module
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def retry_on_failure(max_retries: int = 3, initial_delay: float = 1.0, backoff_factor: float = 2.0):
    """
    Decorator to retry a function call upon encountering an exception.

    Parameters
    ----------
    max_retries : int, optional
        Maximum number of retry attempts (default is 3).
    initial_delay : float, optional
        Initial sleep time in seconds before retrying (default is 1.0).
    backoff_factor : float, optional
        Multiplier applied to delay after each retry attempt (default is 2.0).

    Returns
    -------
    function
        Wrapped function with retry logic.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    logger.warning(
                        f"Attempt {attempt}/{max_retries} failed for function '{func.__name__}' "
                        f"with error: {e}. Retrying in {delay:.1f}s..."
                    )
                    if attempt < max_retries:
                        time.sleep(delay)
                        delay *= backoff_factor
            logger.error(f"All {max_retries} attempts failed for function '{func.__name__}'.")
            raise last_exception
        return wrapper
    return decorator


@retry_on_failure(max_retries=3, initial_delay=1.0)
def get_historical_data(
    ticker: str,
    start_date: Union[str, date, datetime],
    end_date: Union[str, date, datetime],
    interval: str = "1d"
) -> pd.DataFrame:
    """
    Fetch historical OHLCV data for a given ticker symbol and date range using yfinance.

    Parameters
    ----------
    ticker : str
        The ticker symbol of the financial asset (e.g., 'AAPL', 'MSFT', 'BTC-USD').
    start_date : str or date or datetime
        The start date for the historical data query (e.g., '2023-01-01').
    end_date : str or date or datetime
        The end date for the historical data query (e.g., '2023-12-31').
    interval : str, optional
        Data interval (e.g., '1m', '5m', '1h', '1d', '1wk', '1mo'). Default is '1d'.

    Returns
    -------
    pd.DataFrame
        A clean pandas DataFrame containing OHLCV historical data with a DatetimeIndex 
        and no missing values.

    Raises
    ------
    ValueError
        If no data is found for the given parameters or if cleaned data is empty.
    """
    logger.info(
        f"Fetching historical OHLCV data for ticker '{ticker}' "
        f"from {start_date} to {end_date} (interval: '{interval}')."
    )

    ticker_obj = yf.Ticker(ticker)
    df = ticker_obj.history(start=start_date, end=end_date, interval=interval)

    if df is None or df.empty:
        logger.error(f"No historical data returned for ticker '{ticker}' in range {start_date} to {end_date}.")
        raise ValueError(f"No historical data found for ticker '{ticker}' between {start_date} and {end_date}.")

    # Flatten MultiIndex column headers if returned by yfinance
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # Clean data: drop rows where all values are NaN
    df = df.dropna(how="all")

    # Forward fill then backward fill to handle intermittent missing values, drop remaining NaNs
    df = df.ffill().bfill().dropna()

    if df.empty:
        logger.error(f"Historical data for ticker '{ticker}' is empty after cleaning missing values.")
        raise ValueError(f"Cleaned historical data for ticker '{ticker}' contains no valid records.")

    logger.info(f"Successfully retrieved and cleaned {len(df)} rows of historical data for ticker '{ticker}'.")
    return df


@retry_on_failure(max_retries=3, initial_delay=1.0)
def get_batch_historical_data(
    tickers: list,
    start_date: Union[str, date, datetime],
    end_date: Union[str, date, datetime],
    interval: str = "1d"
) -> dict:
    """
    Fetch historical OHLCV data for multiple ticker symbols concurrently using yfinance batch download.

    Parameters
    ----------
    tickers : list of str
        List of ticker symbols (e.g., ['AAPL', 'MSFT', 'NVDA']).
    start_date : str or date or datetime
        The start date for historical data query.
    end_date : str or date or datetime
        The end date for historical data query.
    interval : str, optional
        Data interval. Default is '1d'.

    Returns
    -------
    dict
        Dictionary mapping ticker string -> clean pandas DataFrame.
    """
    logger.info(f"Batch fetching historical OHLCV for {len(tickers)} tickers from {start_date} to {end_date}.")
    
    # Batch download using yfinance threads
    raw_data = yf.download(
        tickers=tickers,
        start=start_date,
        end=end_date,
        interval=interval,
        group_by="ticker",
        threads=True,
        progress=False,
    )

    results = {}

    if len(tickers) == 1:
        t = tickers[0]
        if isinstance(raw_data, pd.DataFrame) and not raw_data.empty:
            df = raw_data.dropna(how="all").ffill().bfill()
            if not df.empty:
                results[t] = df
        return results

    for t in tickers:
        try:
            if isinstance(raw_data.columns, pd.MultiIndex):
                if t in raw_data.columns.levels[0]:
                    df_t = raw_data[t].copy()
                else:
                    continue
            else:
                df_t = raw_data.copy()

            df_t = df_t.dropna(how="all")
            df_t = df_t.ffill().bfill()
            if not df_t.empty and "Close" in df_t.columns:
                results[t] = df_t
        except Exception as ex:
            logger.debug("Failed parsing batch data for ticker %s: %s", t, ex)

    logger.info("Successfully batch fetched data for %d / %d tickers.", len(results), len(tickers))
    return results


@retry_on_failure(max_retries=3, initial_delay=1.0)
def get_latest_price(ticker: str) -> float:
    """
    Fetch the latest real-time or most recent closing price for a given ticker symbol using yfinance.

    Parameters
    ----------
    ticker : str
        The ticker symbol of the financial asset (e.g., 'AAPL', 'MSFT', 'BTC-USD').

    Returns
    -------
    float
        The latest price of the specified ticker symbol.

    Raises
    ------
    ValueError
        If a valid price cannot be retrieved for the ticker symbol.
    """
    logger.info(f"Fetching latest real-time price for ticker '{ticker}'.")

    ticker_obj = yf.Ticker(ticker)
    price = None

    # Option 1: Try fast_info attributes
    try:
        fast_info = getattr(ticker_obj, "fast_info", None)
        if fast_info:
            price = fast_info.get("lastPrice") or fast_info.get("regularMarketPrice")
    except Exception as e:
        logger.debug(f"Could not retrieve fast_info for ticker '{ticker}': {e}")

    # Option 2: Fall back to fetching recent history if fast_info fails
    if price is None or pd.isna(price):
        logger.debug(f"Falling back to short interval history for ticker '{ticker}'.")
        hist = ticker_obj.history(period="1d", interval="1m")
        if hist.empty:
            hist = ticker_obj.history(period="5d", interval="1d")

        if not hist.empty and "Close" in hist.columns:
            price = float(hist["Close"].iloc[-1])

    if price is None or pd.isna(price):
        logger.error(f"Failed to retrieve valid price for ticker '{ticker}'.")
        raise ValueError(f"Could not fetch a valid real-time price for ticker '{ticker}'.")

    logger.info(f"Successfully fetched latest price for ticker '{ticker}': {price}")
    return float(price)


@retry_on_failure(max_retries=3, initial_delay=1.0)
def get_intraday_data(
    ticker: str,
    lookback_days: int = 30,
    interval: str = "5m",
) -> pd.DataFrame:
    """
    Fetch intraday OHLCV bars for a given ticker using yfinance.

    yfinance enforces maximum lookback periods for intraday intervals:
    - 1m: max 7 days
    - 5m: max 60 days
    - 15m/30m: max 60 days
    - 1h: max 730 days

    Parameters
    ----------
    ticker : str
        Ticker symbol (e.g., 'NVDA').
    lookback_days : int, optional
        Number of calendar days to look back (default 30).
    interval : str, optional
        Intraday bar interval (default '5m').

    Returns
    -------
    pd.DataFrame
        Clean DataFrame with OHLCV data and DatetimeIndex.

    Raises
    ------
    ValueError
        If no data is returned or cleaned data is empty.
    """
    # Clamp lookback to yfinance limits
    max_days = {"1m": 7, "2m": 60, "5m": 60, "15m": 60, "30m": 60, "1h": 730}
    limit = max_days.get(interval, 60)
    clamped = min(lookback_days, limit)

    logger.info(
        "Fetching intraday %s bars for '%s' (lookback=%dd, clamped=%dd).",
        interval, ticker, lookback_days, clamped,
    )

    ticker_obj = yf.Ticker(ticker)
    df = ticker_obj.history(period=f"{clamped}d", interval=interval)

    if df is None or df.empty:
        raise ValueError(
            f"No intraday data returned for '{ticker}' "
            f"(interval={interval}, lookback={clamped}d)."
        )

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.dropna(how="all").ffill().bfill().dropna()

    if df.empty:
        raise ValueError(f"Intraday data for '{ticker}' is empty after cleaning.")

    logger.info(
        "Retrieved %d intraday %s bars for '%s'.", len(df), interval, ticker
    )
    return df


def get_market_regime_data(
    ticker: str = "SPY",
    sma_period: int = 200,
) -> dict:
    """
    Fetch daily data for a broad-market ETF and determine whether the
    market is in a bullish regime (price > SMA).

    Parameters
    ----------
    ticker : str, optional
        Market proxy ticker (default 'SPY').
    sma_period : int, optional
        SMA lookback in trading days (default 200).

    Returns
    -------
    dict
        Keys: 'is_bullish' (bool), 'price' (float), 'sma' (float),
        'ticker' (str).
    """
    lookback = sma_period + 60  # extra margin for SMA warmup
    try:
        ticker_obj = yf.Ticker(ticker)
        df = ticker_obj.history(period=f"{lookback}d", interval="1d")

        if df is None or df.empty or len(df) < sma_period:
            logger.warning(
                "Insufficient data for market regime (%s). "
                "Defaulting to bullish.", ticker,
            )
            return {"is_bullish": True, "price": 0.0, "sma": 0.0, "ticker": ticker}

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.dropna(how="all").ffill().bfill()
        sma = df["Close"].rolling(window=sma_period).mean()
        latest_close = float(df["Close"].iloc[-1])
        latest_sma = float(sma.iloc[-1])
        is_bullish = latest_close > latest_sma

        logger.info(
            "Market regime [%s]: Close=%.2f, SMA_%d=%.2f -> %s",
            ticker, latest_close, sma_period, latest_sma,
            "BULLISH" if is_bullish else "BEARISH",
        )
        return {
            "is_bullish": is_bullish,
            "price": latest_close,
            "sma": latest_sma,
            "ticker": ticker,
        }
    except Exception as e:
        logger.warning("Market regime check failed (%s): %s. Defaulting to bullish.", ticker, e)
        return {"is_bullish": True, "price": 0.0, "sma": 0.0, "ticker": ticker}


@retry_on_failure(max_retries=2, initial_delay=0.5)
def get_latest_bar(ticker: str, interval: str = "5m") -> pd.DataFrame:
    """
    Fetch the most recent 1–2 bars for live bar merging.

    Parameters
    ----------
    ticker : str
        Ticker symbol.
    interval : str, optional
        Bar interval (default '5m').

    Returns
    -------
    pd.DataFrame
        DataFrame with the latest bar(s).
    """
    ticker_obj = yf.Ticker(ticker)
    df = ticker_obj.history(period="1d", interval=interval)

    if df is None or df.empty:
        raise ValueError(f"No latest bar data for '{ticker}' at interval '{interval}'.")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    return df.tail(2)

