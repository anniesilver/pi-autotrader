from datetime import datetime

from autotrader.tasks_page import H, SAMPLE, W, parse, parse_json, render

NOW = datetime(2026, 10, 22, 19, 0)


def test_parse_text_list():
    title, items = parse(SAMPLE)
    assert title == "下周任务清单"
    kinds = [k for k, _, _ in items]
    assert kinds[:3] == ["section", "todo", "done"]
    assert "bullet" in kinds


def test_parse_artifact_tasks_sorted_with_due_notes():
    tasks = [
        {"title": "b", "due": "2026-10-27", "progress": 0, "order": 2},
        {"title": "a", "due": "2026-10-17", "progress": 100, "order": 1},
        {"title": "c", "due": "2026-10-20", "progress": 40, "order": 3},
    ]
    _, items = parse_json(tasks, NOW.date())
    assert [t for _, t, _ in items] == ["a", "b", "c"]
    assert items[0][0] == "done" and items[1][0] == "todo"
    assert "还剩 5 天" in items[1][2]["note"]
    assert "逾期 2 天" in items[2][2]["note"]


def test_renders_both_formats_at_kindle_size():
    for source in (SAMPLE, {"title": "x", "tasks": [{"title": "t", "progress": 50}]}, ""):
        img = render(source, NOW)
        assert img.size == (W, H) and img.mode == "L"


def test_long_list_does_not_overflow():
    img = render("\n".join(f"[ ] task {i}" for i in range(60)), NOW)
    assert img.size == (W, H)
