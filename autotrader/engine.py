"""SPY_POWER_CASHFLOW decision engine.

Pure logic, no broker calls. Once per trading day (shortly before the close) the
bot builds a Snapshot of the account, calls `decide`, and executes the returned
actions in order. The engine applies each action's expected effect to a working
copy of the portfolio, so later decisions in the same day see earlier ones,
exactly as the backtest's day loop did.

Rules ported from algo_trading/SPY_POWER_CASHFLOW/trading_simulator.py:
  * First run with no shares: buy initial_position_percent of equity.
  * First trading day handled in a month: sell covered calls on all uncovered
    shares, strike max(1.5%, VIX*0.15) OTM rounded to $5, expiring on the
    month's last trading day.
  * Every day: track the high since the last buy; if leverage is above the
    VIX-tiered limit, close calls (highest strike first) and sell shares;
    if price fell to the VIX-tiered dip trigger, buy with part of buying power.
  * Last trading day of the month: buy back expiring ITM calls (selling shares
    only if buying power can't fund it), let OTM calls expire, and withdraw
    monthly_withdrawal_rate% of equity.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

from .config import StrategyConfig
from .pricing import estimate_call_premium, target_call_strike


@dataclass
class ShortCall:
    strike: float
    expiry: date
    contracts: int
    premium: float  # per share, at open
    open_date: date


@dataclass
class Snapshot:
    day: date
    price: float
    vix: float  # decimal, 0.18 = VIX 18
    shares: int
    cash: float  # negative when on margin; already net of any virtual withdrawals
    short_calls: List[ShortCall]
    month_last_trading_day: date

    @property
    def is_month_end(self) -> bool:
        return self.day >= self.month_last_trading_day


@dataclass
class EngineState:
    """Persisted between runs (the bot saves it as JSON)."""

    highest_since_last_buy: float = 0.0
    calls_written_month: Optional[str] = None  # "YYYY-MM"
    month_end_done: Optional[str] = None  # "YYYY-MM"


@dataclass
class Action:
    kind: str  # BUY_STOCK | SELL_STOCK | SELL_CALL | BUY_CALL | WITHDRAW
    reason: str
    shares: int = 0
    contracts: int = 0
    strike: float = 0.0
    expiry: Optional[date] = None
    est_price: float = 0.0  # stock price or option premium per share
    amount: float = 0.0  # WITHDRAW only

    def describe(self) -> str:
        if self.kind in ("BUY_STOCK", "SELL_STOCK"):
            return f"{self.kind} {self.shares} @ ~{self.est_price:.2f} ({self.reason})"
        if self.kind in ("SELL_CALL", "BUY_CALL"):
            return (
                f"{self.kind} {self.contracts}x {self.strike:.0f}C {self.expiry} "
                f"@ ~{self.est_price:.2f} ({self.reason})"
            )
        return f"{self.kind} ${self.amount:,.2f} ({self.reason})"


@dataclass
class _Book:
    """Working copy of the portfolio used while deciding."""

    price: float
    shares: int
    cash: float
    calls: List[ShortCall] = field(default_factory=list)

    @property
    def position_value(self) -> float:
        return self.shares * self.price

    @property
    def equity(self) -> float:
        return self.cash + self.position_value

    @property
    def covered_shares(self) -> int:
        return sum(c.contracts for c in self.calls) * 100

    @property
    def leverage(self) -> float:
        if self.equity <= 0:
            return math.inf
        return self.position_value / self.equity if self.shares > 0 else 0.0


def _stock_commission(shares: int, cfg: StrategyConfig) -> float:
    return max(shares * cfg.stock_commission, cfg.min_commission)


def _option_commission(contracts: int, cfg: StrategyConfig) -> float:
    return max(contracts * cfg.option_commission, cfg.min_commission)


def buying_power(book: _Book, cfg: StrategyConfig) -> float:
    # The backtest's call-assignment buffer is computed but never subtracted
    # (call_costs stays 0 in position.get_buying_power), so it is left out here too.
    return max(0.0, book.equity * cfg.max_margin_ratio - book.position_value)


def close_cost_per_share(call: ShortCall, price: float, day: date) -> float:
    """Cost to buy back one share's worth of a short call, as the backtest models it."""
    if price > call.strike:
        return price - call.strike
    total_days = max(1, (call.expiry - call.open_date).days)
    remaining = max(0, (call.expiry - day).days)
    return call.premium * remaining / total_days


def _effective_max_ratio(vix: float, cfg: StrategyConfig) -> float:
    if vix >= cfg.extreme_vix:
        return 1.0 + (cfg.vix_deleverage_target_ratio - 1.0) * 0.5
    if vix >= cfg.vix_deleverage_threshold:
        return cfg.vix_deleverage_target_ratio
    return cfg.max_margin_ratio


def _dip_params(vix: float, cfg: StrategyConfig):
    if vix >= cfg.vix_high_threshold:
        return cfg.high_vix_dip_trigger, cfg.high_vix_dip_buy_percent
    return cfg.dip_trigger, cfg.dip_buy_percent


class _Run:
    def __init__(self, snap: Snapshot, state: EngineState, cfg: StrategyConfig):
        self.snap = snap
        self.state = copy.deepcopy(state)
        self.cfg = cfg
        self.book = _Book(snap.price, snap.shares, snap.cash, copy.deepcopy(snap.short_calls))
        self.actions: List[Action] = []
        self.month = snap.day.strftime("%Y-%m")

    # --- primitive actions -------------------------------------------------

    def buy_stock(self, shares: int, reason: str):
        b = self.book
        b.cash -= shares * b.price + _stock_commission(shares, self.cfg)
        b.shares += shares
        self.state.highest_since_last_buy = b.price
        self.actions.append(Action("BUY_STOCK", reason, shares=shares, est_price=b.price))

    def sell_stock(self, shares: int, reason: str):
        b = self.book
        b.cash += shares * b.price - _stock_commission(shares, self.cfg)
        b.shares -= shares
        self.actions.append(Action("SELL_STOCK", reason, shares=shares, est_price=b.price))

    def buy_call(self, call: ShortCall, contracts: int, cost_per_share: float, reason: str):
        b = self.book
        b.cash -= cost_per_share * self.cfg.contract_size * contracts
        call.contracts -= contracts
        if call.contracts <= 0:
            b.calls.remove(call)
        self.actions.append(
            Action("BUY_CALL", reason, contracts=contracts, strike=call.strike,
                   expiry=call.expiry, est_price=cost_per_share)
        )

    # --- strategy steps ----------------------------------------------------

    def initial_position(self):
        if self.book.shares > 0 or self.state.highest_since_last_buy > 0:
            return
        shares = int(self.book.equity * self.cfg.initial_position_percent / self.book.price)
        if shares > 0:
            self.buy_stock(shares, "initial position")

    def write_monthly_calls(self):
        if self.state.calls_written_month == self.month:
            return
        self.state.calls_written_month = self.month
        b, cfg, snap = self.book, self.cfg, self.snap
        available = b.shares - b.covered_shares
        if available < cfg.contract_size:
            return
        contracts = max(1, round((available // cfg.contract_size) * cfg.covered_call_ratio))
        days = (snap.month_last_trading_day - snap.day).days
        strike = target_call_strike(b.price, snap.vix, cfg)
        premium = estimate_call_premium(b.price, strike, days, snap.vix, cfg)
        b.cash += premium * cfg.contract_size * contracts - _option_commission(contracts, cfg)
        b.calls.append(ShortCall(strike, snap.month_last_trading_day, contracts, premium, snap.day))
        self.actions.append(
            Action("SELL_CALL", "monthly covered calls", contracts=contracts, strike=strike,
                   expiry=snap.month_last_trading_day, est_price=premium)
        )

    def deleverage(self):
        b, cfg = self.book, self.cfg
        limit = _effective_max_ratio(self.snap.vix, cfg)
        if b.equity <= 0:
            ratio = math.inf
        else:
            ratio = b.position_value / b.equity
        if ratio <= limit:
            return
        excess = b.position_value - b.equity * limit
        to_sell = math.ceil(excess / b.price)
        keep = max(1, int(b.shares * 0.1))
        to_sell = max(0, min(to_sell, b.shares - keep)) if b.shares > keep else 0
        if to_sell <= 0:
            return

        tag = "VIX deleverage" if limit < cfg.max_margin_ratio else "margin limit"
        remaining = b.shares - to_sell
        # Close calls first so shares are never sold out from under a short call.
        if to_sell > b.shares * 0.5:
            closes = [(c, c.contracts) for c in b.calls]
        else:
            closes = []
            excess_covered = b.covered_shares - int(remaining * cfg.covered_call_ratio)
            need = math.ceil(excess_covered / cfg.contract_size) if excess_covered > 0 else 0
            for c in sorted(b.calls, key=lambda c: (-c.strike, c.expiry)):
                if need <= 0:
                    break
                n = min(c.contracts, need)
                closes.append((c, n))
                need -= n
        for c, n in closes:
            self.buy_call(c, n, close_cost_per_share(c, b.price, self.snap.day), f"{tag}: free shares")
        self.sell_stock(to_sell, f"{tag}: leverage {ratio:.2f} > {limit:.2f}")

    def dip_buy(self):
        b, cfg = self.book, self.cfg
        trigger, pct = _dip_params(self.snap.vix, cfg)
        high = self.state.highest_since_last_buy
        if high <= 0 or b.price > high * trigger:
            return
        bp = buying_power(b, cfg)
        shares = int(bp * pct / b.price)
        if shares > 0 and shares * b.price + _stock_commission(shares, cfg) <= bp:
            drop = (high - b.price) / high * 100
            self.buy_stock(shares, f"dip buy: -{drop:.1f}% from {high:.2f}")

    def month_end(self):
        if not self.snap.is_month_end or self.state.month_end_done == self.month:
            return
        self.state.month_end_done = self.month
        b, cfg, day = self.book, self.cfg, self.snap.day
        expiring = [c for c in b.calls if c.expiry <= day]
        bp = buying_power(b, cfg)
        for c in expiring:
            if b.price > c.strike:
                cost = (b.price - c.strike) * cfg.contract_size * c.contracts
                shortfall = cost - max(0.0, bp)
                if shortfall > 0:
                    net = b.price - cfg.stock_commission
                    n = min(math.ceil((shortfall + cfg.min_commission) / net), b.shares)
                    if n > 0:
                        self.sell_stock(n, "fund ITM call buyback")
                        bp = buying_power(b, cfg)
                self.buy_call(c, c.contracts, b.price - c.strike, "expiring ITM: buy back, keep shares")
                bp -= cost
            else:
                b.calls.remove(c)  # expires worthless, nothing to send
        amount = b.equity * cfg.monthly_withdrawal_rate / 100
        if amount > 0:
            b.cash -= amount
            self.actions.append(Action("WITHDRAW", f"{cfg.monthly_withdrawal_rate}% monthly", amount=amount))


def decide(snap: Snapshot, state: EngineState, cfg: StrategyConfig | None = None):
    """Return (actions, new_state) for one daily run."""
    cfg = cfg or StrategyConfig()
    run = _Run(snap, state, cfg)
    run.initial_position()
    run.write_monthly_calls()
    if run.book.price > run.state.highest_since_last_buy:
        run.state.highest_since_last_buy = run.book.price
    run.deleverage()
    run.dip_buy()
    run.month_end()
    return run.actions, run.state
