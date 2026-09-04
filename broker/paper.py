import logging
import os
import sqlite3
import sys
from datetime import datetime
from typing import Optional, Union

import pandas as pd

# Ensure project root is on path when running as a script
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from risk.manager import RiskManager
from strategy.signals import SignalGenerator

# Configure logger for paper broker module
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# Default database path alongside this module
_DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trades.db")


class LocalPaperBroker:
    """
    Simulated paper-trading broker that executes BUY/SELL orders
    against an in-memory balance, persists every trade to a local
    SQLite database, and integrates with a ``RiskManager`` and
    ``SignalGenerator`` for automated decision making.

    This class is the execution engine of the trading bot.  Its
    ``run_tick()`` method is designed to be called once per bar
    (candlestick) and encapsulates the full order-of-operations:
    risk gate -> stop-loss check -> signal evaluation -> order execution.

    Parameters
    ----------
    initial_balance : float, optional
        Starting cash balance in the paper account (default 5000.0).
    ticker : str, optional
        Ticker symbol being traded (default ``'AAPL'``).
    risk_manager : RiskManager or None, optional
        Pre-trade risk management engine.  If ``None``, a default
        ``RiskManager`` is created with the given ``initial_balance``.
    signal_generator : SignalGenerator or None, optional
        Signal generation engine.  If ``None``, a default
        ``SignalGenerator`` is created using the ``risk_manager``.
    min_confidence : float, optional
        Minimum signal confidence required to execute a BUY order
        (default 0.5).
    db_path : str or None, optional
        Path to the SQLite database file.  Defaults to
        ``broker/trades.db`` next to this module.
    """

    def __init__(
        self,
        initial_balance: float = 5000.0,
        ticker: str = "AAPL",
        risk_manager: RiskManager = None,
        signal_generator: SignalGenerator = None,
        min_confidence: float = 0.25,
        db_path: str = None,
    ) -> None:
        """
        Initialise the paper broker.

        Parameters
        ----------
        initial_balance : float, optional
            Starting cash (default 5000.0).
        ticker : str, optional
            Ticker symbol (default ``'AAPL'``).
        risk_manager : RiskManager or None, optional
            Risk engine; created automatically if ``None``.
        signal_generator : SignalGenerator or None, optional
            Signal engine; created automatically if ``None``.
        min_confidence : float, optional
            Confidence threshold for BUY execution (default 0.25).
        db_path : str or None, optional
            SQLite database file path.
        """
        self.initial_balance = initial_balance
        self.cash: float = initial_balance
        self.shares: int = 0
        self.entry_price: float | None = None
        self.ticker = ticker
        self.min_confidence = min_confidence

        # Wire up risk manager
        if risk_manager is None:
            self.risk_manager = RiskManager(initial_balance=initial_balance)
        else:
            self.risk_manager = risk_manager

        # Wire up signal generator
        if signal_generator is None:
            self.signal_generator = SignalGenerator(
                risk_manager=self.risk_manager
            )
        else:
            self.signal_generator = signal_generator

        # SQLite persistence
        self._db_path = db_path or _DEFAULT_DB_PATH
        self._mem_conn: sqlite3.Connection | None = None
        self._init_db()

        logger.info(
            "LocalPaperBroker initialised -- ticker=%s, balance=%.2f, "
            "min_confidence=%.2f, db=%s",
            ticker,
            initial_balance,
            min_confidence,
            self._db_path,
        )

    # ------------------------------------------------------------------
    # Database helpers
    # ------------------------------------------------------------------

    def _get_connection(self) -> sqlite3.Connection:
        """
        Return a SQLite connection.

        For in-memory databases (``':memory:'``), a single persistent
        connection is reused so that all operations share the same
        database.  For file-backed databases, a new connection is
        created each time.

        Returns
        -------
        sqlite3.Connection
        """
        if self._db_path == ":memory:":
            if self._mem_conn is None:
                self._mem_conn = sqlite3.connect(":memory:")
            return self._mem_conn
        return sqlite3.connect(self._db_path)

    def _close_connection(self, conn: sqlite3.Connection) -> None:
        """
        Close a connection only if it is *not* the persistent
        in-memory connection.
        """
        if self._db_path != ":memory:":
            conn.close()

    def _init_db(self) -> None:
        """
        Create the trades table in the SQLite database if it does
        not already exist.
        """
        conn = self._get_connection()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trades (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp  TEXT    NOT NULL,
                    action     TEXT    NOT NULL,
                    ticker     TEXT    NOT NULL,
                    price      REAL    NOT NULL,
                    quantity   INTEGER NOT NULL,
                    cash_after REAL    NOT NULL,
                    reason     TEXT,
                    pnl        REAL
                )
                """
            )
            conn.commit()
        finally:
            self._close_connection(conn)
        logger.debug("SQLite trades table ready at %s", self._db_path)

    def _save_trade(self, trade: dict) -> None:
        """
        Persist a single trade record to the SQLite database.

        Parameters
        ----------
        trade : dict
            Trade dictionary as returned by ``execute_buy`` or
            ``execute_sell``.
        """
        conn = self._get_connection()
        try:
            conn.execute(
                """
                INSERT INTO trades
                    (timestamp, action, ticker, price, quantity,
                     cash_after, reason, pnl)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trade["timestamp"],
                    trade["action"],
                    trade["ticker"],
                    trade["price"],
                    trade["quantity"],
                    trade["cash_after"],
                    trade["reason"],
                    trade["pnl"],
                ),
            )
            conn.commit()
        finally:
            self._close_connection(conn)
        logger.debug("Trade saved to SQLite: %s", trade)

    # ------------------------------------------------------------------
    # Portfolio helpers
    # ------------------------------------------------------------------

    def get_portfolio_value(self, current_price: float) -> float:
        """
        Calculate the total portfolio value (cash + holdings).

        Parameters
        ----------
        current_price : float
            Current market price per share.

        Returns
        -------
        float
            Total portfolio value.
        """
        return self.cash + (self.shares * current_price)

    # ------------------------------------------------------------------
    # Order execution
    # ------------------------------------------------------------------

    def execute_buy(self, price: float, quantity: int, reason: str) -> dict:
        """
        Execute a paper BUY order.

        Deducts the cost from cash, adds shares, records the entry
        price, and persists the trade to SQLite.

        Parameters
        ----------
        price : float
            Execution price per share.
        quantity : int
            Number of shares to purchase.
        reason : str
            Human-readable reason for the trade.

        Returns
        -------
        dict
            Trade record dictionary, or empty dict if the order
            could not be executed.
        """
        cost = price * quantity

        # Guard: can we afford it?
        max_affordable = int(self.cash // price) if price > 0 else 0
        if quantity > max_affordable:
            logger.warning(
                "BUY quantity %d exceeds affordable %d at price %.2f "
                "(cash=%.2f). Clamping.",
                quantity,
                max_affordable,
                price,
                self.cash,
            )
            quantity = max_affordable
            cost = price * quantity

        if quantity <= 0:
            logger.warning("BUY skipped -- 0 affordable shares at %.2f.", price)
            return {}

        self.cash -= cost
        self.shares += quantity
        self.entry_price = price

        trade = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "action": "BUY",
            "ticker": self.ticker,
            "price": round(price, 4),
            "quantity": quantity,
            "cash_after": round(self.cash, 2),
            "reason": reason,
            "pnl": 0.0,
        }

        self._save_trade(trade)
        logger.info(
            "BUY executed -- %d x %s @ %.2f | cost=%.2f | cash_after=%.2f",
            quantity,
            self.ticker,
            price,
            cost,
            self.cash,
        )
        return trade

    def execute_sell(
        self, price: float, quantity: Union[int, str], reason: str
    ) -> dict:
        """
        Execute a paper SELL order.

        Adds proceeds to cash, reduces shares, calculates realised PnL,
        and persists the trade to SQLite.

        Parameters
        ----------
        price : float
            Execution price per share.
        quantity : int or str
            Number of shares to sell, or the string ``"ALL"`` to
            liquidate the entire position.
        reason : str
            Human-readable reason for the trade.

        Returns
        -------
        dict
            Trade record dictionary, or empty dict if no shares to sell.
        """
        # Resolve "ALL"
        if isinstance(quantity, str) and quantity.upper() == "ALL":
            quantity = self.shares

        if quantity <= 0 or self.shares <= 0:
            logger.warning("SELL skipped -- no shares to sell.")
            return {}

        quantity = min(quantity, self.shares)

        # PnL calculation
        pnl = 0.0
        if self.entry_price is not None:
            pnl = (price - self.entry_price) * quantity

        proceeds = price * quantity
        self.cash += proceeds
        self.shares -= quantity

        # Clear entry price when fully exited
        if self.shares == 0:
            self.entry_price = None

        trade = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "action": "SELL",
            "ticker": self.ticker,
            "price": round(price, 4),
            "quantity": quantity,
            "cash_after": round(self.cash, 2),
            "reason": reason,
            "pnl": round(pnl, 2),
        }

        self._save_trade(trade)
        pnl_label = f"+{pnl:.2f}" if pnl >= 0 else f"{pnl:.2f}"
        logger.info(
            "SELL executed -- %d x %s @ %.2f | proceeds=%.2f | "
            "PnL=%s | cash_after=%.2f",
            quantity,
            self.ticker,
            price,
            proceeds,
            pnl_label,
            self.cash,
        )
        return trade

    # ------------------------------------------------------------------
    # Main tick loop
    # ------------------------------------------------------------------

    def run_tick(self, df: pd.DataFrame) -> dict:
        """
        Process a single time-step (bar) of market data.

        This is the **main loop method** and enforces a strict order
        of operations:

        1. Read current price from the last row of *df*.
        2. Call ``risk_manager.can_trade()`` (circuit-breaker gate).
        3. If holding shares, check stop-loss; sell if triggered.
        4. Call ``signal_generator.generate_signal()``.
        5. If BUY signal with sufficient confidence: size and buy.
        6. If SELL signal: liquidate position.
        7. Return a status dictionary.

        Parameters
        ----------
        df : pd.DataFrame
            DataFrame with indicator columns already added.
            The **last row** is treated as the current bar.

        Returns
        -------
        dict
            Status dictionary containing the action taken, current
            portfolio state, and any trade executed.
        """
        # (a) Current price from last row
        current_price = float(df.iloc[-1]["Close"])
        portfolio_value = self.get_portfolio_value(current_price)

        # Resolve the bar's timestamp for backtest-aware cooldown tracking.
        # During a backtest the index is a DatetimeIndex; during live trading
        # it may be a string or already a datetime — we normalise to datetime.
        raw_ts = df.index[-1]
        try:
            if isinstance(raw_ts, datetime):
                bar_time: Optional[datetime] = raw_ts.replace(tzinfo=None)
            else:
                bar_time = pd.Timestamp(raw_ts).to_pydatetime().replace(tzinfo=None)
        except Exception:
            bar_time = None  # fall back to wall-clock time

        status = {
            "timestamp": str(df.index[-1]),
            "price": round(current_price, 4),
            "portfolio_value": round(portfolio_value, 2),
            "cash": round(self.cash, 2),
            "shares": self.shares,
            "action": "HOLD",
            "trade": None,
            "signal": None,
        }

        # (b) Risk gate -- checked FIRST, using bar time for backtest awareness
        can_trade, block_reason = self.risk_manager.can_trade(
            portfolio_value, as_of=bar_time
        )

        # (c) Stop-loss check for open positions
        if self.shares > 0 and self.entry_price is not None:
            triggered, sl_reason = self.risk_manager.check_stop_loss(
                self.entry_price, current_price, as_of=bar_time
            )
            if triggered:
                logger.warning(
                    "Stop-loss triggered at price %.2f (entry %.2f) -- "
                    "liquidating position.",
                    current_price,
                    self.entry_price,
                )
                trade = self.execute_sell(current_price, "ALL", sl_reason)
                status["action"] = "SELL (stop-loss)"
                status["trade"] = trade
                status["cash"] = round(self.cash, 2)
                status["shares"] = self.shares
                status["portfolio_value"] = round(
                    self.get_portfolio_value(current_price), 2
                )
                return status

        # (d) Generate signal
        signal = self.signal_generator.generate_signal(df, portfolio_value)
        status["signal"] = signal

        # (e) BUY if signal is strong enough and not blocked
        if (
            signal["signal"] == "BUY"
            and signal["confidence"] >= self.min_confidence
            and not signal["blocked"]
        ):
            qty = self.risk_manager.get_position_size(
                portfolio_value, current_price
            )
            # Also cap by what we can actually afford
            max_affordable = int(self.cash // current_price) if current_price > 0 else 0
            qty = min(qty, max_affordable)

            if qty > 0:
                reason = "; ".join(signal["reasons"])
                trade = self.execute_buy(current_price, qty, reason)
                if trade:
                    status["action"] = "BUY"
                    status["trade"] = trade
                    status["cash"] = round(self.cash, 2)
                    status["shares"] = self.shares
                    status["portfolio_value"] = round(
                        self.get_portfolio_value(current_price), 2
                    )
                    return status

        # (f) SELL if signal says so
        if signal["signal"] == "SELL":
            if self.shares == 0:
                # Nothing to sell, skip
                pass
            else:
                reason = "; ".join(signal["reasons"])
                trade = self.execute_sell(current_price, "ALL", reason)
                if trade:
                    status["action"] = "SELL"
                    status["trade"] = trade
                    status["cash"] = round(self.cash, 2)
                    status["shares"] = self.shares
                    status["portfolio_value"] = round(
                        self.get_portfolio_value(current_price), 2
                    )
                    return status

        # (g) No action taken
        logger.debug(
            "HOLD -- price=%.2f, portfolio=%.2f, shares=%d",
            current_price,
            portfolio_value,
            self.shares,
        )
        return status

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def get_trade_history(self) -> pd.DataFrame:
        """
        Load all trade records from the SQLite database.

        Returns
        -------
        pd.DataFrame
            DataFrame containing every trade executed by this broker,
            ordered chronologically.
        """
        conn = self._get_connection()
        try:
            df = pd.read_sql_query(
                "SELECT * FROM trades ORDER BY id", conn
            )
        finally:
            self._close_connection(conn)
        return df

    def get_performance_summary(self, current_price: float = None) -> dict:
        """
        Compute a performance summary for the paper account.

        Parameters
        ----------
        current_price : float or None, optional
            Current market price used to value open positions.
            If ``None``, open positions are valued at the entry price
            or zero.

        Returns
        -------
        dict
            Dictionary containing:
            - total_trades
            - winning_trades
            - losing_trades
            - win_rate
            - total_pnl
            - current_portfolio_value
            - return_pct (vs initial balance)
        """
        history = self.get_trade_history()

        # Closed-trade stats
        sells = history[history["action"] == "SELL"] if not history.empty else pd.DataFrame()

        total_trades = len(sells)
        winning = len(sells[sells["pnl"] > 0]) if not sells.empty else 0
        losing = len(sells[sells["pnl"] < 0]) if not sells.empty else 0
        total_pnl = float(sells["pnl"].sum()) if not sells.empty else 0.0
        win_rate = (winning / total_trades * 100) if total_trades > 0 else 0.0

        # Portfolio valuation
        if current_price is not None:
            portfolio_val = self.get_portfolio_value(current_price)
        elif self.entry_price is not None:
            portfolio_val = self.get_portfolio_value(self.entry_price)
        else:
            portfolio_val = self.cash

        return_pct = (
            (portfolio_val - self.initial_balance) / self.initial_balance * 100
        )

        summary = {
            "total_trades": total_trades,
            "winning_trades": winning,
            "losing_trades": losing,
            "win_rate": round(win_rate, 2),
            "total_pnl": round(total_pnl, 2),
            "current_portfolio_value": round(portfolio_val, 2),
            "return_pct": round(return_pct, 2),
        }

        logger.info("Performance summary: %s", summary)
        return summary


# ======================================================================
# Self-test / demonstration
# ======================================================================
if __name__ == "__main__":
    from datetime import date, timedelta

    from data.fetcher import get_historical_data
    from strategy.indicators import add_all_indicators

    BALANCE = 5000.0
    TICKER = "AAPL"
    LOOKBACK_DAYS = 180
    SIM_WINDOW = 30

    # Use a temporary in-memory DB for the demo so we don't pollute
    # the real trades.db with test data.
    DEMO_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trades_demo.db")

    # Clean up any previous demo DB
    if os.path.exists(DEMO_DB):
        os.remove(DEMO_DB)

    print("=" * 70)
    print("  LocalPaperBroker -- Backtest Simulation")
    print("=" * 70)

    # ------------------------------------------------------------------
    # 1. Fetch data and compute indicators
    # ------------------------------------------------------------------
    end_date = date.today()
    start_date = end_date - timedelta(days=LOOKBACK_DAYS)

    print(f"\nFetching {TICKER} data from {start_date} to {end_date}...")
    raw_df = get_historical_data(TICKER, str(start_date), str(end_date))
    df = add_all_indicators(raw_df)
    print(f"Total rows: {len(df)}  |  Simulating last {SIM_WINDOW} bars\n")

    # ------------------------------------------------------------------
    # 2. Set up components
    # ------------------------------------------------------------------
    rm = RiskManager(initial_balance=BALANCE)
    sg = SignalGenerator(risk_manager=rm, require_confirmation=False)
    broker = LocalPaperBroker(
        initial_balance=BALANCE,
        ticker=TICKER,
        risk_manager=rm,
        signal_generator=sg,
        min_confidence=0.5,
        db_path=DEMO_DB,
    )

    # ------------------------------------------------------------------
    # 3. Simulate: iterate through last SIM_WINDOW rows
    # ------------------------------------------------------------------
    n = len(df)
    print(f"{'Bar':>4}  {'Date':>12}  {'Close':>10}  {'Action':>16}  "
          f"{'Shares':>7}  {'Cash':>10}  {'Portfolio':>10}")
    print("-" * 80)

    for i in range(SIM_WINDOW):
        # Slice DataFrame up to and including this bar
        end_idx = n - SIM_WINDOW + 1 + i
        window_df = df.iloc[:end_idx]

        result = broker.run_tick(window_df)

        print(
            f"{i + 1:>4}  "
            f"{str(result['timestamp'])[:10]:>12}  "
            f"{result['price']:>10.2f}  "
            f"{result['action']:>16}  "
            f"{result['shares']:>7}  "
            f"{result['cash']:>10.2f}  "
            f"{result['portfolio_value']:>10.2f}"
        )

    # ------------------------------------------------------------------
    # 4. Trade history
    # ------------------------------------------------------------------
    history = broker.get_trade_history()
    print(f"\n{'=' * 70}")
    print("  Trade History")
    print(f"{'=' * 70}")
    if history.empty:
        print("  No trades executed during simulation.")
    else:
        display_cols = ["timestamp", "action", "ticker", "price",
                        "quantity", "cash_after", "pnl", "reason"]
        # Truncate reason for display
        history_display = history[display_cols].copy()
        history_display["reason"] = history_display["reason"].str[:50]
        print(history_display.to_string(index=False))

    # ------------------------------------------------------------------
    # 5. Performance summary
    # ------------------------------------------------------------------
    last_price = float(df.iloc[-1]["Close"])
    summary = broker.get_performance_summary(current_price=last_price)

    print(f"\n{'=' * 70}")
    print("  Performance Summary")
    print(f"{'=' * 70}")
    for k, v in summary.items():
        label = k.replace("_", " ").title()
        if "pct" in k.lower():
            print(f"  {label}: {v}%")
        elif "pnl" in k.lower() or "value" in k.lower():
            print(f"  {label}: {v:.2f}")
        else:
            print(f"  {label}: {v}")

    # Clean up demo DB
    if os.path.exists(DEMO_DB):
        os.remove(DEMO_DB)

    print(f"\n{'=' * 70}")
    print("  Simulation complete.")
    print(f"{'=' * 70}")
