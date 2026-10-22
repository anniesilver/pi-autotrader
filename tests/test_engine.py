from datetime import date

import pytest

from autotrader.config import StrategyConfig
from autotrader.engine import EngineState, ShortCall, Snapshot, decide
from backtest.replay import run

CFG = StrategyConfig()


def snap(day=date(2026, 11, 2), price=500.0, vix=0.15, shares=0, cash=500_000.0, calls=None,
         month_last=date(2026, 11, 30)):
    return Snapshot(day, price, vix, shares, cash, calls or [], month_last)


def kinds(actions):
    return [a.kind for a in actions]


def test_first_run_buys_initial_position_then_writes_calls():
    actions, state = decide(snap(), EngineState())
    assert kinds(actions) == ["BUY_STOCK", "SELL_CALL"]
    assert actions[0].shares == 600  # 60% of 500k / 500
    assert actions[1].contracts == 6
    assert actions[1].strike == 510  # 500 * 1.02 (max(1.5%, 15% * 0.15)), rounded to $5
    assert actions[1].expiry == date(2026, 11, 30)
    assert state.highest_since_last_buy == 500
    assert state.calls_written_month == "2026-11"


def test_calls_written_once_per_month():
    state = EngineState(highest_since_last_buy=500, calls_written_month="2026-11")
    actions, _ = decide(snap(day=date(2026, 11, 3), shares=600, cash=200_000), state)
    assert actions == []


def test_dip_buy_normal_vix():
    state = EngineState(highest_since_last_buy=500, calls_written_month="2026-11")
    actions, new = decide(snap(day=date(2026, 11, 10), price=459.0, shares=600, cash=200_000), state)
    assert kinds(actions) == ["BUY_STOCK"]
    # equity 475,400; buying power = 2x equity - position = 675,400; 40% of it
    assert actions[0].shares == int(675_400 * 0.4 / 459.0)
    assert new.highest_since_last_buy == 459.0


def test_no_dip_buy_in_high_vix_until_minus_20():
    state = EngineState(highest_since_last_buy=500, calls_written_month="2026-11")
    actions, _ = decide(snap(day=date(2026, 11, 10), price=450.0, vix=0.30, shares=600, cash=200_000), state)
    assert actions == []
    actions, _ = decide(snap(day=date(2026, 11, 10), price=400.0, vix=0.30, shares=600, cash=200_000), state)
    assert kinds(actions) == ["BUY_STOCK"]


def test_vix_deleverage_closes_calls_before_selling_shares():
    calls = [ShortCall(420, date(2026, 11, 30), 10, 3.0, date(2026, 11, 2))]
    state = EngineState(highest_since_last_buy=450, calls_written_month="2026-11")
    # equity 200k, position 400k -> leverage 2.0, above the 1.5 high-VIX target
    actions, _ = decide(snap(day=date(2026, 11, 10), price=400.0, vix=0.30, shares=1000, cash=-200_000,
                             calls=calls), state)
    assert kinds(actions) == ["BUY_CALL", "SELL_STOCK"]
    assert actions[1].shares == 250  # (400k - 1.5 * 200k) / 400
    assert actions[0].contracts == 3  # 750 shares left can cover only 7 contracts


def test_month_end_buys_back_itm_and_withdraws():
    calls = [ShortCall(510, date(2026, 11, 30), 6, 4.0, date(2026, 11, 2))]
    state = EngineState(highest_since_last_buy=520, calls_written_month="2026-11")
    actions, new = decide(snap(day=date(2026, 11, 30), price=520.0, shares=600, cash=200_000, calls=calls), state)
    assert kinds(actions) == ["BUY_CALL", "WITHDRAW"]
    assert actions[0].est_price == pytest.approx(10.0)
    equity_after = 200_000 - 6_000 + 600 * 520
    assert actions[1].amount == pytest.approx(equity_after * 0.01)
    assert new.month_end_done == "2026-11"
    # Running again the same day does not repeat month-end work.
    again, _ = decide(snap(day=date(2026, 11, 30), price=520.0, shares=600, cash=150_000), new)
    assert again == []


def test_month_end_lets_otm_calls_expire():
    calls = [ShortCall(530, date(2026, 11, 30), 6, 4.0, date(2026, 11, 2))]
    state = EngineState(highest_since_last_buy=520, calls_written_month="2026-11")
    actions, _ = decide(snap(day=date(2026, 11, 30), price=520.0, shares=600, cash=200_000, calls=calls), state)
    assert kinds(actions) == ["WITHDRAW"]


def test_replay_matches_original_backtest():
    # Reference: algo_trading/SPY_POWER_CASHFLOW TradingSimulator, default config,
    # start 2006-01-01, 20Y data -> final Portfolio_Value 1,345,316.52.
    # The tiny gap comes from the backtest charging day-one interest after the
    # monthly premium lands, while the replay charges it before the engine runs.
    res, _ = run("2006-01-01")
    assert res["equity"].iloc[-1] == pytest.approx(1_345_316.52, rel=0.001)
