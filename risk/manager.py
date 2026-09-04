import logging
from datetime import datetime, timedelta
from typing import Optional

# Configure logger for risk manager module
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


class RiskManager:
    """
    Pre-trade risk management engine that acts as a circuit breaker
    for a quantitative trading system.

    The RiskManager enforces portfolio-level and trade-level risk limits
    including daily loss caps, per-trade stop-losses, position sizing
    constraints, and cooldown periods after adverse events.

    This class must be consulted **before every trade** via ``can_trade()``
    to ensure that no order is placed while risk limits are breached.

    Parameters
    ----------
    initial_balance : float
        Starting portfolio balance used as the baseline for daily loss
        calculations.
    max_daily_loss_pct : float, optional
        Maximum allowable portfolio drawdown in a single trading day,
        expressed as a fraction (default 0.05 = 5%).
    max_trade_loss_pct : float, optional
        Maximum loss tolerated on a single trade before a stop-loss
        triggers, expressed as a fraction (default 0.02 = 2%).
    max_position_pct : float, optional
        Maximum fraction of total portfolio value that may be allocated
        to a single position (default 0.10 = 10%).
    cooldown_minutes : int, optional
        Number of minutes to suspend trading after a stop-loss event
        (default 30).
    """

    def __init__(
        self,
        initial_balance: float,
        max_daily_loss_pct: float = 0.05,
        max_trade_loss_pct: float = 0.02,
        max_position_pct: float = 0.10,
        cooldown_minutes: int = 30,
        max_position_dollars: float = 2000.0,
        max_portfolio_heat_pct: float = 0.60,
        atr_period: int = 14,
        atr_multiplier_k: float = 2.0,
        risk_pct_per_trade: float = 0.01,
    ) -> None:
        """
        Initialise the RiskManager with portfolio parameters and risk limits.

        Parameters
        ----------
        initial_balance : float
            Starting portfolio balance for the current trading day.
        max_daily_loss_pct : float, optional
            Max daily portfolio drawdown fraction (default 0.05).
        max_trade_loss_pct : float, optional
            Max per-trade loss fraction before stop-loss fires (default 0.02).
        max_position_pct : float, optional
            Max fraction of portfolio in a single position (default 0.10).
        cooldown_minutes : int, optional
            Minutes to wait after a stop-loss trigger (default 30).
        """
        self.initial_balance: float = initial_balance
        self.max_daily_loss_pct: float = max_daily_loss_pct
        self.max_trade_loss_pct: float = max_trade_loss_pct
        self.max_position_pct: float = max_position_pct
        self.cooldown_minutes: int = cooldown_minutes
        self.max_position_dollars: float = max_position_dollars
        self.max_portfolio_heat_pct: float = max_portfolio_heat_pct
        self.atr_period: int = atr_period
        self.atr_multiplier_k: float = atr_multiplier_k
        self.risk_pct_per_trade: float = risk_pct_per_trade

        # Daily tracking state
        self._day_start_balance: float = initial_balance
        self._daily_loss_breached: bool = False

        # Cooldown state
        self._cooldown_until: datetime | None = None
        self._stop_loss_count: int = 0

        logger.info(
            "RiskManager initialised -- balance=%.2f, max_daily_loss=%.1f%%, "
            "max_trade_loss=%.1f%%, max_position=%.1f%%, cooldown=%dmin, "
            "max_pos_dollars=$%.0f, portfolio_heat=%.0f%%",
            initial_balance,
            max_daily_loss_pct * 100,
            max_trade_loss_pct * 100,
            max_position_pct * 100,
            cooldown_minutes,
            max_position_dollars,
            max_portfolio_heat_pct * 100,
        )

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def can_trade(
        self,
        current_portfolio_value: float,
        as_of: Optional[datetime] = None,
    ) -> tuple[bool, str]:
        """
        Circuit-breaker check — **must** be called before every trade.

        Returns whether trading is currently permitted, along with a
        human-readable reason if it is not.

        Parameters
        ----------
        current_portfolio_value : float
            Current total portfolio value (cash + holdings).
        as_of : datetime or None, optional
            The reference timestamp to use when evaluating the cooldown
            period.  Pass the current **bar's timestamp** during backtesting
            so that cooldown logic is based on candle time rather than
            wall-clock time.  Defaults to ``datetime.now()``.

        Returns
        -------
        tuple[bool, str]
            ``(True, "OK")`` if trading is allowed, otherwise
            ``(False, reason)`` describing which limit was breached.
        """
        now = as_of if as_of is not None else datetime.now()

        # 1. Check daily loss limit
        daily_loss_pct = (
            (self._day_start_balance - current_portfolio_value)
            / self._day_start_balance
        )
        if daily_loss_pct >= self.max_daily_loss_pct:
            self._daily_loss_breached = True
            reason = (
                f"Daily loss limit breached: portfolio down {daily_loss_pct:.2%} "
                f"(limit {self.max_daily_loss_pct:.2%}) from day-start "
                f"balance of {self._day_start_balance:.2f}"
            )
            logger.warning(reason)
            return False, reason

        if self._daily_loss_breached:
            reason = (
                "Trading halted for the day -- daily loss limit was "
                "previously breached"
            )
            logger.warning(reason)
            return False, reason

        # 2. Check cooldown period
        if self._cooldown_until is not None:
            if now < self._cooldown_until:
                remaining = (self._cooldown_until - now).total_seconds()
                reason = (
                    f"Cooldown active -- {remaining:.0f}s remaining "
                    f"(until {self._cooldown_until.strftime('%H:%M:%S')})"
                )
                logger.warning(reason)
                return False, reason
            else:
                logger.info("Cooldown period has expired -- trading resumed.")
                self._cooldown_until = None

        logger.debug(
            "can_trade check passed -- portfolio value=%.2f, daily_loss=%.2f%%",
            current_portfolio_value,
            daily_loss_pct * 100,
        )
        return True, "OK"

    def get_position_size(
        self, current_portfolio_value: float, price_per_share: float
    ) -> int:
        """
        Calculate the maximum number of shares that may be purchased
        for a single position without exceeding the position-size limit.

        Returns 0 if ``can_trade()`` would deny the trade.

        Parameters
        ----------
        current_portfolio_value : float
            Current total portfolio value (cash + holdings).
        price_per_share : float
            Current price of the asset to be purchased.

        Returns
        -------
        int
            Maximum number of whole shares allowed, or 0 if trading
            is currently blocked.
        """
        allowed, reason = self.can_trade(current_portfolio_value)
        if not allowed:
            logger.info(
                "get_position_size returning 0 -- trading blocked: %s", reason
            )
            return 0

        if price_per_share <= 0:
            logger.error(
                "Invalid price_per_share=%.4f -- returning 0", price_per_share
            )
            return 0

        max_notional = current_portfolio_value * self.max_position_pct
        max_shares = int(max_notional // price_per_share)

        logger.info(
            "Position sizing: portfolio=%.2f, max_notional=%.2f, "
            "price=%.2f -> max_shares=%d",
            current_portfolio_value,
            max_notional,
            price_per_share,
            max_shares,
        )
        return max_shares

    def check_stop_loss(
        self,
        entry_price: float,
        current_price: float,
        as_of: Optional[datetime] = None,
    ) -> tuple[bool, str]:
        """
        Evaluate whether the current price has breached the per-trade
        stop-loss threshold relative to the entry price.

        If a stop-loss is triggered, a cooldown timer is automatically
        started to prevent immediate re-entry.

        Parameters
        ----------
        entry_price : float
            Price at which the position was opened.
        current_price : float
            Current market price of the asset.
        as_of : datetime or None, optional
            The reference timestamp used as the cooldown start time.
            Pass the current **bar's timestamp** during backtesting so
            that the cooldown is calculated from candle time, not wall-clock
            time.  Defaults to ``datetime.now()``.

        Returns
        -------
        tuple[bool, str]
            ``(True, reason)`` if the stop-loss should trigger,
            ``(False, "OK")`` if the position is safe.
        """
        if entry_price <= 0:
            logger.error("Invalid entry_price=%.4f", entry_price)
            return False, "OK"

        loss_pct = (entry_price - current_price) / entry_price

        if loss_pct >= self.max_trade_loss_pct:
            self._stop_loss_count += 1
            now = as_of if as_of is not None else datetime.now()
            self._cooldown_until = now + timedelta(minutes=self.cooldown_minutes)
            reason = (
                f"STOP-LOSS triggered: price dropped {loss_pct:.2%} "
                f"(limit {self.max_trade_loss_pct:.2%}), "
                f"entry={entry_price:.2f}, current={current_price:.2f}. "
                f"Cooldown active for {self.cooldown_minutes}min "
                f"(until {self._cooldown_until.strftime('%H:%M:%S')})"
            )
            logger.warning(reason)
            return True, reason

        logger.debug(
            "Stop-loss OK -- entry=%.2f, current=%.2f, loss=%.2f%%",
            entry_price,
            current_price,
            loss_pct * 100,
        )
        return False, "OK"

    def get_position_size_atr(
        self,
        equity: float,
        price_per_share: float,
        atr: float,
    ) -> int:
        """
        ATR-based position sizing with dollar cap and percentage cap.

        Shares = floor(equity × risk_pct / (ATR × k)),
        capped by min(max_position_dollars, equity × max_position_pct).

        Parameters
        ----------
        equity : float
            Current total portfolio equity.
        price_per_share : float
            Current price of the asset.
        atr : float
            Current Average True Range value for the asset.

        Returns
        -------
        int
            Maximum number of shares allowed.
        """
        allowed, reason = self.can_trade(equity)
        if not allowed:
            logger.info(
                "get_position_size_atr returning 0 -- blocked: %s", reason
            )
            return 0

        if price_per_share <= 0 or atr <= 0:
            logger.error(
                "Invalid price=%.4f or atr=%.4f -- returning 0",
                price_per_share, atr,
            )
            return 0

        # ATR-based share count
        shares_by_atr = int(
            (equity * self.risk_pct_per_trade) // (atr * self.atr_multiplier_k)
        )

        # Dollar / percentage cap
        dollar_cap = min(
            self.max_position_dollars,
            equity * self.max_position_pct,
        )
        shares_by_cap = int(dollar_cap // price_per_share)

        final_shares = max(0, min(shares_by_atr, shares_by_cap))

        logger.info(
            "ATR position sizing: equity=%.2f, price=%.2f, ATR=%.2f, "
            "shares_atr=%d, shares_cap=%d -> final=%d",
            equity, price_per_share, atr,
            shares_by_atr, shares_by_cap, final_shares,
        )
        return final_shares

    def check_portfolio_heat(
        self,
        current_long_exposure: float,
        total_equity: float,
    ) -> tuple[bool, str]:
        """
        Check whether combined long exposure exceeds the portfolio heat limit.

        Parameters
        ----------
        current_long_exposure : float
            Total market value of all open long positions.
        total_equity : float
            Current total portfolio equity.

        Returns
        -------
        tuple[bool, str]
            ``(True, "OK")`` if new buys are permitted,
            ``(False, reason)`` if heat limit is breached.
        """
        if total_equity <= 0:
            return False, "Invalid total equity"

        heat_pct = current_long_exposure / total_equity

        if heat_pct >= self.max_portfolio_heat_pct:
            reason = (
                f"Portfolio heat limit breached: {heat_pct:.1%} long exposure "
                f"(limit {self.max_portfolio_heat_pct:.1%}). "
                f"Exposure=${current_long_exposure:,.0f}, "
                f"equity=${total_equity:,.0f}"
            )
            logger.warning(reason)
            return False, reason

        logger.debug(
            "Portfolio heat OK: %.1f%% (limit %.1f%%)",
            heat_pct * 100, self.max_portfolio_heat_pct * 100,
        )
        return True, "OK"

    def reset_daily_state(self) -> None:
        """
        Reset all daily risk-tracking state.

        Call this at the start of each trading day to clear the daily
        loss breach flag and update the day-start balance.
        """
        self._daily_loss_breached = False
        self._cooldown_until = None
        logger.info(
            "Daily state reset -- day-start balance=%.2f", self._day_start_balance
        )

    def get_status(self) -> dict:
        """
        Return a snapshot of the current risk-management state for
        logging, monitoring dashboards, or diagnostics.

        Returns
        -------
        dict
            Dictionary containing all current risk state fields.
        """
        now = datetime.now()
        cooldown_active = (
            self._cooldown_until is not None and now < self._cooldown_until
        )
        cooldown_remaining_s = (
            max(0, (self._cooldown_until - now).total_seconds())
            if cooldown_active
            else 0
        )

        status = {
            "initial_balance": self.initial_balance,
            "day_start_balance": self._day_start_balance,
            "daily_loss_breached": self._daily_loss_breached,
            "cooldown_active": cooldown_active,
            "cooldown_remaining_seconds": round(cooldown_remaining_s),
            "stop_loss_count_today": self._stop_loss_count,
            "max_daily_loss_pct": self.max_daily_loss_pct,
            "max_trade_loss_pct": self.max_trade_loss_pct,
            "max_position_pct": self.max_position_pct,
            "cooldown_minutes": self.cooldown_minutes,
        }
        logger.debug("RiskManager status: %s", status)
        return status


# ======================================================================
# Self-test / demonstration
# ======================================================================
if __name__ == "__main__":
    STARTING_BALANCE = 5000.0
    PASS = "[PASS]"
    FAIL = "[FAIL]"

    print("=" * 64)
    print("  RiskManager -- Self-Test Suite")
    print("=" * 64)

    # ------------------------------------------------------------------
    # Scenario 1: Stop-loss triggers and cooldown blocks next trade
    # ------------------------------------------------------------------
    print("\n--- Scenario 1: Stop-loss -> Cooldown ---")
    rm = RiskManager(
        initial_balance=STARTING_BALANCE,
        max_trade_loss_pct=0.02,
        cooldown_minutes=30,
    )

    # Before stop-loss, trading should be allowed
    allowed, msg = rm.can_trade(STARTING_BALANCE)
    result = PASS if allowed else FAIL
    print(f"  [1a] Trade allowed before any event: {result}  ({msg})")

    # Simulate a trade entry at 100, price drops to 97 (3% loss > 2% limit)
    triggered, reason = rm.check_stop_loss(entry_price=100.0, current_price=97.0)
    result = PASS if triggered else FAIL
    print(f"  [1b] Stop-loss triggers at 3% drop:  {result}  ({reason})")

    # Immediately after stop-loss, trading should be blocked by cooldown
    allowed, msg = rm.can_trade(STARTING_BALANCE)
    result = PASS if not allowed else FAIL
    print(f"  [1c] Cooldown blocks next trade:      {result}  ({msg})")

    # Position size should return 0 during cooldown
    shares = rm.get_position_size(STARTING_BALANCE, price_per_share=100.0)
    result = PASS if shares == 0 else FAIL
    print(f"  [1d] Position size is 0 in cooldown:  {result}  (shares={shares})")

    # ------------------------------------------------------------------
    # Scenario 2: Daily loss breach halts all trading
    # ------------------------------------------------------------------
    print("\n--- Scenario 2: Daily Loss Breach ---")
    rm2 = RiskManager(
        initial_balance=STARTING_BALANCE,
        max_daily_loss_pct=0.05,
    )

    # Portfolio drops from 5000 to 4700 (6% loss > 5% limit)
    depleted_value = STARTING_BALANCE * 0.94  # 4700
    allowed, msg = rm2.can_trade(depleted_value)
    result = PASS if not allowed else FAIL
    print(f"  [2a] Daily loss breach blocks trade:  {result}  ({msg})")

    # Even if portfolio recovers, daily breach flag stays set
    allowed, msg = rm2.can_trade(STARTING_BALANCE)
    result = PASS if not allowed else FAIL
    print(f"  [2b] Stays blocked after recovery:    {result}  ({msg})")

    # Reset clears the daily breach
    rm2.reset_daily_state()
    allowed, msg = rm2.can_trade(STARTING_BALANCE)
    result = PASS if allowed else FAIL
    print(f"  [2c] Allowed after daily reset:       {result}  ({msg})")

    # ------------------------------------------------------------------
    # Scenario 3: Position sizing respects max_position_pct
    # ------------------------------------------------------------------
    print("\n--- Scenario 3: Position Sizing ---")
    rm3 = RiskManager(
        initial_balance=STARTING_BALANCE,
        max_position_pct=0.10,
    )

    # 10% of 5000 = 500.  At 100/share -> max 5 shares
    shares = rm3.get_position_size(STARTING_BALANCE, price_per_share=100.0)
    result = PASS if shares == 5 else FAIL
    print(f"  [3a] Max shares at 100 (10% rule):   {result}  (shares={shares}, expected=5)")

    # At 250/share -> max 2 shares (500 / 250 = 2)
    shares = rm3.get_position_size(STARTING_BALANCE, price_per_share=250.0)
    result = PASS if shares == 2 else FAIL
    print(f"  [3b] Max shares at 250 (10% rule):   {result}  (shares={shares}, expected=2)")

    # ------------------------------------------------------------------
    # Scenario 4: get_status returns valid dict
    # ------------------------------------------------------------------
    print("\n--- Scenario 4: Status Snapshot ---")
    status = rm.get_status()
    expected_keys = {
        "initial_balance", "day_start_balance", "daily_loss_breached",
        "cooldown_active", "cooldown_remaining_seconds",
        "stop_loss_count_today", "max_daily_loss_pct",
        "max_trade_loss_pct", "max_position_pct", "cooldown_minutes",
    }
    has_all_keys = expected_keys.issubset(status.keys())
    result = PASS if has_all_keys else FAIL
    print(f"  [4a] Status dict has all keys:        {result}")
    for k, v in status.items():
        print(f"        {k}: {v}")

    print("\n" + "=" * 64)
    print("  Self-test complete.")
    print("=" * 64)
