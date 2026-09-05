import os

# Optionally load environment variables from .env file if python-dotenv is installed
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# config.py -- Single source of truth for ALL trading bot settings.
#
# Edit the values below to configure the bot.
# No code changes needed elsewhere -- every module reads from here.
# ---------------------------------------------------------------

TRADING = {
    "ticker": "NVDA",                  # primary asset / default fallback
    "tickers": ["NVDA", "TSLA", "META", "MSFT", "AAPL"],  # 5-stock high-momentum universe
    "interval": "1d",                  # daily candles (simplest)
    "interval_daily": "1d",            # daily bars for multi-timeframe alignment
    "initial_balance": 100000.0,
    "min_confidence": 0.70,  # lowered 0.75→0.70: allow slightly more trades through
    "lookback_days": 60,               # hourly lookback (yfinance max ~60d for 1h)
    "lookback_days_intraday": 30,      # 5m lookback (yfinance max ~60d for 5m)
    "scan_interval_minutes": 15,       # scan and trade every 15 minutes
}

SIGNAL = {
    "rsi_oversold": 40.0,    # lower bound for RSI on BUY (lowered 45→40: require stronger dip before buying)
    "rsi_overbought": 70.0,  # sell when overbought
    "require_confirmation": False,
}

RISK = {
    "max_daily_loss_pct": 0.05,
    "max_trade_loss_pct": 0.05,        # loosened 4%→5%: fewer premature stop-outs
    "max_position_pct": 0.10,          # 10% per trade
    "max_position_dollars": 5000.0,    # $5000 per trade
    "cooldown_minutes": 5,             # reduced 15→5 min: re-enter much faster after stop-loss
    "max_portfolio_heat_pct": 0.60,    # max 60% of equity in long positions
    # ATR-based position sizing
    "atr_period": 14,
    "atr_multiplier_k": 2.0,          # denominator multiplier for ATR sizing
    "risk_pct_per_trade": 0.01,        # risk 1% of equity per trade via ATR
}

BRACKET = {
    "stop_loss_atr_mult": 3.0,      # widened 2.5→3.0: more breathing room per trade
    "take_profit_atr_mult": 2.0,    # closer target, more fills
    "trailing_activation_atr": 1.0,
    "trailing_stop_atr_mult": 1.0,
}

MARKET_REGIME = {
    "ticker": "SPY",                   # broad market trend filter
    "sma_period": 200,                 # 200-day SMA for regime detection
}

ALERTS = {
    "telegram_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
    "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", ""),
    "enabled": False,
}

BACKTEST = {
    "start_date": "2024-01-01",
    "end_date": "2025-01-01",
}

WALK_FORWARD = {
    "start_date": "2023-01-01",
    "end_date": "2025-01-01",          # 2 years gives a good number of windows
    "train_months": 6,
    "test_months": 3,
}

ALPACA = {
    "api_key": os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID") or "PKGF7GGSEMWZ6SETQW53AB3QSR",
    "secret_key": os.getenv("ALPACA_SECRET_KEY") or os.getenv("APCA_API_SECRET_KEY") or "7Ks1aALfwLCVsxPPfzEZFruQ3i4ii86nTrLcgqsom3pb",
    "base_url": os.getenv("ALPACA_BASE_URL") or "https://paper-api.alpaca.markets",
    "feed": os.getenv("ALPACA_FEED") or "iex",
}