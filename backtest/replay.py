"""Replay the live engine over historical SPY/VIX closes.

A tiny simulated broker fills every action at the engine's estimated price and
charges margin interest daily, the way the original backtest does. Comparing the
result with algo_trading's TradingSimulator checks that the port is faithful.

    python -m backtest.replay --start 2006-01-01 --end 2025-03-14
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass, field
from typing import List

import pandas as pd

from autotrader.config import StrategyConfig
from autotrader.engine import Action, EngineState, ShortCall, Snapshot, decide

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


def load_history(data_dir: str = DATA_DIR) -> pd.DataFrame:
    spy = pd.read_csv(os.path.join(data_dir, "SPY-20Y.csv"), parse_dates=["DateTime"]).set_index("DateTime")
    vix = pd.read_csv(os.path.join(data_dir, "VIX-20Y.csv"), parse_dates=["DateTime"]).set_index("DateTime")
    df = spy[["Close"]].join(vix["Close"].rename("VIX"), how="inner").sort_index()
    df["VIX"] = df["VIX"].astype(float) / 100
    return df


@dataclass
class SimBroker:
    cash: float
    shares: int = 0
    calls: List[ShortCall] = field(default_factory=list)
    log: List[str] = field(default_factory=list)

    def apply(self, day, a: Action, cfg: StrategyConfig):
        if a.kind == "BUY_STOCK":
            self.cash -= a.shares * a.est_price + max(a.shares * cfg.stock_commission, cfg.min_commission)
            self.shares += a.shares
        elif a.kind == "SELL_STOCK":
            self.cash += a.shares * a.est_price - max(a.shares * cfg.stock_commission, cfg.min_commission)
            self.shares -= a.shares
        elif a.kind == "SELL_CALL":
            self.cash += a.est_price * cfg.contract_size * a.contracts - max(
                a.contracts * cfg.option_commission, cfg.min_commission
            )
            self.calls.append(ShortCall(a.strike, a.expiry, a.contracts, a.est_price, day))
        elif a.kind == "BUY_CALL":
            self.cash -= a.est_price * cfg.contract_size * a.contracts
            left = a.contracts
            for c in sorted(self.calls, key=lambda c: -c.strike):
                if left <= 0:
                    break
                if c.strike == a.strike and c.expiry == a.expiry:
                    n = min(c.contracts, left)
                    c.contracts -= n
                    left -= n
            self.calls = [c for c in self.calls if c.contracts > 0]
        elif a.kind == "WITHDRAW":
            self.cash -= a.amount
        self.log.append(f"{day} {a.describe()}")

    def expire(self, day):
        self.calls = [c for c in self.calls if c.expiry > day]


def run(start=None, end=None, initial_cash=500_000.0, cfg: StrategyConfig | None = None):
    cfg = cfg or StrategyConfig()
    df = load_history()
    if start:
        df = df[df.index >= pd.Timestamp(start)]
    if end:
        df = df[df.index <= pd.Timestamp(end)]
    month_last = df.index.to_series().groupby(df.index.to_period("M")).transform("max")

    broker = SimBroker(cash=initial_cash)
    state = EngineState()
    rows = []
    for ts, row in df.iterrows():
        day = ts.date()
        if broker.cash < 0:
            broker.cash -= abs(broker.cash) * cfg.margin_interest_rate / 365
        snap = Snapshot(
            day=day,
            price=float(row["Close"]),
            vix=float(row["VIX"]),
            shares=broker.shares,
            cash=broker.cash,
            short_calls=[ShortCall(**vars(c)) for c in broker.calls],
            month_last_trading_day=month_last[ts].date(),
        )
        actions, state = decide(snap, state, cfg)
        for a in actions:
            broker.apply(day, a, cfg)
        if snap.is_month_end:
            broker.expire(day)
        equity = broker.cash + broker.shares * snap.price
        rows.append({"date": ts, "equity": equity, "cash": broker.cash, "shares": broker.shares,
                     "leverage": broker.shares * snap.price / equity if equity > 0 else float("inf")})
    return pd.DataFrame(rows).set_index("date"), broker


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start")
    p.add_argument("--end")
    p.add_argument("--cash", type=float, default=500_000.0)
    p.add_argument("--show-trades", action="store_true")
    args = p.parse_args()
    res, broker = run(args.start, args.end, args.cash)
    if args.show_trades:
        print("\n".join(broker.log))
    print(f"Period: {res.index[0].date()} to {res.index[-1].date()}")
    print(f"Final equity: ${res['equity'].iloc[-1]:,.2f}  shares: {res['shares'].iloc[-1]}  "
          f"max leverage: {res['leverage'].max():.2f}")
    print(f"Actions: {len(broker.log)}")


if __name__ == "__main__":
    main()
