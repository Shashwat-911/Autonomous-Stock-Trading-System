import logging
import os
import sys
from datetime import datetime
from typing import Optional, Union

# Prevent local module (broker/alpaca.py) from shadowing installed 'alpaca' package
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir in sys.path:
    sys.path.remove(current_dir)

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus, OrderClass
from alpaca.trading.requests import (
    MarketOrderRequest,
    GetOrdersRequest,
    LimitOrderRequest,
    TakeProfitRequest,
    StopLossRequest,
)

# Ensure project root is on path for risk, strategy, data imports
root_dir = os.path.abspath(os.path.join(current_dir, ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

import pandas as pd
from typing import Dict
from risk.manager import RiskManager
from strategy.signals import SignalGenerator

# Configure logger for Alpaca broker module
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


class AlpacaPaperBroker:
    """
    Live paper-trading broker interface using the official Alpaca API (alpaca-py).

    Provides order placement, account balance tracking, open position monitoring,
    and market clock verification for live paper trading.

    Parameters
    ----------
    api_key : str
        Alpaca API key ID.
    secret_key : str
        Alpaca secret key.
    base_url : str, optional
        Alpaca base URL (default ``'https://paper-api.alpaca.markets/v2'``).
    ticker : str, optional
        Ticker symbol to trade (default ``'NVDA'``).
    risk_manager : RiskManager
        Risk management engine for pre-trade circuit breaker and position sizing.
    signal_generator : SignalGenerator
        Signal generator for evaluating indicator data.
    min_confidence : float, optional
        Minimum signal confidence required to issue a BUY order (default 0.25).
    feed : str, optional
        Data feed identifier (default ``'iex'``).
    """

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        base_url: str = "https://paper-api.alpaca.markets",
        ticker: str = "NVDA",
        risk_manager: Optional[RiskManager] = None,
        signal_generator: Optional[SignalGenerator] = None,
        min_confidence: float = 0.25,
        feed: str = "iex",
    ) -> None:
        """
        Initialise Alpaca paper broker client.
        """
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = base_url
        self.ticker = ticker
        self.min_confidence = min_confidence
        self.feed = feed

        # Initialize official Alpaca TradingClient for paper account
        self.client = TradingClient(api_key, secret_key, paper=True)

        self.risk_manager = risk_manager
        self.signal_generator = signal_generator

        # Trailing stop tracking: ticker -> {order_id, entry_price, atr, activated}
        self._trailing_state: Dict[str, dict] = {}
        self._last_buy_time: Dict[str, datetime] = {}

        logger.info(
            "AlpacaPaperBroker initialized -- ticker=%s, feed=%s, min_confidence=%.2f",
            ticker,
            feed,
            min_confidence,
        )

    def is_market_open(self) -> bool:
        """
        Check if the US stock market is currently open via Alpaca's clock API.

        Returns
        -------
        bool
            True if market is open, False otherwise.
        """
        clock = self.get_clock()
        return bool(clock.is_open) if clock else False

    def get_clock(self):
        """
        Fetch the current market clock from Alpaca.

        Returns
        -------
        Clock or None
            Alpaca Clock object with is_open, next_open, next_close, timestamp.
        """
        try:
            return self.client.get_clock()
        except Exception as e:
            logger.error("Failed to query market clock from Alpaca: %s", e)
            return None

    def get_account_info(self) -> dict:
        """
        Fetch current account balance and metrics from Alpaca.

        Returns
        -------
        dict
            Dict with keys: cash, portfolio_value, buying_power, equity, daytrade_count.
        """
        account = self.client.get_account()
        return {
            "cash": float(account.cash),
            "portfolio_value": float(account.portfolio_value),
            "buying_power": float(account.buying_power),
            "equity": float(account.equity),
            "daytrade_count": getattr(account, "daytrade_count", 0),
        }

    def get_current_position(self) -> Optional[dict]:
        """
        Fetch current open position for the configured ticker symbol.

        Returns
        -------
        dict or None
            Position dictionary if an open position exists, else None.
        """
        try:
            position = self.client.get_open_position(self.ticker)
            return {
                "shares": float(position.qty),
                "avg_entry_price": float(position.avg_entry_price),
                "current_price": float(position.current_price),
                "unrealized_pnl": float(position.unrealized_pl),
                "unrealized_pnl_pct": float(position.unrealized_plpc) * 100.0,
            }
        except Exception:
            return None

    def get_all_positions(self) -> Dict[str, dict]:
        """
        Fetch open positions across all tickers from Alpaca.

        Returns
        -------
        Dict[str, dict]
            Mapping of ticker -> position details dict.
        """
        try:
            positions = self.client.get_all_positions()
            pos_dict = {}
            for p in positions:
                pos_dict[p.symbol] = {
                    "shares": float(p.qty),
                    "avg_entry_price": float(p.avg_entry_price),
                    "current_price": float(p.current_price),
                    "unrealized_pnl": float(p.unrealized_pl),
                    "unrealized_pnl_pct": float(p.unrealized_plpc) * 100.0,
                }
            return pos_dict
        except Exception:
            return {}

    def submit_buy(self, quantity: int, reason: str, ticker: Optional[str] = None) -> dict:
        """
        Submit a market BUY order to Alpaca.

        Parameters
        ----------
        quantity : int
            Number of shares to buy.
        reason : str
            Reason for submitting the trade.
        ticker : str, optional
            Ticker symbol (default is self.ticker).

        Returns
        -------
        dict
            Order metadata dictionary or empty dict if skipped.
        """
        sym = ticker or self.ticker
        if quantity <= 0:
            logger.warning("submit_buy skipped -- invalid quantity %d.", quantity)
            return {}

        order_data = MarketOrderRequest(
            symbol=sym,
            qty=quantity,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
        )

        order = self.client.submit_order(order_data)
        logger.info(
            "BUY ORDER SUBMITTED: %d shares of %s | Reason: %s | Order ID: %s",
            quantity,
            sym,
            reason,
            order.id,
        )
        return {
            "order_id": str(order.id),
            "qty": quantity,
            "side": "BUY",
            "reason": reason,
        }

    def submit_bracket_buy(
        self,
        quantity: int,
        reason: str,
        current_price: float,
        atr: float,
        stop_loss_mult: float = 2.5,
        take_profit_mult: float = 2.0,
        ticker: str | None = None,
    ) -> dict:
        """
        Submit a bracket BUY order with ATR-based stop-loss and take-profit.

        Parameters
        ----------
        quantity : int
            Number of shares to buy.
        reason : str
            Reason for the trade.
        current_price : float
            Current market price (used to calculate bracket levels).
        atr : float
            Current ATR value for the asset.
        stop_loss_mult : float, optional
            ATR multiplier for stop-loss distance (default 1.5).
        take_profit_mult : float, optional
            ATR multiplier for take-profit distance (default 3.0).
        ticker : str, optional
            Ticker symbol (default is self.ticker).

        Returns
        -------
        dict
            Order metadata including bracket levels.
        """
        sym = ticker or self.ticker
        if quantity <= 0:
            logger.warning("submit_bracket_buy skipped -- invalid quantity %d.", quantity)
            return {}

        stop_price = round(current_price - (stop_loss_mult * atr), 2)
        take_profit_price = round(current_price + (take_profit_mult * atr), 2)

        # Ensure stop price is positive and sensible
        if stop_price <= 0:
            stop_price = round(current_price * 0.95, 2)
        if take_profit_price <= current_price:
            take_profit_price = round(current_price * 1.06, 2)

        try:
            order_data = MarketOrderRequest(
                symbol=sym,
                qty=quantity,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY,
                order_class=OrderClass.BRACKET,
                take_profit=TakeProfitRequest(limit_price=take_profit_price),
                stop_loss=StopLossRequest(stop_price=stop_price),
            )

            order = self.client.submit_order(order_data)

            # Track for trailing stop management
            self._trailing_state[sym] = {
                "order_id": str(order.id),
                "entry_price": current_price,
                "atr": atr,
                "stop_price": stop_price,
                "take_profit_price": take_profit_price,
                "trailing_activated": False,
            }

            logger.info(
                "BRACKET BUY ORDER: %d shares of %s @ ~$%.2f | "
                "SL=$%.2f (-%.1f×ATR) | TP=$%.2f (+%.1f×ATR) | "
                "Reason: %s | Order ID: %s",
                quantity, sym, current_price,
                stop_price, stop_loss_mult,
                take_profit_price, take_profit_mult,
                reason, order.id,
            )

            return {
                "order_id": str(order.id),
                "qty": quantity,
                "side": "BUY",
                "reason": reason,
                "stop_loss": stop_price,
                "take_profit": take_profit_price,
                "bracket": True,
            }

        except Exception as e:
            logger.warning(
                "Bracket order failed (%s), falling back to market order: %s",
                sym, e,
            )
            return self.submit_buy(quantity, reason, ticker=ticker)

    def submit_sell(self, quantity: Union[int, str], reason: str, ticker: Optional[str] = None) -> dict:
        """
        Submit a market SELL order to Alpaca.

        Parameters
        ----------
        quantity : int or str
            Number of shares to sell, or 'ALL' to liquidate position.
        reason : str
            Reason for submitting the trade.
        ticker : str, optional
            Ticker symbol (default is self.ticker).

        Returns
        -------
        dict
            Order metadata dictionary or empty dict if skipped.
        """
        sym = ticker or self.ticker
        if isinstance(quantity, str) and quantity.upper() == "ALL":
            all_pos = self.get_all_positions()
            position = all_pos.get(sym)
            if position is None or position["shares"] <= 0:
                logger.warning("submit_sell skipped -- no open position for %s.", sym)
                return {}
            quantity = int(position["shares"])

        if quantity <= 0:
            logger.warning("submit_sell skipped -- invalid quantity %s.", quantity)
            return {}

        order_data = MarketOrderRequest(
            symbol=sym,
            qty=quantity,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
        )

        order = self.client.submit_order(order_data)
        logger.info(
            "SELL ORDER SUBMITTED: %d shares of %s | Reason: %s | Order ID: %s",
            quantity,
            sym,
            reason,
            order.id,
        )
        return {
            "order_id": str(order.id),
            "qty": quantity,
            "side": "SELL",
            "reason": reason,
        }

    def _update_trailing_stop(self, ticker: str, current_price: float) -> None:
        """
        Check if a position has gained enough to activate a trailing stop.
        If so, log the activation. Actual stop management is handled by
        Alpaca's bracket order stop-loss leg.

        Parameters
        ----------
        ticker : str
            Ticker symbol to check.
        current_price : float
            Current market price.
        """
        state = self._trailing_state.get(ticker)
        if state is None:
            return

        entry = state["entry_price"]
        atr = state["atr"]

        if atr <= 0:
            return

        import config
        bracket_cfg = getattr(config, "BRACKET", {})
        activation_mult = bracket_cfg.get("trailing_activation_atr", 1.5)

        unrealized_gain = current_price - entry
        activation_threshold = activation_mult * atr

        if unrealized_gain >= activation_threshold and not state["trailing_activated"]:
            state["trailing_activated"] = True
            new_stop = round(current_price - (1.0 * atr), 2)
            logger.info(
                "TRAILING STOP ACTIVATED for %s: gain=$%.2f >= %.1f×ATR($%.2f). "
                "New mental stop=$%.2f (was $%.2f)",
                ticker, unrealized_gain, activation_mult, activation_threshold,
                new_stop, state["stop_price"],
            )
            state["stop_price"] = new_stop
        elif state["trailing_activated"]:
            # Trail the stop up as price moves higher
            trail_stop = round(current_price - (1.0 * atr), 2)
            if trail_stop > state["stop_price"]:
                logger.info(
                    "TRAILING STOP RAISED for %s: $%.2f -> $%.2f (price=$%.2f)",
                    ticker, state["stop_price"], trail_stop, current_price,
                )
                state["stop_price"] = trail_stop

    def run_tick(self, df: pd.DataFrame, **kwargs) -> dict:
        """
        Process a single time bar against the live Alpaca paper environment.

        Parameters
        ----------
        df : pd.DataFrame
            DataFrame containing technical indicators.

        Returns
        -------
        dict
            Tick status output dictionary.
        """
        current_price = float(df["Close"].iloc[-1])
        atr_value = float(df["ATR_14"].iloc[-1]) if "ATR_14" in df.columns else 0.0

        if not self.is_market_open():
            return {
                "signal": "HOLD",
                "reason": "Market closed",
                "price": current_price,
                "time": datetime.now().isoformat(),
                "market_open": False,
            }

        account = self.get_account_info()
        portfolio_value = account["portfolio_value"]

        can_trade, block_reason = self.risk_manager.can_trade(portfolio_value)
        position = self.get_current_position()

        # Update trailing stops for existing positions
        self._update_trailing_stop(self.ticker, current_price)

        if position is not None:
            entry_price = position["avg_entry_price"]
            stop_triggered, stop_reason = self.risk_manager.check_stop_loss(
                entry_price, current_price
            )
            if stop_triggered:
                self.submit_sell("ALL", stop_reason)
                return {
                    "signal": "SELL",
                    "reason": stop_reason,
                    "price": current_price,
                    "portfolio_value": portfolio_value,
                    "position": position,
                    "can_trade": False,
                    "time": datetime.now().isoformat(),
                    "market_open": True,
                }

        # Extract extra context for signal generation
        market_regime_bullish = kwargs.get("market_regime_bullish", True)
        daily_trend_bullish = kwargs.get("daily_trend_bullish", True)

        signal_dict = self.signal_generator.generate_signal(
            df, portfolio_value,
            market_regime_bullish=market_regime_bullish,
            daily_trend_bullish=daily_trend_bullish,
        )
        signal = signal_dict["signal"]
        confidence = signal_dict["confidence"]

        if signal == "BUY" and confidence >= self.min_confidence and can_trade:
            # Portfolio heat check
            all_pos = self.get_all_positions()
            long_exposure = sum(
                p["shares"] * p["current_price"]
                for p in all_pos.values()
            )
            heat_ok, heat_reason = self.risk_manager.check_portfolio_heat(
                long_exposure, portfolio_value
            )

            if heat_ok and position is None:
                # Simple percentage-based sizing (no ATR)
                qty = self.risk_manager.get_position_size(
                    portfolio_value, current_price
                )

                if qty > 0:
                    # TEMP: bracket orders disabled for debugging
                    # Uses plain market order + simple position sizing
                    self.submit_buy(qty, "; ".join(signal_dict["reasons"]))
                    self._last_buy_time[self.ticker] = datetime.now()
            elif not heat_ok:
                logger.info("BUY blocked by portfolio heat: %s", heat_reason)

        if signal == "SELL" and position is not None:
            if self.ticker in self._last_buy_time:
                minutes_held = (
                    datetime.now() - self._last_buy_time[self.ticker]
                ).seconds / 60
                if minutes_held < 60:  # minimum 60 minute hold
                    logger.info(
                        f"Hold filter: only held {minutes_held:.0f}m, skipping SELL"
                    )
                else:
                    self.submit_sell("ALL", "; ".join(signal_dict["reasons"]))
            else:
                self.submit_sell("ALL", "; ".join(signal_dict["reasons"]))

        return {
            "signal": signal,
            "confidence": confidence,
            "price": current_price,
            "portfolio_value": portfolio_value,
            "position": position,
            "can_trade": can_trade,
            "time": datetime.now().isoformat(),
            "market_open": True,
        }

    def run_tick_multi(self, ticker_dfs: Dict[str, pd.DataFrame]) -> Dict[str, dict]:
        """
        Process time bars across all tickers against the live Alpaca paper environment.

        Parameters
        ----------
        ticker_dfs : Dict[str, pd.DataFrame]
            Mapping of ticker -> DataFrame with technical indicators added.

        Returns
        -------
        Dict[str, dict]
            Mapping of ticker -> tick status output dictionary.
        """
        results = {}
        market_open = self.is_market_open()
        account = self.get_account_info()
        portfolio_value = account["portfolio_value"]
        all_positions = self.get_all_positions()

        for ticker, df in ticker_dfs.items():
            if df is None or df.empty:
                continue

            current_price = float(df["Close"].iloc[-1])

            if not market_open:
                results[ticker] = {
                    "ticker": ticker,
                    "signal": "SKIP",
                    "reason": "Market closed",
                    "price": current_price,
                    "portfolio_value": portfolio_value,
                    "position": all_positions.get(ticker),
                    "can_trade": False,
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "market_open": False,
                }
                continue

            can_trade, block_reason = self.risk_manager.can_trade(portfolio_value)
            position = all_positions.get(ticker)

            # Check stop loss if holding position
            if position is not None:
                entry_price = position["avg_entry_price"]
                stop_triggered, stop_reason = self.risk_manager.check_stop_loss(
                    entry_price, current_price
                )
                if stop_triggered:
                    self.submit_sell("ALL", stop_reason, ticker=ticker)
                    results[ticker] = {
                        "ticker": ticker,
                        "signal": "SELL",
                        "reason": stop_reason,
                        "confidence": 1.0,
                        "price": current_price,
                        "portfolio_value": portfolio_value,
                        "position": position,
                        "can_trade": False,
                        "time": datetime.now().strftime("%H:%M:%S"),
                        "market_open": True,
                    }
                    continue

            signal_dict = self.signal_generator.generate_signal(df, portfolio_value)
            signal = signal_dict["signal"]
            confidence = signal_dict["confidence"]

            if signal == "BUY" and confidence >= self.min_confidence and can_trade:
                qty = self.risk_manager.get_position_size(portfolio_value, current_price)
                if qty > 0 and position is None:
                    self.submit_buy(qty, "; ".join(signal_dict["reasons"]), ticker=ticker)

            if signal == "SELL" and position is not None:
                self.submit_sell("ALL", "; ".join(signal_dict["reasons"]), ticker=ticker)

            display_signal = signal if signal in ("BUY", "SELL") else "SKIP"

            results[ticker] = {
                "ticker": ticker,
                "signal": display_signal,
                "confidence": confidence,
                "reasons": "; ".join(signal_dict.get("reasons", [])),
                "price": current_price,
                "portfolio_value": portfolio_value,
                "position": position,
                "can_trade": can_trade,
                "time": datetime.now().strftime("%H:%M:%S"),
                "market_open": True,
            }

        return results

    def get_performance_summary(self) -> dict:
        """
        Calculate performance summary metrics vs $100,000 paper balance baseline.

        Returns
        -------
        dict
            Performance metrics summary.
        """
        account = self.get_account_info()
        starting_equity = 100000.0
        return {
            "equity": account["equity"],
            "cash": account["cash"],
            "portfolio_value": account["portfolio_value"],
            "starting_equity": starting_equity,
            "return_pct": ((account["equity"] - starting_equity) / starting_equity) * 100.0,
            "buying_power": account["buying_power"],
        }

    def get_trade_history(self) -> pd.DataFrame:
        """
        Fetch order history directly from Alpaca API for this ticker.

        Returns
        -------
        pd.DataFrame
            DataFrame of executed/submitted trade orders.
        """
        try:
            req = GetOrdersRequest(
                status=QueryOrderStatus.ALL,
                symbols=[self.ticker]
            )
            orders = self.client.get_orders(filter=req)
            rows = []
            for o in orders:
                rows.append({
                    "order_id": str(o.id),
                    "timestamp": str(o.submitted_at),
                    "ticker": o.symbol,
                    "action": str(o.side.value).upper(),
                    "quantity": float(o.qty),
                    "status": str(o.status.value),
                    "filled_avg_price": float(o.filled_avg_price) if o.filled_avg_price else None,
                })
            return pd.DataFrame(rows)
        except Exception as e:
            logger.error("Failed to fetch order history from Alpaca: %s", e)
            return pd.DataFrame()

    def export_trade_history(self, filepath: str) -> None:
        """
        Export trade history to CSV.
        """
        df = self.get_trade_history()
        if not df.empty:
            df.to_csv(filepath, index=False)
            logger.info("Trade history exported to %s", filepath)


if __name__ == "__main__":
    import config
    from data.fetcher import get_historical_data
    from strategy.indicators import add_all_indicators

    print("=" * 70)
    print("  AlpacaPaperBroker -- Diagnostics & Verification")
    print("=" * 70)

    rm = RiskManager(
        initial_balance=config.TRADING["initial_balance"],
        **config.RISK,
    )
    sg = SignalGenerator(rm, **config.SIGNAL)
    broker = AlpacaPaperBroker(
        api_key=config.ALPACA["api_key"],
        secret_key=config.ALPACA["secret_key"],
        base_url=config.ALPACA["base_url"],
        ticker=config.TRADING["ticker"],
        risk_manager=rm,
        signal_generator=sg,
        feed=config.ALPACA["feed"],
    )

    print("\n=== ALPACA ACCOUNT INFO ===")
    acc_info = broker.get_account_info()
    for k, v in acc_info.items():
        print(f"  {k}: {v}")

    print("\n=== MARKET STATUS ===")
    print("Market open:", broker.is_market_open())

    print("\n=== CURRENT POSITION ===")
    pos = broker.get_current_position()
    print(pos if pos is not None else "No open position")

    print("\n=== RUNNING ONE TICK ===")
    raw_df = get_historical_data(
        config.TRADING["ticker"],
        start_date="2025-05-01",
        end_date="2026-08-09",
        interval="1d",
    )
    df = add_all_indicators(raw_df)

    tick = broker.run_tick(df)
    for k, v in tick.items():
        print(f"  {k}: {v}")

    print("\n=== PERFORMANCE SUMMARY ===")
    perf = broker.get_performance_summary()
    for k, v in perf.items():
        print(f"  {k}: {v}")

    print("\n" + "=" * 70)
    print("  Alpaca test complete.")
    print("=" * 70)
