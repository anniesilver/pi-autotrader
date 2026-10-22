"""One daily run: guard rails, snapshot, decide, check, execute, record, notify."""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import List, Optional

from .broker import Broker, Fill
from .config import StrategyConfig
from .engine import Action, Snapshot, decide
from .notify import notify
from .settings import BotSettings
from .state import BotState, journal, write_status

log = logging.getLogger(__name__)


class Abort(Exception):
    pass


def check_actions(actions: List[Action], snap: Snapshot, equity: float, s: BotSettings):
    """Refuse anything outside the strategy's normal envelope before a single order goes out."""
    if len(actions) > s.max_actions_per_run:
        raise Abort(f"{len(actions)} actions in one run (limit {s.max_actions_per_run})")
    shares = snap.shares
    covered = sum(c.contracts for c in snap.short_calls) * 100
    for a in actions:
        if a.kind == "BUY_STOCK":
            if a.shares * snap.price > s.max_order_equity_fraction * equity:
                raise Abort(f"buy of {a.shares} shares exceeds {s.max_order_equity_fraction:.0%} of equity")
            shares += a.shares
        elif a.kind == "SELL_STOCK":
            if a.shares > shares:
                raise Abort(f"sell of {a.shares} shares but only {shares} held")
            shares -= a.shares
            if covered > shares:
                raise Abort("share sale would leave short calls uncovered")
        elif a.kind == "BUY_CALL":
            covered -= a.contracts * 100
        elif a.kind == "SELL_CALL":
            if covered + a.contracts * 100 > shares:
                raise Abort(f"selling {a.contracts} calls would be naked ({shares} shares, {covered} covered)")
            covered += a.contracts * 100


def execute(broker: Broker, a: Action) -> Optional[Fill]:
    if a.kind == "BUY_STOCK":
        return broker.trade_stock("BUY", a.shares, a.est_price)
    if a.kind == "SELL_STOCK":
        return broker.trade_stock("SELL", a.shares, a.est_price)
    if a.kind == "SELL_CALL":
        return broker.sell_calls(a.contracts, a.strike, a.expiry)
    if a.kind == "BUY_CALL":
        return broker.buy_calls(a.contracts, a.strike, a.expiry)
    return None  # WITHDRAW is bookkeeping only


def run_once(broker: Broker, s: BotSettings, today: date, cfg: StrategyConfig | None = None,
             force: bool = False) -> dict:
    cfg = cfg or StrategyConfig()
    state = BotState.load(s.state_dir)
    mode = "DRY RUN" if s.dry_run else "PAPER" if broker.account_id().startswith("DU") else "LIVE"
    status = {"time": datetime.now().isoformat(timespec="seconds"), "day": today, "mode": mode,
              "account": broker.account_id(), "result": "", "actions": []}

    def finish(result: str, alert: bool = False):
        status["result"] = result
        write_status(s.state_dir, status)
        journal(s.state_dir, {"type": "run", **status})
        if alert or status["actions"]:
            lines = [result] + [f"- {x['action']} -> {x.get('fill', '')}" for x in status["actions"]]
            notify(s.ntfy_topic, f"pi-autotrader [{mode}]", "\n".join(lines),
                   priority="high" if alert else "default")
        log.info(result)
        return status

    if s.kill_switch.exists():
        return finish(f"Kill switch {s.kill_switch} present; nothing done.", alert=True)
    if not broker.account_id().startswith("DU") and not s.allow_live:
        return finish(f"Account {broker.account_id()} is not a paper account and ALLOW_LIVE is off.", alert=True)
    if not broker.is_trading_day(today):
        return finish("Not a trading day.")
    if state.last_run_day == today.isoformat() and not force:
        return finish("Already ran today.")

    price, vix = broker.spy_price(), broker.vix()
    if not (0.03 < vix < 1.5) or price <= 0:
        return finish(f"Implausible market data (SPY {price}, VIX {vix}); skipped.", alert=True)

    snap = Snapshot(
        day=today, price=price, vix=vix, shares=broker.spy_shares(),
        cash=broker.cash() - state.virtual_withdrawn, short_calls=broker.short_calls(),
        month_last_trading_day=broker.month_last_trading_day(today),
    )
    equity = snap.cash + snap.shares * snap.price
    status.update({
        "spy": price, "vix": round(vix * 100, 2), "shares": snap.shares, "cash": round(snap.cash, 2),
        "equity": round(equity, 2), "leverage": round(snap.shares * price / equity, 3) if equity > 0 else None,
        "ib_net_liquidation": broker.net_liquidation(), "virtual_withdrawn": round(state.virtual_withdrawn, 2),
        "short_calls": [{"strike": c.strike, "expiry": c.expiry, "contracts": c.contracts} for c in snap.short_calls],
        "high_since_last_buy": state.engine.highest_since_last_buy,
        "month_end": snap.month_last_trading_day,
    })

    actions, new_engine = decide(snap, state.engine, cfg)
    status["actions"] = [{"action": a.describe()} for a in actions]
    status["high_since_last_buy"] = new_engine.highest_since_last_buy
    try:
        check_actions(actions, snap, equity, s)
    except Abort as e:
        return finish(f"Safety check refused the plan: {e}", alert=True)

    if s.dry_run:
        return finish(f"Dry run: {len(actions)} action(s) decided, none sent." if actions else "No action today.")

    for i, a in enumerate(actions):
        try:
            fill = execute(broker, a)
        except Exception as e:  # e.g. no quote, lost connection
            fill = Fill(False, detail=f"error: {e}")
        if a.kind == "WITHDRAW":
            state.virtual_withdrawn += a.amount
            status["actions"][i]["fill"] = "recorded (virtual)"
            continue
        status["actions"][i]["fill"] = fill.detail
        journal(s.state_dir, {"type": "order", "day": today, "action": a.describe(), "fill": vars(fill)})
        if not fill.ok:
            # Keep the old engine state; the next run re-decides from the real positions.
            state.save(s.state_dir)
            return finish(f"Order failed, stopped after {i} of {len(actions)}: {fill.detail}", alert=True)

    state.engine = new_engine
    state.last_run_day = today.isoformat()
    state.save(s.state_dir)
    return finish(f"Done: {len(actions)} action(s)." if actions else "No action today.")
