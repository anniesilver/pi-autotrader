"""Persistent bot state (state/state.json) and the trade journal (state/journal.jsonl)."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from .engine import EngineState


@dataclass
class BotState:
    engine: EngineState = field(default_factory=EngineState)
    # A paper account can't withdraw, so monthly withdrawals are tracked here and
    # subtracted from cash when building snapshots (keeps leverage like the backtest).
    virtual_withdrawn: float = 0.0
    last_run_day: Optional[str] = None  # "YYYY-MM-DD" of the last completed run

    @classmethod
    def load(cls, state_dir: Path) -> "BotState":
        path = state_dir / "state.json"
        if not path.exists():
            return cls()
        raw = json.loads(path.read_text())
        return cls(
            engine=EngineState(**raw.get("engine", {})),
            virtual_withdrawn=raw.get("virtual_withdrawn", 0.0),
            last_run_day=raw.get("last_run_day"),
        )

    def save(self, state_dir: Path):
        state_dir.mkdir(parents=True, exist_ok=True)
        path = state_dir / "state.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2))
        os.replace(tmp, path)


def journal(state_dir: Path, record: dict):
    state_dir.mkdir(parents=True, exist_ok=True)
    with open(state_dir / "journal.jsonl", "a") as f:
        f.write(json.dumps(record, default=str) + "\n")


def write_status(state_dir: Path, status: dict):
    """Latest run summary; the Kindle dashboard (step 4) renders this."""
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / "status.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(status, indent=2, default=str))
    os.replace(tmp, path)
