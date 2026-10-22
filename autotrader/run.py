"""Entry point for the daily run (step 3 schedules it for 15:45 New York time).

    python -m autotrader.run              # uses .env; DRY_RUN defaults to on
    python -m autotrader.run --send       # actually place orders (paper account)
    python -m autotrader.run --force      # run again even if today already ran
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
        status = run_once(broker, s, today, force=args.force)
        print(json.dumps(status, indent=2, default=str))
    finally:
        broker.close()


if __name__ == "__main__":
    main()
