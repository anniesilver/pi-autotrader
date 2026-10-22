"""Entry point for the daily run (step 3 schedules it for 15:45 New York time).

    python -m autotrader.run              # uses .env; DRY_RUN defaults to on
    python -m autotrader.run --send       # actually place orders (paper account)
    python -m autotrader.run --force      # run again even if today already ran
    python -m autotrader.run --check      # connection check: print what IB reports, decide nothing
"""

import argparse
import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from .bot import run_once
from .settings import BotSettings


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--send", action="store_true", help="place orders (overrides DRY_RUN)")
    p.add_argument("--force", action="store_true", help="run even if today already ran")
    p.add_argument("--check", action="store_true", help="print account and market data, then exit")
    args = p.parse_args()

    s = BotSettings.from_env()
    if args.send:
        s.dry_run = False
    s.state_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(s.state_dir / "bot.log")],
    )

    from .ib_broker import IBBroker  # imported here so tests don't need ib_async

    broker = IBBroker(s)
    try:
        today = datetime.now(ZoneInfo("America/New_York")).date()
        if args.check:
            print(json.dumps({
                "account": broker.account_id(),
                "paper": broker.account_id().startswith("DU"),
                "spy": broker.spy_price(),
                "vix": broker.vix(),
                "spy_shares": broker.spy_shares(),
                "cash": broker.cash(),
                "net_liquidation": broker.net_liquidation(),
                "short_calls": [vars(c) for c in broker.short_calls()],
                "trading_day_today": broker.is_trading_day(today),
                "month_last_trading_day": broker.month_last_trading_day(today),
            }, indent=2, default=str))
            return
        status = run_once(broker, s, today, force=args.force)
        print(json.dumps(status, indent=2, default=str))
    finally:
        broker.close()


if __name__ == "__main__":
    main()
