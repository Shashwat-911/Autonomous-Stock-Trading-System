"""
gpu_indicators.py -- CUDA-accelerated technical indicator calculator.

Uses CuPy on NVIDIA GPUs to process batch price matrices (N tickers x M timebars)
in parallel, keeping CPU load minimal.
"""

import logging
import os
import sys
import warnings
from typing import Dict, List, Tuple
import pandas as pd
import numpy as np

# Suppress CuPy CUDA path detection warnings before import
os.environ.setdefault("CUPY_CACHE_IN_TEMP", "1")
warnings.filterwarnings("ignore", message="CUDA path could not be detected")

# Ensure project root is on sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(current_dir, ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from strategy.indicators import add_all_indicators

logger = logging.getLogger(__name__)

# Check CuPy CUDA availability (silently fall back to NumPy)
HAS_CUPY = False
try:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        import cupy as cp
        _ = cp.zeros((1, 1))
    HAS_CUPY = True
    logger.info("CuPy CUDA indicator engine initialized on GPU: %s",
                cp.cuda.runtime.getDeviceProperties(0)['name'].decode())
except Exception:
    logger.info("GPU unavailable — using vectorized NumPy/Pandas CPU engine.")
    cp = np


class GPUIndicatorEngine:
    """
    Computes technical indicators across multiple tickers simultaneously on the GPU.
    """

    def __init__(self, use_gpu: bool = True) -> None:
        self.use_gpu = use_gpu and HAS_CUPY

    def compute_batch_indicators(self, data_dict: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
        """
        Compute SMA, EMA, RSI, MACD, and Bollinger Bands for a dictionary of ticker DataFrames.

        Parameters
        ----------
        data_dict : Dict[str, pd.DataFrame]
            Dictionary mapping ticker string -> DataFrame containing 'Close' column.

        Returns
        -------
        Dict[str, pd.DataFrame]
            Dictionary mapping ticker string -> DataFrame with technical indicator columns added.
        """
        if not data_dict:
            return {}

        results = {}
        tickers = list(data_dict.keys())
        
        # Build 2D numpy array (num_tickers, num_bars)
        price_series_list = []
        valid_tickers = []
        max_len = 0

        for t in tickers:
            df = data_dict[t]
            if df is not None and not df.empty and "Close" in df.columns:
                close_vals = df["Close"].to_numpy(dtype=np.float64)
                price_series_list.append(close_vals)
                valid_tickers.append(t)
                if len(close_vals) > max_len:
                    max_len = len(close_vals)

        if not valid_tickers or max_len < 30:
            # Fallback to standard CPU calculation per ticker if insufficient history
            for t, df in data_dict.items():
                if df is not None and not df.empty:
                    results[t] = add_all_indicators(df)
            return results

        # Pad shorter series if any
        padded_prices = []
        for p in price_series_list:
            if len(p) < max_len:
                pad_width = max_len - len(p)
                padded = np.pad(p, (pad_width, 0), mode='edge')
            else:
                padded = p
            padded_prices.append(padded)

        prices_2d = np.vstack(padded_prices)  # Shape: (N, M)

        if self.use_gpu:
            try:
                # Transfer price matrix to NVIDIA GPU VRAM
                prices_gpu = cp.asarray(prices_2d)

                # Compute Indicators on GPU
                sma20_gpu = self._gpu_sma(prices_gpu, 20)
                ema20_gpu = self._gpu_ema(prices_gpu, 20)
                rsi14_gpu = self._gpu_rsi(prices_gpu, 14)
                macd_gpu, signal_gpu, hist_gpu = self._gpu_macd(prices_gpu, 12, 26, 9)
                bb_upper_gpu, bb_middle_gpu, bb_lower_gpu = self._gpu_bollinger_bands(prices_gpu, 20, 2)

                # Transfer computed results back to Host CPU
                sma20 = cp.asnumpy(sma20_gpu)
                ema20 = cp.asnumpy(ema20_gpu)
                rsi14 = cp.asnumpy(rsi14_gpu)
                macd = cp.asnumpy(macd_gpu)
                signal = cp.asnumpy(signal_gpu)
                bb_upper = cp.asnumpy(bb_upper_gpu)
                bb_lower = cp.asnumpy(bb_lower_gpu)

                for idx, t in enumerate(valid_tickers):
                    df = data_dict[t].copy()
                    n_orig = len(data_dict[t])
                    df["SMA_20"] = sma20[idx, -n_orig:]
                    df["EMA_20"] = ema20[idx, -n_orig:]
                    df["RSI_14"] = rsi14[idx, -n_orig:]
                    df["MACD"] = macd[idx, -n_orig:]
                    df["MACD_Signal"] = signal[idx, -n_orig:]
                    df["MACD_Hist"] = macd[idx, -n_orig:] - signal[idx, -n_orig:]
                    df["BB_Upper"] = bb_upper[idx, -n_orig:]
                    df["BB_Lower"] = bb_lower[idx, -n_orig:]
                    results[t] = df

                return results
            except Exception as ex:
                logger.warning("GPU execution error (%s), falling back to CPU.", ex)

        # CPU Vectorized Fallback (includes ATR via add_all_indicators)
        for t in data_dict:
            df = data_dict[t]
            if df is not None and not df.empty:
                results[t] = add_all_indicators(df)
        return results

    # -------------------------------------------------------------------
    # GPU CUDA Kernels / Vector Functions
    # -------------------------------------------------------------------

    def _gpu_sma(self, prices_gpu, window: int):
        """Vectorized Simple Moving Average on GPU matrix."""
        num_tickers, num_bars = prices_gpu.shape
        pad_head = prices_gpu[:, :1].repeat(window - 1, axis=1)
        padded = cp.concatenate([pad_head, prices_gpu], axis=1)
        cumsum = cp.cumsum(padded, axis=1)
        sma = (cumsum[:, window:] - cumsum[:, :-window]) / float(window)
        return sma[:, :num_bars]

    def _gpu_ema(self, prices_gpu, window: int):
        """Vectorized Exponential Moving Average on GPU."""
        alpha = 2.0 / (window + 1.0)
        num_tickers, num_bars = prices_gpu.shape
        ema = cp.zeros_like(prices_gpu)
        ema[:, 0] = prices_gpu[:, 0]
        for t in range(1, num_bars):
            ema[:, t] = alpha * prices_gpu[:, t] + (1.0 - alpha) * ema[:, t - 1]
        return ema

    def _gpu_rsi(self, prices_gpu, window: int = 14):
        """Vectorized Relative Strength Index on GPU (Wilder's smoothing)."""
        delta = prices_gpu[:, 1:] - prices_gpu[:, :-1]
        gains = cp.maximum(delta, 0.0)
        losses = cp.maximum(-delta, 0.0)

        num_tickers, num_bars = prices_gpu.shape
        avg_gains = cp.zeros((num_tickers, num_bars), dtype=cp.float64)
        avg_losses = cp.zeros((num_tickers, num_bars), dtype=cp.float64)

        if num_bars > window:
            avg_gains[:, window] = cp.mean(gains[:, :window], axis=1)
            avg_losses[:, window] = cp.mean(losses[:, :window], axis=1)

            for i in range(window + 1, num_bars):
                avg_gains[:, i] = (avg_gains[:, i - 1] * (window - 1) + gains[:, i - 1]) / window
                avg_losses[:, i] = (avg_losses[:, i - 1] * (window - 1) + losses[:, i - 1]) / window

        rs = cp.where(avg_losses == 0, 100.0, avg_gains / (avg_losses + 1e-10))
        rsi = 100.0 - (100.0 / (1.0 + rs))
        rsi[:, :window] = 50.0  # default neutral before window
        return rsi

    def _gpu_macd(self, prices_gpu, fast: int = 12, slow: int = 26, signal: int = 9):
        """Vectorized MACD on GPU."""
        ema_fast = self._gpu_ema(prices_gpu, fast)
        ema_slow = self._gpu_ema(prices_gpu, slow)
        macd = ema_fast - ema_slow
        signal_line = self._gpu_ema(macd, signal)
        histogram = macd - signal_line
        return macd, signal_line, histogram

    def _gpu_bollinger_bands(self, prices_gpu, window: int = 20, num_std: float = 2.0):
        """Vectorized Bollinger Bands on GPU."""
        sma = self._gpu_sma(prices_gpu, window)
        num_tickers, num_bars = prices_gpu.shape
        std = cp.zeros_like(prices_gpu)

        for i in range(window, num_bars):
            slice_window = prices_gpu[:, i - window:i]
            std[:, i] = cp.std(slice_window, axis=1)

        std_init = cp.std(prices_gpu[:, :window], axis=1, keepdims=True)
        std[:, :window] = std_init

        upper = sma + (std * num_std)
        lower = sma - (std * num_std)
        return upper, sma, lower


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("=" * 60)
    print("  GPU Technical Indicators Engine Diagnostic Test")
    print("=" * 60)
    
    engine = GPUIndicatorEngine(use_gpu=True)
    print("Engine using GPU:", engine.use_gpu)

    # Generate synthetic dummy data for 100 tickers x 100 bars
    dummy_data = {}
    dates = pd.date_range("2026-01-01", periods=100, freq="D")
    for i in range(100):
        ticker_name = f"TICKER_{i}"
        prices = 100.0 + np.random.randn(100).cumsum()
        dummy_data[ticker_name] = pd.DataFrame({"Close": prices}, index=dates)

    import time
    t0 = time.time()
    res = engine.compute_batch_indicators(dummy_data)
    t1 = time.time()

    print(f"Successfully processed {len(res)} tickers in {(t1 - t0)*1000:.2f} ms")
    sample_df = res["TICKER_0"]
    print("\nSample Ticker Output (Last 5 rows):")
    print(sample_df[["Close", "SMA_20", "RSI_14", "MACD", "BB_Upper", "BB_Lower"]].tail())
    print("=" * 60)
