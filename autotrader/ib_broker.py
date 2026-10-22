"""Interactive Brokers implementation of the Broker protocol, using ib_async.

Talks to IB Gateway (or TWS) on the Pi. Orders are limit orders that start at
the mid price and step toward the far side until filled or timed out.
"""

from __future__ import annotations

import calendar
import logging
import math
from datetime import date, datetime
from typing import List

from ib_async import IB, Index, LimitOrder, Option, Stock

from .broker import Fill
from .engine import ShortCall
from .settings import BotSettings

log = logging.getLogger(__name__)

SYMBOL = "SPY"


def _ok(x) -> bool:
    return x is not None and not (isinstance(x, float) and math.isnan(x)) and x > 0


class IBBroker:
    def __init__(self, settings: BotSettings):
        self.s = settings
        self.ib = IB()
        self.ib.connect(settings.ib_host, settings.ib_port, clientId=settings.ib_client_id, timeout=30)
        accounts = self.ib.managedAccounts()
        self.account = settings.ib_account or (accounts[0] if accounts else "")
        if self.account not in accounts:
            raise RuntimeError(f"Account {self.account!r} not in managed accounts {accounts}")
        # 1 = live data; falls back to delayed (3) per request when there is no subscription
        self.ib.reqMarketDataType(1)
        self.stock = self.ib.qualifyContracts(Stock(SYMBOL, "SMART", "USD"))[0]
        self.vix_index = self.ib.qualifyContracts(Index("VIX", "CBOE", "USD"))[0]
        self._chain = None

    def close(self):
        self.ib.disconnect()

    # --- market data -------------------------------------------------------

    def _price(self, contract) -> float:
        [t] = self.ib.reqTickers(contract)
        p = t.marketPrice()
        if not _ok(p):
            p = t.close
        if not _ok(p):
            self.ib.reqMarketDataType(3)
            [t] = self.ib.reqTickers(contract)
            self.ib.reqMarketDataType(1)
            p = t.marketPrice() if _ok(t.marketPrice()) else t.close
        if not _ok(p):
            raise RuntimeError(f"No price for {contract.symbol}")
        return float(p)

    def spy_price(self) -> float:
        return self._price(self.stock)

    def vix(self) -> float:
        return self._price(self.vix_index) / 100.0

    def chain(self):
        if self._chain is None:
            chains = self.ib.reqSecDefOptParams(SYMBOL, "", "STK", self.stock.conId)
            self._chain = next(c for c in chains if c.exchange == "SMART")
        return self._chain

    def _expiries(self) -> List[date]:
        return sorted(datetime.strptime(e, "%Y%m%d").date() for e in self.chain().expirations)

    def is_trading_day(self, day: date) -> bool:
        # SPY lists an expiry for every trading day, so today's expiry exists only on trading days.
        if day.weekday() >= 5:
            return False
        return day in self._expiries()

    def month_last_trading_day(self, day: date) -> date:
        in_month = [e for e in self._expiries() if e.year == day.year and e.month == day.month and e >= day]
        if in_month:
            return in_month[-1]
        last = date(day.year, day.month, calendar.monthrange(day.year, day.month)[1])
        while last.weekday() >= 5:
            last = last.replace(day=last.day - 1)
        return last

    # --- account -----------------------------------------------------------

    def account_id(self) -> str:
        return self.account

    def _account_value(self, tag: str) -> float:
        for v in self.ib.accountValues(self.account):
            if v.tag == tag and v.currency in ("USD", "BASE"):
                return float(v.value)
        raise RuntimeError(f"Account value {tag} not available")

    def cash(self) -> float:
        return self._account_value("TotalCashValue")

    def net_liquidation(self) -> float:
        return self._account_value("NetLiquidation")

    def _positions(self):
        return [p for p in self.ib.positions(self.account) if p.contract.symbol == SYMBOL]

    def spy_shares(self) -> int:
        return int(sum(p.position for p in self._positions() if p.contract.secType == "STK"))

    def short_calls(self) -> List[ShortCall]:
        calls = []
        for p in self._positions():
            c = p.contract
            if c.secType == "OPT" and c.right == "C" and p.position < 0:
                expiry = datetime.strptime(c.lastTradeDateOrContractMonth[:8], "%Y%m%d").date()
                premium = p.avgCost / float(c.multiplier or 100)
                # open_date isn't tracked by IB; assume the start of the expiry month (as the backtest does)
                calls.append(ShortCall(float(c.strike), expiry, int(-p.position), premium,
                                       expiry.replace(day=1)))
        return calls

    # --- orders ------------------------------------------------------------

    def _work_order(self, contract, action: str, qty: int, start: float, far: float, tick: float) -> Fill:
        """Limit order from `start` stepping toward `far` until filled or out of time."""
        steps = 5
        wait = max(5, self.s.order_timeout_s // (steps + 1))
        order = LimitOrder(action, qty, round(start, 2), account=self.account, tif="DAY")
        trade = self.ib.placeOrder(contract, order)
        for i in range(1, steps + 2):
            self.ib.sleep(wait)
            if trade.isDone():
                break
            if i <= steps:
                px = start + (far - start) * i / steps
                order.lmtPrice = round(round(px / tick) * tick, 2)
                self.ib.placeOrder(contract, order)
        if not trade.isDone():
            self.ib.cancelOrder(order)
            self.ib.sleep(2)
        filled = int(trade.orderStatus.filled)
        avg = float(trade.orderStatus.avgFillPrice or 0)
        status = trade.orderStatus.status
        return Fill(ok=filled == qty, filled=filled, avg_price=avg, detail=f"{status} {filled}/{qty} @ {avg:.2f}")

    def _quote(self, contract):
        [t] = self.ib.reqTickers(contract)
        bid, ask = t.bid, t.ask
        if not (_ok(bid) and _ok(ask)):
            raise RuntimeError(f"No bid/ask for {contract.localSymbol or contract.symbol}")
        return float(bid), float(ask)

    def trade_stock(self, side: str, shares: int, ref_price: float) -> Fill:
        action = "BUY" if side == "BUY" else "SELL"
        bid, ask = self._quote(self.stock)
        mid = (bid + ask) / 2
        far = ask + 0.05 if action == "BUY" else bid - 0.05
        return self._work_order(self.stock, action, shares, mid, far, 0.01)

    def _option(self, strike: float, expiry: date):
        opt = Option(SYMBOL, expiry.strftime("%Y%m%d"), strike, "C", "SMART", tradingClass=SYMBOL)
        q = self.ib.qualifyContracts(opt)
        return q[0] if q else None

    def sell_calls(self, contracts: int, target_strike: float, expiry: date) -> Fill:
        # Nearest listed strike at or above the target, so we never sell closer to the money.
        strikes = sorted(s for s in self.chain().strikes if s >= target_strike)
        for strike in strikes[:5]:
            opt = self._option(strike, expiry)
            if opt:
                break
        else:
            return Fill(False, detail=f"no listed call >= {target_strike} for {expiry}")
        bid, ask = self._quote(opt)
        if bid < 0.05:
            return Fill(False, detail=f"bid {bid:.2f} too low for {opt.localSymbol}", strike=strike)
        fill = self._work_order(opt, "SELL", contracts, (bid + ask) / 2, bid, 0.01)
        fill.strike = strike
        return fill

    def buy_calls(self, contracts: int, strike: float, expiry: date) -> Fill:
        opt = self._option(strike, expiry)
        if not opt:
            return Fill(False, detail=f"call {strike} {expiry} not found")
        bid, ask = self._quote(opt)
        return self._work_order(opt, "BUY", contracts, (bid + ask) / 2, ask + 0.05, 0.01)
