"""Render the Kindle dashboard: state/status.json + journal -> state/dash/dashboard.png.

Kindle Voyage screen: 1072 x 1448, 16-level grayscale. The Kindle pulls the PNG
over WiFi (deploy/kindle) and shows it full screen.

    python -m autotrader.dashboard            # render once
    python -m autotrader.dashboard --demo     # render sample data (for layout checks)
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from PIL import Image, ImageDraw, ImageFont

from .config import StrategyConfig
from .settings import BotSettings

W, H = 1072, 1448
M = 56  # margin
FONT_DIRS = ["/usr/share/fonts/truetype/dejavu"]


def _font(size: int, bold: bool = False):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    for d in FONT_DIRS:
        p = Path(d) / name
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default(size=size)


def _money(x: Optional[float]) -> str:
    if x is None:
        return "—"
    return f"-${-x:,.0f}" if x < 0 else f"${x:,.0f}"


def load_equity_history(state_dir: Path, limit: int = 120) -> List[float]:
    path = state_dir / "journal.jsonl"
    if not path.exists():
        return []
    values = []
    for line in path.read_text().splitlines()[-2000:]:
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("type") == "run" and rec.get("equity"):
            values.append(float(rec["equity"]))
    return values[-limit:]


def render(status: dict, history: List[float], now: datetime, cfg: StrategyConfig | None = None) -> Image.Image:
    cfg = cfg or StrategyConfig()
    img = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(img)
    f_small, f_body, f_bold = _font(30), _font(36), _font(36, True)
    f_big, f_mid, f_title = _font(84, True), _font(64, True), _font(44, True)

    # Header bar
    d.rectangle([0, 0, W, 120], fill=0)
    d.text((M, 32), "SPY POWER CASHFLOW", font=f_title, fill=255)
    mode = status.get("mode", "?")
    tw = d.textlength(mode, font=f_title)
    d.text((W - M - tw, 32), mode, font=f_title, fill=255)

    y = 150
    run_time = status.get("time")
    stale = True
    if run_time:
        last = datetime.fromisoformat(run_time)
        stale = now - last > timedelta(days=4)
        d.text((M, y), f"Last run {last:%a %b %d %H:%M}", font=f_body, fill=0)
    else:
        d.text((M, y), "No run yet", font=f_body, fill=0)
    d.text((M, y + 46), f"Updated {now:%a %b %d %H:%M}", font=f_small, fill=90)
    y += 110

    # Result banner (inverted when something needs attention)
    result = status.get("result", "")
    alert = stale or any(k in result for k in ("failed", "refused", "Kill switch", "Implausible", "not a paper"))
    if stale:
        result = "STALE: no bot run in 4+ days. " + result
    d.rectangle([M, y, W - M, y + 100], fill=0 if alert else 230, outline=0, width=3)
    _wrap(d, result or "—", (M + 24, y + 8), W - 2 * M - 48, f_bold, 255 if alert else 0, max_lines=2)
    y += 125

    # Big numbers
    def stat(x, label, value, font=f_big):
        d.text((x, y), label, font=f_small, fill=90)
        d.text((x, y + 38), value, font=font, fill=0)

    stat(M, "EQUITY", _money(status.get("equity")))
    y += 145
    col = (W - 2 * M) // 3
    stat(M, "SPY", f"{status['spy']:.2f}" if status.get("spy") else "—", f_mid)
    stat(M + col + 20, "VIX", f"{status['vix']:.1f}" if status.get("vix") else "—", f_mid)
    lev = status.get("leverage")
    stat(M + 2 * col, "LEVERAGE", f"{lev:.2f}x" if lev is not None else "—", f_mid)
    y += 125

    # Leverage gauge: 0 .. max_margin_ratio, with the VIX deleverage target marked
    gx0, gx1, gy = M, W - M, y
    d.rectangle([gx0, gy, gx1, gy + 34], outline=0, width=3)
    if lev:
        fill_to = gx0 + (gx1 - gx0) * min(lev / cfg.max_margin_ratio, 1.0)
        d.rectangle([gx0, gy, fill_to, gy + 34], fill=60)
    tx = gx0 + (gx1 - gx0) * cfg.vix_deleverage_target_ratio / cfg.max_margin_ratio
    d.line([tx, gy - 10, tx, gy + 44], fill=0, width=4)
    d.text((gx0, gy + 44), "0x", font=f_small, fill=90)
    d.text((tx - 30, gy + 44), f"{cfg.vix_deleverage_target_ratio}x", font=f_small, fill=90)
    d.text((gx1 - 50, gy + 44), f"{cfg.max_margin_ratio:.0f}x", font=f_small, fill=90)
    y += 95

    # Position
    _section(d, y, "POSITION", f_small)
    y += 50
    d.text((M, y), f"{status.get('shares', 0):,} SPY shares", font=f_body, fill=0)
    d.text((W // 2, y), f"Cash {_money(status.get('cash'))}", font=f_body, fill=0)
    y += 56
    spy = status.get("spy")
    calls = status.get("short_calls") or []
    if calls:
        for c in calls[:3]:
            otm = f"  {(c['strike'] / spy - 1) * 100:+.1f}% vs SPY" if spy else ""
            d.text((M, y), f"Short {c['contracts']}x {c['strike']:.0f}C  exp {str(c['expiry'])[5:]}{otm}",
                   font=f_body, fill=0)
            y += 50
    else:
        d.text((M, y), "No open calls", font=f_body, fill=90)
        y += 50

    # Dip trigger
    high = status.get("high_since_last_buy")
    if high and spy:
        vix = (status.get("vix") or 0) / 100
        trig = cfg.high_vix_dip_trigger if vix >= cfg.vix_high_threshold else cfg.dip_trigger
        target = high * trig
        d.text((M, y), f"Next dip buy at {target:.2f}  ({(target / spy - 1) * 100:+.1f}%)  high {high:.2f}",
               font=f_body, fill=0)
    y += 65

    # Equity history sparkline
    _section(d, y, "EQUITY, LAST RUNS", f_small)
    y += 50
    _sparkline(d, history, (M, y, W - M, y + 160))
    y += 185

    # Today's actions
    _section(d, y, "LAST RUN ACTIONS", f_small)
    y += 50
    actions = status.get("actions") or []
    if not actions:
        d.text((M, y), "None", font=f_body, fill=90)
    for a in actions[:4]:
        text = a["action"] + (f"  → {a['fill']}" if a.get("fill") else "")
        y = _wrap(d, text, (M, y), W - 2 * M, f_small, 0, max_lines=2) + 8
        if y > H - 150:
            break

    # Footer
    month_end = status.get("month_end")
    footer = f"Month end {str(month_end)[5:]}" if month_end else ""
    footer += f"   ·   account {status.get('account', '?')}"
    d.line([M, H - 90, W - M, H - 90], fill=150, width=2)
    d.text((M, H - 70), footer.strip(" ·"), font=f_small, fill=90)
    return img


def _section(d, y, title, font):
    d.text((M, y), title, font=font, fill=90)
    d.line([M, y + 40, W - M, y + 40], fill=150, width=2)


def _wrap(d, text, xy, width, font, fill, max_lines=3) -> int:
    x, y = xy
    words, line, lines = text.split(), "", []
    for w in words:
        trial = f"{line} {w}".strip()
        if d.textlength(trial, font=font) <= width:
            line = trial
        else:
            lines.append(line)
            line = w
    lines.append(line)
    lines = lines[:max_lines]
    h = font.size + 8
    for i, ln in enumerate(lines):
        d.text((x, y + i * h), ln, font=font, fill=fill)
    return y + len(lines) * h


def _sparkline(d, values, box):
    x0, y0, x1, y1 = box
    d.rectangle(box, outline=200, width=2)
    if len(values) < 2:
        d.text((x0 + 20, y0 + 20), "Not enough history yet", font=_font(30), fill=120)
        return
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    pts = [(x0 + 10 + (x1 - x0 - 20) * i / (len(values) - 1),
            y1 - 10 - (y1 - y0 - 20) * (v - lo) / span) for i, v in enumerate(values)]
    d.line(pts, fill=0, width=5)
    f = _font(26)
    d.text((x0 + 14, y0 + 8), f"${hi:,.0f}", font=f, fill=90)
    d.text((x0 + 14, y1 - 40), f"${lo:,.0f}", font=f, fill=90)


DEMO = {
    "time": "2026-11-16T15:46:02", "day": "2026-11-16", "mode": "PAPER", "account": "DU1234567",
    "result": "Done: 1 action(s).", "spy": 668.42, "vix": 17.8, "shares": 905, "cash": -21350.0,
    "equity": 583580.0, "leverage": 1.037, "high_since_last_buy": 702.15, "month_end": "2026-11-30",
    "short_calls": [{"strike": 685.0, "expiry": "2026-11-30", "contracts": 9}],
    "actions": [{"action": "BUY_STOCK 305 @ ~645.10 (dip buy: -8.1% from 702.15)",
                 "fill": "Filled 305/305 @ 645.08"}],
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--demo", action="store_true")
    p.add_argument("--out")
    args = p.parse_args()
    s = BotSettings.from_env()
    out = Path(args.out) if args.out else s.state_dir / "dash" / "dashboard.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    if args.demo:
        status = DEMO
        history = [560_000 + 9000 * __import__("math").sin(i / 6) + 300 * i for i in range(80)]
        now = datetime(2026, 11, 16, 16, 0)
    else:
        path = s.state_dir / "status.json"
        status = json.loads(path.read_text()) if path.exists() else {"result": "No run yet", "mode": "—"}
        history = load_equity_history(s.state_dir)
        now = datetime.now()
    tmp = out.with_suffix(".tmp.png")
    render(status, history, now).save(tmp)
    tmp.replace(out)
    print(out)


if __name__ == "__main__":
    main()
