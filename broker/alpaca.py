import logging
import os
import sys
from datetime import datetime, timedelta, timezone
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

    def submit_buy(self, quantity: int, reason: str = "", ticker: Optional[str] = None) -> dict:
        """Submit a simple market buy order. Returns empty dict on failure."""
        sym = ticker or self.ticker
        if quantity <= 0:
            logger.warning("submit_buy skipped -- invalid quantity %d.", quantity)
            return {}

        try:
            from alpaca.trading.requests import MarketOrderRequest
            from alpaca.trading.enums import OrderSide, TimeInForce

            order_data = MarketOrderRequest(
                symbol=sym,
                qty=quantity,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY,
            )
            order = self.client.submit_order(order_data)
            logger.info(
                f"BUY submitted: {quantity}sh {sym} | reason={reason} "
                f"| order_id={order.id}"
            )
            return {
                "id": str(order.id),
                "order_id": str(order.id),
                "status": str(order.status),
                "qty": quantity,
                "side": "BUY",
                "reason": reason,
            }
        except Exception as e:
            logger.error(
                f"BUY order failed for {sym} (qty={quantity}): {e}"
            )
            return {}

    def submit_bracket_buy(
        self,
        quantity: int,
        reason: str,
        current_price: float,
        atr: float,
        stop_loss_mult: float = 1.5,
        take_profit_mult: float = 3.0,
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
                time_in_force=TimeInForce.GTC,
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

    def cancel_open_orders(self, ticker: Optional[str] = None) -> list:
        """
        Cancel all resting open orders for a ticker (e.g. bracket SL/TP orders).

        Parameters
        ----------
        ticker : str, optional
            Ticker symbol (default is self.ticker).

        Returns
        -------
        list
            List of cancelled order IDs.
        """
        sym = ticker or self.ticker
        cancelled = []
        try:
            open_orders = self.client.get_orders(
                GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[sym])
            )
            for o in open_orders:
                try:
                    self.client.cancel_order_by_id(o.id)
                    cancelled.append(str(o.id))
                    logger.info("Cancelled open order %s for %s", o.id, sym)
                except Exception as cancel_err:
                    logger.warning("Could not cancel order %s for %s: %s", o.id, sym, cancel_err)
        except Exception as e:
            logger.warning("Failed to fetch open orders for %s: %s", sym, e)
        return cancelled

    def submit_sell(self, quantity: Union[int, str], reason: str, ticker: Optional[str] = None) -> dict:
        """
        Submit a market SELL order to Alpaca or liquidate an open position.

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
        is_all = isinstance(quantity, str) and quantity.upper() == "ALL"

        all_pos = self.get_all_positions()
        position = all_pos.get(sym)
        if position is None or position["shares"] <= 0:
            logger.warning("submit_sell skipped -- no open position for %s.", sym)
            return {}

        pos_shares = int(position["shares"])
        if is_all:
            sell_qty = pos_shares
        else:
            try:
                sell_qty = int(quantity)
            except (ValueError, TypeError):
                logger.warning("submit_sell skipped -- invalid quantity %s.", quantity)
                return {}

        if sell_qty <= 0:
            logger.warning("submit_sell skipped -- invalid quantity %s.", quantity)
            return {}

        # If liquidating the full position, use Alpaca's native close_position
        # which automatically cancels resting bracket orders (stop-loss / take-profit)
        if is_all or sell_qty >= pos_shares:
            try:
                order = self.client.close_position(sym)
                order_id = getattr(order, "id", None) or getattr(order, "order_id", "CLOSED")
                logger.info(
                    "POSITION CLOSED (LIQUIDATED): %s | Shares: %d | Reason: %s | Order ID: %s",
                    sym,
                    pos_shares,
                    reason,
                    order_id,
                )
                return {
                    "order_id": str(order_id),
                    "qty": pos_shares,
                    "side": "SELL",
                    "reason": reason,
                }
            except Exception as e:
                logger.warning(
                    "close_position failed for %s (%s); attempting order cancel + market sell fallback.",
                    sym,
                    e,
                )
                self.cancel_open_orders(sym)

        # For partial sell or fallback after close_position error:
        # Cancel resting bracket orders first so shares are not 'held_for_orders'
        self.cancel_open_orders(sym)

        order_data = MarketOrderRequest(
            symbol=sym,
            qty=sell_qty,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
        )

        try:
            order = self.client.submit_order(order_data)
            logger.info(
                "SELL ORDER SUBMITTED: %d shares of %s | Reason: %s | Order ID: %s",
                sell_qty,
                sym,
                reason,
                order.id,
            )
            return {
                "order_id": str(order.id),
                "qty": sell_qty,
                "side": "SELL",
                "reason": reason,
            }
        except Exception as e:
            logger.error("submit_sell failed for %s (%d shares): %s", sym, sell_qty, e)
            return {}

    def _has_pending_buy_order(self) -> bool:
        """
        Return True if there is any open BUY order for this ticker 
        that has not yet been filled. Prevents duplicate order submission.
        """
        try:
            open_orders = self.client.get_orders(
                filter=GetOrdersRequest(
                    status=QueryOrderStatus.OPEN,
                    symbols=[self.ticker],
                    limit=10,
                )
            )
            for order in open_orders:
                if hasattr(order, 'side') and str(order.side).lower() in ('buy', 'ordersidebuy', 'orderside.buy'):
                    logger.info(
                        f"Dedup: Pending BUY order exists for {self.ticker} "
                        f"(id={order.id}, status={order.status}) — skipping new BUY"
                    )
                    return True
            return False
        except Exception as e:
            logger.warning(f"Dedup check failed for {self.ticker}: {e}")
            return False  # Fail open: if we can't check, allow the order

    def eod_liquidate_all(self, reason: str = "EOD force-close") -> dict:
        """
        Cancel all open bracket legs for this ticker and submit a market SELL
        for any remaining position. Called ~10 minutes before market close.
        Safe to call even when no position exists (returns early).
        
        Returns: dict with keys: cancelled_orders (int), position_closed (bool), 
                 qty_closed (int), error (str or None)
        """
        result = {"cancelled_orders": 0, "position_closed": False,
                  "qty_closed": 0, "error": None}
        try:
            # Step 1: Cancel all open orders for this ticker
            try:
                open_orders = self.client.get_orders(
                    filter=GetOrdersRequest(
                        status=QueryOrderStatus.OPEN,
                        symbols=[self.ticker],
                        limit=50,
                    )
                )
                for order in open_orders:
                    try:
                        self.client.cancel_order_by_id(order.id)
                        result["cancelled_orders"] += 1
                        logger.info(f"EOD: Cancelled order {order.id} for {self.ticker}")
                    except Exception as e:
                        logger.warning(f"EOD: Failed to cancel order {order.id}: {e}")
            except Exception as e:
                logger.warning(f"EOD: Could not fetch open orders for {self.ticker}: {e}")

            # Step 2: Check if position exists
            position = self.get_current_position()
            if position is None:
                logger.info(f"EOD: No open position for {self.ticker} — nothing to close.")
                return result

            qty = int(float(position["shares"] if isinstance(position, dict) else position.qty))
            if qty <= 0:
                return result

            # Step 3: Submit market SELL to close position
            import time
            time.sleep(0.5)  # Brief pause after cancellations to let Alpaca process
            
            from alpaca.trading.requests import MarketOrderRequest
            from alpaca.trading.enums import OrderSide, TimeInForce

            order_req = MarketOrderRequest(
                symbol=self.ticker,
                qty=qty,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
            )
            order = self.client.submit_order(order_req)
            result["position_closed"] = True
            result["qty_closed"] = qty
            logger.info(
                f"EOD force-close: Submitted SELL {qty}sh {self.ticker} "
                f"| reason={reason} | order_id={order.id}"
            )
            
            # Reset internal tracking
            self._entry_price = None
            self._trailing_stop = None
            if hasattr(self, "_trailing_state"):
                self._trailing_state.pop(self.ticker, None)

        except Exception as e:
            result["error"] = str(e)
            logger.error(f"EOD liquidation failed for {self.ticker}: {e}")

        return result


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

        import config as cfg
        bracket_cfg = getattr(cfg, "BRACKET", {})
        activation_mult = bracket_cfg.get("trailing_activation_atr", 1.8)
        trail_mult = bracket_cfg.get("trailing_stop_atr_mult", 1.2)

        unrealized_gain = current_price - entry
        activation_threshold = activation_mult * atr

        if unrealized_gain >= activation_threshold and not state["trailing_activated"]:
            state["trailing_activated"] = True
            new_stop = round(current_price - (trail_mult * atr), 2)
            logger.info(
                "TRAILING STOP ACTIVATED for %s: gain=$%.2f >= %.1f×ATR($%.2f). "
                "New mental stop=$%.2f (was $%.2f)",
                ticker, unrealized_gain, activation_mult, activation_threshold,
                new_stop, state["stop_price"],
            )
            state["stop_price"] = new_stop
        elif state["trailing_activated"]:
            # Trail the stop up as price moves higher
            trail_stop = round(current_price - (trail_mult * atr), 2)
            if trail_stop > state["stop_price"]:
                logger.info(
                    "TRAILING STOP RAISED for %s: $%.2f -> $%.2f (price=$%.2f)",
                    ticker, state["stop_price"], trail_stop, current_price,
                )
                state["stop_price"] = trail_stop

    def run_tick(
        self,
        df: pd.DataFrame,
        market_regime_bullish: bool = True,
        daily_trend_bullish: bool = True,
        pending_exposure: float = 0.0,
        **kwargs,
    ) -> dict:
        """
        Process a single time bar against the live Alpaca paper environment.

        Parameters
        ----------
        df : pd.DataFrame
            DataFrame containing technical indicators.
        market_regime_bullish : bool, optional
            Whether broad market regime (SPY) is bullish (default True).
        daily_trend_bullish : bool, optional
            Whether higher-timeframe daily trend is bullish (default True).
        pending_exposure : float, optional
            Dollar value of pending/unconfirmed orders from this scan (default 0.0).

        Returns
        -------
        dict
            Tick status output dictionary.
        """
        if df is None or df.empty or "Close" not in df.columns:
            logger.warning(
                f"Invalid or empty DataFrame for {self.ticker} — skipping tick"
            )
            return {
                "action": "SKIP",
                "reason": "Invalid or empty DataFrame",
                "ticker": self.ticker,
                "signal": "HOLD",
                "confidence": 0.0,
            }

        raw_price = df["Close"].iloc[-1]
        if pd.isna(raw_price) or raw_price <= 0:
            logger.warning(
                f"Invalid price for {self.ticker}: {raw_price} — skipping tick"
            )
            return {
                "action": "SKIP",
                "reason": f"Invalid price: {raw_price}",
                "ticker": self.ticker,
                "signal": "HOLD",
                "confidence": 0.0,
            }
        current_price = float(raw_price)

        raw_atr = df["ATR_14"].iloc[-1] if "ATR_14" in df.columns else 0.0
        atr_value = 0.0 if pd.isna(raw_atr) else float(raw_atr)
        market_open = self.is_market_open()
        submitted_buy = False
        order_val = 0.0

        try:
            account = self.get_account_info()
            portfolio_value = account["portfolio_value"]
        except Exception:
            portfolio_value = 100000.0

        can_trade, block_reason = self.risk_manager.can_trade(portfolio_value)
        position = self.get_current_position()

        # Update trailing stops for existing positions
        self._update_trailing_stop(self.ticker, current_price)

        if market_open and position is not None:
            entry_price = position["avg_entry_price"]
            stop_triggered, stop_reason = self.risk_manager.check_stop_loss(
                entry_price, current_price
            )
            if stop_triggered:
                self.submit_sell("ALL", stop_reason)
                return {
                    "signal": "SELL",
                    "reason": stop_reason,
                    "confidence": 1.0,
                    "price": current_price,
                    "portfolio_value": portfolio_value,
                    "position": position,
                    "can_trade": False,
                    "time": datetime.now().isoformat(),
                    "market_open": True,
                }

        # Extract extra context for signal generation (also check kwargs for backward compatibility)
        m_regime_bullish = kwargs.get("market_regime_bullish", market_regime_bullish)
        d_trend_bullish = kwargs.get("daily_trend_bullish", daily_trend_bullish)

        signal_dict = self.signal_generator.generate_signal(
            df, portfolio_value,
            market_regime_bullish=m_regime_bullish,
            daily_trend_bullish=d_trend_bullish,
        )
        signal = signal_dict["signal"]
        confidence = signal_dict["confidence"]

        if not market_open:
            return {
                "signal": signal,
                "confidence": confidence,
                "reasons": signal_dict.get("reasons", []),
                "price": current_price,
                "portfolio_value": portfolio_value,
                "position": position,
                "can_trade": False,
                "time": datetime.now().isoformat(),
                "market_open": False,
                "reason": "Market closed (orders paused)",
            }

        if signal == "BUY" and confidence >= self.min_confidence and can_trade:
            # Portfolio heat check augmented with pending orders from this scan
            all_pos = self.get_all_positions()
            long_exposure = sum(
                p["shares"] * p["current_price"]
                for p in all_pos.values()
            )
            augmented_exposure = long_exposure + pending_exposure
            heat_ok, heat_reason = self.risk_manager.check_portfolio_heat(
                augmented_exposure, portfolio_value
            )

            if heat_ok and position is None:
                # Deduplication: skip if a pending BUY order already exists
                if self._has_pending_buy_order():
                    return {
                        "action": "SKIP",
                        "reason": "Pending BUY order already exists — dedup protection",
                        "ticker": self.ticker,
                        "signal": "HOLD",
                        "confidence": 0.0,
                    }

                # ATR-based position sizing with dollar and percentage caps
                if atr_value > 0 and hasattr(self.risk_manager, "get_position_size_atr"):
                    qty = self.risk_manager.get_position_size_atr(
                        portfolio_value, current_price, atr_value
                    )
                else:
                    qty = self.risk_manager.get_position_size(
                        portfolio_value, current_price
                    )

                if qty > 0:
                    import config
                    bracket_cfg = getattr(config, "BRACKET", {})
                    sl_mult = bracket_cfg.get("stop_loss_atr_mult", 1.5)
                    tp_mult = bracket_cfg.get("take_profit_atr_mult", 3.0)

                    if atr_value > 0:
                        self.submit_bracket_buy(
                            qty,
                            "; ".join(signal_dict["reasons"]),
                            current_price=current_price,
                            atr=atr_value,
                            stop_loss_mult=sl_mult,
                            take_profit_mult=tp_mult,
                        )
                    else:
                        self.submit_buy(qty, "; ".join(signal_dict["reasons"]))
                    self._last_buy_time[self.ticker] = datetime.now()
                    submitted_buy = True
                    order_val = qty * current_price
            elif not heat_ok:
                logger.info("BUY blocked by portfolio heat: %s", heat_reason)

        if signal == "SELL" and position is not None:
            # Check if shares are already committed to bracket orders
            try:
                pos = self.get_current_position()
                if pos is not None:
                    from alpaca.trading.requests import GetOrdersRequest
                    from alpaca.trading.enums import QueryOrderStatus

                    open_orders = self.client.get_orders(
                        GetOrdersRequest(
                            status=QueryOrderStatus.OPEN,
                            symbols=[self.ticker],
                        )
                    )
                    # If there are open bracket legs (stop or limit),
                    # skip manual sell — let bracket handle the exit
                    bracket_legs = [
                        o
                        for o in open_orders
                        if str(getattr(o.order_type, "value", o.order_type)).lower()
                        in ("stop", "limit", "stop_limit")
                    ]
                    if bracket_legs:
                        logger.info(
                            "SELL skipped for %s — bracket exit orders active "
                            "(%d legs). Letting broker handle exit.",
                            self.ticker,
                            len(bracket_legs),
                        )
                    else:
                        # No bracket legs active — safe to manual sell
                        if self.ticker in self._last_buy_time:
                            minutes_held = (
                                datetime.now() - self._last_buy_time[self.ticker]
                            ).total_seconds() / 60
                            if minutes_held < 60:  # minimum 60 minute hold
                                logger.info(
                                    f"Hold filter: only held {minutes_held:.0f}m, skipping SELL"
                                )
                            else:
                                self.submit_sell(
                                    "ALL", "; ".join(signal_dict["reasons"])
                                )
                        else:
                            self.submit_sell(
                                "ALL", "; ".join(signal_dict["reasons"])
                            )
            except Exception as e:
                logger.warning(
                    "Bracket check failed: %s — proceeding with manual sell", e
                )
                if self.ticker in self._last_buy_time:
                    minutes_held = (
                        datetime.now() - self._last_buy_time[self.ticker]
                    ).total_seconds() / 60
                    if minutes_held < 60:  # minimum 60 minute hold
                        logger.info(
                            f"Hold filter: only held {minutes_held:.0f}m, skipping SELL"
                        )
                    else:
                        self.submit_sell(
                            "ALL", "; ".join(signal_dict["reasons"])
                        )
                else:
                    self.submit_sell(
                        "ALL", "; ".join(signal_dict["reasons"])
                    )

        ret = {
            "signal": signal,
            "confidence": confidence,
            "reasons": signal_dict.get("reasons", []),
            "price": current_price,
            "portfolio_value": portfolio_value,
            "position": position,
            "can_trade": can_trade,
            "time": datetime.now().isoformat(),
            "market_open": True,
        }
        if submitted_buy:
            ret["action"] = "BUY"
            ret["order_value"] = order_val
        return ret

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
            if df is None or df.empty or "Close" not in df.columns:
                continue

            raw_price = df["Close"].iloc[-1]
            if pd.isna(raw_price) or raw_price <= 0:
                continue
            current_price = float(raw_price)

            if not market_open:
                sig_dict = self.signal_generator.generate_signal(df, portfolio_value)
                results[ticker] = {
                    "ticker": ticker,
                    "signal": sig_dict["signal"],
                    "confidence": sig_dict["confidence"],
                    "reasons": "; ".join(sig_dict.get("reasons", [])),
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

    def _build_round_trips(self, orders_df: pd.DataFrame) -> pd.DataFrame:
        """
        Match BUY fills to subsequent SELL fills for the same ticker.
        Returns a DataFrame with one row per completed round-trip trade containing:
        - ticker, entry_time, exit_time, entry_price, exit_price,
          qty, pnl, pnl_pct, hold_duration_minutes, side='round_trip'
        Unmatched open BUY positions are excluded (no exit yet).
        """
        if orders_df.empty:
            return pd.DataFrame()

        # Filter to filled orders only
        status_s = orders_df["status"].astype(str).str.lower()
        filled = orders_df[status_s == "filled"].copy()
        if filled.empty:
            return pd.DataFrame()
        filled = filled.sort_values("filled_at").reset_index(drop=True)

        round_trips = []
        open_buys = []  # stack of open BUY fills

        for _, row in filled.iterrows():
            side = str(row["side"]).lower()
            if side == "buy":
                open_buys.append(row)
            elif side == "sell" and open_buys:
                buy = open_buys.pop(0)  # FIFO matching
                qty = min(float(buy["filled_qty"]), float(row["filled_qty"]))
                entry_price = float(buy["filled_avg_price"])
                exit_price = float(row["filled_avg_price"])
                pnl = (exit_price - entry_price) * qty
                pnl_pct = (exit_price - entry_price) / entry_price * 100

                entry_time = pd.to_datetime(buy["filled_at"])
                exit_time = pd.to_datetime(row["filled_at"])
                hold_minutes = (exit_time - entry_time).total_seconds() / 60

                round_trips.append({
                    "ticker": self.ticker,
                    "entry_time": entry_time,
                    "exit_time": exit_time,
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "qty": qty,
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "hold_duration_minutes": hold_minutes,
                    "side": "round_trip",
                    "entry_reason": buy.get("reason", ""),
                    "exit_reason": row.get("reason", ""),
                })

        return pd.DataFrame(round_trips)

    def get_trade_history(self) -> pd.DataFrame:
        """
        Fetch order history directly from Alpaca API for this ticker,
        and build round-trip trades.

        Returns
        -------
        pd.DataFrame
            DataFrame of completed round-trip trades.
        """
        try:
            after_date = datetime.now(timezone.utc) - timedelta(days=7)
            req = GetOrdersRequest(
                status=QueryOrderStatus.ALL,
                symbols=[self.ticker],
                after=after_date,
                limit=500,
            )
            orders = self.client.get_orders(filter=req)
            rows = []
            for o in orders:
                rows.append({
                    "order_id": str(o.id),
                    "timestamp": str(o.submitted_at),
                    "submitted_at": str(o.submitted_at),
                    "filled_at": str(o.filled_at) if o.filled_at else None,
                    "ticker": o.symbol,
                    "symbol": o.symbol,
                    "action": str(o.side.value).lower() if hasattr(o.side, "value") else str(o.side).lower(),
                    "side": str(o.side.value).lower() if hasattr(o.side, "value") else str(o.side).lower(),
                    "quantity": float(o.qty or 0),
                    "qty": float(o.qty or 0),
                    "filled_qty": float(o.filled_qty or 0),
                    "price": float(o.limit_price or o.stop_price or 0),
                    "status": str(o.status.value).lower() if hasattr(o.status, "value") else str(o.status).lower(),
                    "filled_avg_price": float(o.filled_avg_price) if o.filled_avg_price else None,
                })
            orders_df = pd.DataFrame(rows)
            return self._build_round_trips(orders_df)
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
