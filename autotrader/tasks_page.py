"""Render a task list as a Kindle page: state/tasks.json (or .txt) -> state/dash/tasks.png.

A second "app" for the Kindle next to the trading dashboard. Only needs Pillow and
a CJK font, so the same file also runs on a PC for testing:

    python -m autotrader.tasks_page                    # on the Pi
    python tasks_page.py tasks.json tasks.png          # anywhere

tasks.json: the 下周任务清单 artifact's tasks, a list of
{"title", "due": "YYYY-MM-DD", "progress": 0-100, "order"}, or
{"title": "page title", "tasks": [...]}. Each task gets a progress bar and due date.

tasks.txt format (UTF-8), for a plain list:

    # 下周任务清单          title
    ## 周一                 section heading
    [ ] 买菜                open task  ("- [ ]" also works)
    [x] 交房租              done task, drawn struck through
    - 备注                  bullet
    anything else           plain text
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional, Tuple, Union

from PIL import Image, ImageDraw, ImageFont

W, H = 1072, 1448
M = 64  # margin
FOOTER_H = 70

# Regular / bold candidates. Debian/Pi: `sudo apt install fonts-noto-cjk`.
FONTS = [
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
    ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyhbd.ttc"),
    ("C:/Windows/Fonts/simhei.ttf", "C:/Windows/Fonts/simhei.ttf"),
    ("/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/PingFang.ttc"),
    ("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
    ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
]


def _font(size: int, bold: bool = False):
    for regular, heavy in FONTS:
        p = Path(heavy if bold else regular)
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default(size=size)


def parse(text: str) -> Tuple[str, List[tuple]]:
    """Return (title, [(kind, text, extra)]) with kind in section/todo/done/bullet/text/blank."""
    title, items = "", []
    for raw in text.splitlines():
        line = raw.strip().lstrip("\ufeff")
        if line.startswith("- [") or line.startswith("* ["):
            line = line[2:]
        if not line:
            items.append(("blank", ""))
        elif line.startswith("## "):
            items.append(("section", line[3:].strip()))
        elif line.startswith("# "):
            if title:
                items.append(("section", line[2:].strip()))
            else:
                title = line[2:].strip()
        elif line[:3] in ("[ ]", "[]"):
            items.append(("todo", line[3:].strip() if line[:3] == "[ ]" else line[2:].strip()))
        elif line[:3].lower() == "[x]":
            items.append(("done", line[3:].strip()))
        elif line[:2] in ("- ", "* "):
            items.append(("bullet", line[2:].strip()))
        else:
            items.append(("text", line))
    while items and items[0][0] == "blank":
        items.pop(0)
    return title, [(k, t, None) for k, t in items]


WEEKDAYS = "一二三四五六日"


def parse_json(data: Union[list, dict], today: date) -> Tuple[str, List[tuple]]:
    """Artifact tasks -> (title, [(kind, text, extra)]); extra has progress and a due label."""
    title = ""
    if isinstance(data, dict):
        title, data = data.get("title", ""), data.get("tasks", [])
    items = []
    for t in sorted(data, key=lambda t: (t.get("order", 0), t.get("due") or "")):
        progress = max(0, min(100, int(t.get("progress") or 0)))
        due, note = t.get("due") or "", ""
        if due:
            d = date.fromisoformat(due)
            note = f"周{WEEKDAYS[d.weekday()]} {d.month}月{d.day}日"
            left = (d - today).days
            if progress < 100:
                note += f" · 还剩 {left} 天" if left > 0 else " · 今天截止" if left == 0 else f" · 逾期 {-left} 天"
        items.append(("done" if progress >= 100 else "todo", (t.get("title") or "").strip(),
                      {"progress": progress, "note": note}))
    return title, items


def _wrap(d: ImageDraw.ImageDraw, text: str, font, width: int) -> List[str]:
    """Break text to fit width, per character, so it works for Chinese with no spaces."""
    lines, cur = [], ""
    for ch in text:
        if d.textlength(cur + ch, font=font) <= width:
            cur += ch
            continue
        # Prefer breaking at the last space for Latin words
        cut = cur.rfind(" ")
        if cut > 0 and ch != " ":
            lines.append(cur[:cut])
            cur = cur[cut + 1:] + ch
        else:
            lines.append(cur)
            cur = ch.lstrip()
    if cur:
        lines.append(cur)
    return lines or [""]


def render(source: Union[str, list, dict], now: datetime, title: Optional[str] = None) -> Image.Image:
    """source: tasks.txt text, or the artifact's task list (see parse_json)."""
    if isinstance(source, str):
        parsed_title, items = parse(source)
    else:
        parsed_title, items = parse_json(source, now.date())
    title = title or parsed_title or "任务清单"
    img = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(img)
    f_title, f_section = _font(60, True), _font(44, True)
    f_item, f_small = _font(42), _font(30)

    d.rectangle([0, 0, W, 130], fill=0)
    d.text((M, 30), title, font=f_title, fill=255)
    todo = sum(1 for k, _, _ in items if k == "todo")
    done = sum(1 for k, _, _ in items if k == "done")
    if todo + done:
        count = f"{done}/{todo + done}"
        d.text((W - M - d.textlength(count, font=f_section), 42), count, font=f_section, fill=255)

    y, bottom = 165, H - FOOTER_H - 20
    line_h, box = 58, 34
    text_x = M + box + 24
    hidden = 0
    for i, (kind, body, extra) in enumerate(items):
        if kind == "blank":
            y += 20
            continue
        font = f_section if kind == "section" else f_item
        x = M if kind in ("section", "text") else text_x
        lines = _wrap(d, body, font, W - M - x)
        need = (len(lines) * line_h) + (24 if kind == "section" else 10) + (52 if extra else 0)
        if y + need > bottom:
            hidden = sum(1 for k, _, _ in items[i:] if k != "blank")
            break
        if kind == "section":
            y += 14
        if kind in ("todo", "done"):
            by = y + (line_h - box) // 2
            d.rectangle([M, by, M + box, by + box], outline=0, width=4)
            if kind == "done":
                d.line([(M + 7, by + 18), (M + 15, by + 27), (M + 29, by + 7)], fill=0, width=5)
        elif kind == "bullet":
            cy = y + line_h // 2
            d.ellipse([M + 10, cy - 8, M + 26, cy + 8], fill=0)
        fill = 130 if kind == "done" else 0
        for ln in lines:
            d.text((x, y + 4), ln, font=font, fill=fill)
            if kind == "done":
                mid = y + line_h // 2 + 2
                d.line([(x, mid), (x + d.textlength(ln, font=font), mid)], fill=fill, width=3)
            y += line_h
        if kind == "section":
            d.line([(M, y + 4), (W - M, y + 4)], fill=0, width=3)
            y += 14
        if extra:
            # progress bar, percentage and due date under the title
            pct = f"{extra['progress']}%"
            bx0, bx1, by = x, x + 330, y + 12
            d.rectangle([bx0, by, bx1, by + 20], outline=0 if kind == "todo" else 150, width=3)
            if extra["progress"]:
                d.rectangle([bx0, by, bx0 + (bx1 - bx0) * extra["progress"] // 100, by + 20],
                            fill=0 if kind == "todo" else 150)
            d.text((bx1 + 16, y), pct, font=f_small, fill=fill)
            note = extra["note"]
            note_fill = 0 if "逾期" in note or "今天" in note else 90
            d.text((W - M - d.textlength(note, font=f_small), y), note, font=f_small, fill=note_fill)
            y += 52
        y += 18 if extra else 10

    if hidden:
        d.text((M, bottom - 10), f"… 还有 {hidden} 项 / {hidden} more", font=f_small, fill=90)
    if not items:
        d.text((M, 200), "(空 / empty)", font=f_item, fill=120)

    d.line([(M, H - FOOTER_H), (W - M, H - FOOTER_H)], fill=160, width=2)
    d.text((M, H - FOOTER_H + 16), f"更新 Updated {now:%m-%d %H:%M}", font=f_small, fill=90)
    hint = "点屏幕切换 · Tap to switch"
    d.text((W - M - d.textlength(hint, font=f_small), H - FOOTER_H + 16), hint, font=f_small, fill=90)
    return img


SAMPLE = """# 下周任务清单
## 周一
[ ] 把 pidash 装到 Kindle 上
[x] Kindle 越狱
## 周三
[ ] Raspberry Pi 到货后装系统
[ ] IB paper trading 跑一次 dry run
## 周末
- 和 Ken 对一下策略参数
"""


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("src", nargs="?", default=None, help="default: state/tasks.json, else state/tasks.txt")
    p.add_argument("out", nargs="?", default=None, help="default: state/dash/tasks.png, or next to src")
    p.add_argument("--sample", action="store_true", help="render a sample list")
    args = p.parse_args(argv)
    if args.src:
        src = Path(args.src)
    else:
        src = Path("state/tasks.json")
        if not src.exists():
            src = Path("state/tasks.txt")
    if args.sample:
        source = SAMPLE
    elif not src.exists():
        source = f"# 任务清单\n{src} not found"
    elif src.suffix.lower() == ".json":
        source = json.loads(src.read_text(encoding="utf-8-sig"))
    else:
        source = src.read_text(encoding="utf-8-sig")
    if args.out:
        out = Path(args.out)
    elif not args.src:
        out = Path("state/dash/tasks.png")
    else:
        out = src.with_suffix(".png")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.stem + ".tmp.png")
    render(source, datetime.now()).save(tmp)
    tmp.replace(out)
    print(out)


if __name__ == "__main__":
    sys.exit(main())
