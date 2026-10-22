# pi-autotrader

A low-frequency auto-trader that runs on a Raspberry Pi, trades through Interactive Brokers, and shows its status on a jailbroken Kindle Voyage.

The first strategy is **SPY_POWER_CASHFLOW**, ported from `algo_trading/SPY_POWER_CASHFLOW` (backtested in TradingHub): hold SPY on modest margin, sell monthly covered calls, buy dips, deleverage when VIX is high.

> Paper trading only until the owners decide otherwise. Nothing here is financial advice.

## Plan

1. **Live decision engine** from the backtest code (this PR): `autotrader/engine.py`
2. **Python bot** on the IB paper account (`ib_async`, IB Gateway): order execution, state, safety limits, notifications
3. **Pi setup**: Raspberry Pi OS 64-bit, IB Gateway + IBC, systemd service and schedule
4. **Kindle display**: the Pi renders a 1072×1448 grayscale status image; the Kindle pulls and shows it
5. **Paper trade** for at least three monthly cycles, compare with the backtest, then decide on live

## Layout

```
autotrader/config.py    strategy settings (defaults match the backtest)
autotrader/engine.py    decide(snapshot, state) -> actions; pure logic, no broker calls
autotrader/pricing.py   strike targeting and Black-Scholes estimates
backtest/replay.py      replays the engine over 20 years of SPY/VIX closes
data/                   SPY and VIX daily closes, 2005-2025
docs/STRATEGY_LIVE.md   the rules, and how live trading differs from the backtest
tests/                  unit tests plus a parity check against the original backtest
```

## Run

```bash
pip install -r requirements.txt
python -m pytest
python -m backtest.replay --start 2006-01-01 --show-trades
```
