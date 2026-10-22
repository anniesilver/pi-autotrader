import json
from datetime import date

import pytest

from autotrader.bot import run_once
from autotrader.broker import Fill
from autotrader.engine import ShortCall
from autotrader.settings import BotSettings
from autotrader.state import BotState


class FakeBroker:
    def __init__(self, account="DU123", price=500.0, vix=0.15, shares=0, cash=500_000.0, calls=None,
                 fail_on=None):
        self.account, self.price, self._vix = account, price, vix
        self.shares, self._cash, self.calls = shares, cash, calls or []
        self.fail_on = fail_on
        self.orders = []

    def account_id(self): return self.account
    def is_trading_day(self, day): return day.weekday() < 5
    def month_last_trading_day(self, day): return date(2026, 11, 30)
    def spy_price(self): return self.price
    def vix(self): return self._vix
    def cash(self): return self._cash
    def spy_shares(self): return self.shares
    def short_calls(self): return list(self.calls)
    def net_liquidation(self): return self._cash + self.shares * self.price

    def _fill(self, kind, qty):
        self.orders.append((kind, qty))
        if self.fail_on == kind:
            return Fill(False, 0, 0.0, "Cancelled 0/%d" % qty)
        return Fill(True, qty, 1.0, "Filled")

    def trade_stock(self, side, shares, ref):
        fill = self._fill(side, shares)
        if fill.ok:
            self.shares += shares if side == "BUY" else -shares
        return fill

    def sell_calls(self, contracts, strike, expiry): return self._fill("SELL_CALL", contracts)
    def buy_calls(self, contracts, strike, expiry): return self._fill("BUY_CALL", contracts)


@pytest.fixture
def settings(tmp_path):
    s = BotSettings()
    s.state_dir = tmp_path
    s.kill_switch = tmp_path / "STOP"
    s.dry_run = False
    return s


MON = date(2026, 11, 2)


def test_first_run_buys_and_writes_calls(settings):
    b = FakeBroker()
    status = run_once(b, settings, MON)
    assert b.orders == [("BUY", 600), ("SELL_CALL", 6)]
    assert status["result"] == "Done: 2 action(s)."
    st = BotState.load(settings.state_dir)
    assert st.last_run_day == "2026-11-02"
    assert st.engine.calls_written_month == "2026-11"
    assert json.loads((settings.state_dir / "status.json").read_text())["mode"] == "PAPER"


def test_dry_run_sends_nothing_and_keeps_state(settings):
    settings.dry_run = True
    b = FakeBroker()
    status = run_once(b, settings, MON)
    assert b.orders == []
    assert len(status["actions"]) == 2
    assert BotState.load(settings.state_dir).last_run_day is None


def test_refuses_live_account(settings):
    b = FakeBroker(account="U999")
    status = run_once(b, settings, MON)
    assert b.orders == []
    assert "not a paper account" in status["result"]


def test_kill_switch(settings):
    settings.kill_switch.write_text("")
    b = FakeBroker()
    assert "Kill switch" in run_once(b, settings, MON)["result"]
    assert b.orders == []


def test_runs_once_per_day(settings):
    b = FakeBroker()
    run_once(b, settings, MON)
    b.orders.clear()
    assert run_once(b, settings, MON)["result"] == "Already ran today."
    assert b.orders == []


def test_weekend_skipped(settings):
    b = FakeBroker()
    assert run_once(b, settings, date(2026, 11, 7))["result"] == "Not a trading day."


def test_failed_order_stops_and_keeps_old_state(settings):
    b = FakeBroker(fail_on="SELL_CALL")
    status = run_once(b, settings, MON)
    assert "Order failed, stopped after 1 of 2" in status["result"]
    st = BotState.load(settings.state_dir)
    assert st.last_run_day is None and st.engine.calls_written_month is None
    # Next run re-decides from real positions: shares exist now, so only the calls are retried.
    b.fail_on = None
    b.orders.clear()
    run_once(b, settings, MON)
    assert b.orders == [("SELL_CALL", 6)]


def test_bad_market_data_skips(settings):
    b = FakeBroker(vix=0.0)
    assert "Implausible" in run_once(b, settings, MON)["result"]
    assert b.orders == []


def test_month_end_withdrawal_is_virtual(settings):
    st = BotState()
    st.engine.highest_since_last_buy = 500
    st.engine.calls_written_month = "2026-11"
    st.save(settings.state_dir)
    b = FakeBroker(shares=600, cash=200_000, calls=[ShortCall(530, date(2026, 11, 30), 6, 4.0, MON)])
    run_once(b, settings, date(2026, 11, 30))
    assert b.orders == []  # OTM call just expires
    st = BotState.load(settings.state_dir)
    assert st.virtual_withdrawn == pytest.approx(5_000.0)  # 1% of 500k equity


def test_existing_calls_are_not_written_twice(settings):
    # IB already shows calls covering all shares while the engine state thinks this month isn't done.
    b = FakeBroker(shares=600, cash=200_000, calls=[ShortCall(530, date(2026, 11, 30), 6, 4.0, MON)])
    st = BotState()
    st.engine.highest_since_last_buy = 500
    st.save(settings.state_dir)
    status = run_once(b, settings, MON)
    assert b.orders == [] and status["actions"] == []


def test_safety_check_blocks_naked_calls():
    from autotrader.bot import Abort, check_actions
    from autotrader.engine import Action, Snapshot

    snap = Snapshot(MON, 500.0, 0.15, 600, 200_000, [], date(2026, 11, 30))
    with pytest.raises(Abort, match="naked"):
        check_actions([Action("SELL_CALL", "x", contracts=7, strike=510, expiry=date(2026, 11, 30))],
                      snap, 500_000, BotSettings())
    with pytest.raises(Abort, match="exceeds"):
        check_actions([Action("BUY_STOCK", "x", shares=800, est_price=500)], snap, 500_000, BotSettings())
