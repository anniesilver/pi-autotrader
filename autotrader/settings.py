"""Bot settings, read from environment variables (or a .env file next to the repo).

Safe defaults: dry run on, paper account only, IB Gateway paper port.
"""

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path):
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class BotSettings:
    ib_host: str = "127.0.0.1"
    ib_port: int = 4002  # IB Gateway paper; live Gateway is 4001
    ib_client_id: int = 17
    ib_account: str = ""  # empty = the only managed account

    dry_run: bool = True  # log decisions but send no orders
    allow_live: bool = False  # refuse non-paper (non "DU") accounts unless true

    state_dir: Path = REPO_ROOT / "state"
    kill_switch: Path = REPO_ROOT / "state" / "STOP"

    ntfy_topic: str = ""  # https://ntfy.sh/<topic> push notifications; empty = off

    # Safety limits, checked before any order is sent
    max_order_equity_fraction: float = 0.7  # single stock order notional vs equity
    max_actions_per_run: int = 12
    order_timeout_s: int = 90

    @classmethod
    def from_env(cls) -> "BotSettings":
        _load_dotenv(REPO_ROOT / ".env")
        s = cls()
        s.ib_host = os.environ.get("IB_HOST", s.ib_host)
        s.ib_port = int(os.environ.get("IB_PORT", s.ib_port))
        s.ib_client_id = int(os.environ.get("IB_CLIENT_ID", s.ib_client_id))
        s.ib_account = os.environ.get("IB_ACCOUNT", s.ib_account)
        s.dry_run = _bool("DRY_RUN", s.dry_run)
        s.allow_live = _bool("ALLOW_LIVE", s.allow_live)
        if os.environ.get("STATE_DIR"):
            s.state_dir = Path(os.environ["STATE_DIR"])
            s.kill_switch = s.state_dir / "STOP"
        s.ntfy_topic = os.environ.get("NTFY_TOPIC", s.ntfy_topic)
        return s
