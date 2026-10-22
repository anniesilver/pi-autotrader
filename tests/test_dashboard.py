from datetime import datetime

from PIL import ImageStat

from autotrader.dashboard import DEMO, H, W, render


def test_renders_demo_at_kindle_size():
    img = render(DEMO, [1.0, 2.0, 3.0], datetime(2026, 11, 16, 16, 0))
    assert img.size == (W, H) and img.mode == "L"


def test_renders_before_first_run():
    img = render({"result": "No run yet"}, [], datetime(2026, 11, 16, 16, 0))
    assert img.size == (W, H)


def test_stale_status_flagged():
    img = render(DEMO, [], datetime(2026, 11, 25, 9, 0))
    # Stale banner is drawn inverted (black box), so the banner area is mostly dark.
    banner = img.crop((70, 270, 1000, 350))
    assert ImageStat.Stat(banner).mean[0] < 128
