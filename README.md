# pi-autotrader

A low-frequency auto-trader that runs on a Raspberry Pi, trades through Interactive Brokers, and shows its status on a jailbroken Kindle Voyage.

The first strategy is **SPY_POWER_CASHFLOW**, ported from `algo_trading/SPY_POWER_CASHFLOW` (backtested in TradingHub): hold SPY on modest margin, sell monthly covered calls, buy dips, deleverage when VIX is high.

> Paper trading only until the owners decide otherwise. Nothing here is financial advice.

## Plan

1. **Live decision engine** from the backtest code: `autotrader/engine.py`
2. **Python bot** on the IB paper account (`ib_async`, IB Gateway): order execution, state, safety limits, notifications (`autotrader/bot.py`)
3. **Pi setup**: Raspberry Pi OS 64-bit, IB Gateway + IBC in Docker, systemd timer (`docs/PI_SETUP.md`)
4. **Kindle display**: the Pi renders a 1072×1448 grayscale status image; the Kindle pulls and shows it
5. **Paper trade** for at least three monthly cycles, compare with the backtest, then decide on live

## Layout

```
autotrader/config.py    strategy settings (defaults match the backtest)
autotrader/engine.py    decide(snapshot, state) -> actions; pure logic, no broker calls
autotrader/pricing.py   strike targeting and Black-Scholes estimates
autotrader/bot.py       one daily run: guards, snapshot, decide, safety check, execute, record
autotrader/ib_broker.py Interactive Brokers via ib_async (IB Gateway)
autotrader/run.py       command-line entry point
autotrader/state.py     state/state.json, journal.jsonl, status.json (for the Kindle)
backtest/replay.py      replays the engine over 20 years of SPY/VIX closes
data/                   SPY and VIX daily closes, 2005-2025
docs/STRATEGY_LIVE.md   the rules, and how live trading differs from the backtest
docs/PI_SETUP.md        Raspberry Pi setup, step by step
deploy/                 setup script, IB Gateway docker-compose, systemd timer
tests/                  unit tests plus a parity check against the original backtest
```

## Run

```bash
pip install -r requirements.txt
python -m pytest
python -m backtest.replay --start 2006-01-01 --show-trades
```

## Daily bot

Needs IB Gateway logged in to the **paper** account, with the API enabled on port 4002.

```bash
cp .env.example .env
python -m autotrader.run          # dry run: prints what it would do
python -m autotrader.run --send   # places the orders on the paper account
```

Safety rails, all in `autotrader/bot.py`:

- Refuses any account not starting with `DU` (paper) unless `ALLOW_LIVE=1`.
- `DRY_RUN=1` by default.
- Kill switch: `touch state/STOP` and the bot does nothing until the file is removed.
- Runs once per trading day. Skips weekends and holidays, using SPY's daily option expiries as the calendar.
- Rejects implausible prices or VIX values, more than 12 actions, a single stock order above 70% of equity, and any plan that would leave calls naked or shares uncovered.
- Stops at the first order that doesn't fully fill and keeps the old state. The next run re-decides from the real positions.
- Orders are limit orders that start at the mid and step toward the far side over about 90 seconds, then cancel.

Everything is recorded in `state/`: `state.json` (engine state and virtual withdrawals), `journal.jsonl` (every run and order), `status.json` (latest summary, which feeds the Kindle), and `bot.log`.
