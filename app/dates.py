"""Week and date helpers. Weeks run Sunday through Saturday."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

# Pastel tint + readable ink colour for each day (Sunday first).
DAY_COLORS = [
    ("#fde8da", "#b0603a"),  # Sunday    – soft peach
    ("#dff2e3", "#3d7a50"),  # Monday    – soft green
    ("#fbf2cc", "#91731a"),  # Tuesday   – soft yellow
    ("#deecfa", "#3a6b9a"),  # Wednesday – soft blue
    ("#ebe4f9", "#6a55a6"),  # Thursday  – soft lavender
    ("#fbe2eb", "#a94d6e"),  # Friday    – soft pink
    ("#e4efd9", "#587c3a"),  # Saturday  – soft sage green
]


def day_index(d: date) -> int:
    """0 = Sunday ... 6 = Saturday."""
    return (d.weekday() + 1) % 7


def week_start(d: date) -> date:
    return d - timedelta(days=day_index(d))


def week_dates(start: date) -> list[date]:
    start = week_start(start)
    return [start + timedelta(days=i) for i in range(7)]


def day_name(d: date) -> str:
    return DAY_NAMES[day_index(d)]


def today_in(tz_name: str) -> date:
    return datetime.now(ZoneInfo(tz_name)).date()


def short_date(d: date) -> str:
    return f"{d:%b} {d.day}"


def week_label(start: date, today: date) -> str:
    end = start + timedelta(days=6)
    if start.year != end.year:
        return f"{short_date(start)}, {start.year} – {short_date(end)}, {end.year}"
    label = f"{short_date(start)} – {short_date(end)}"
    if start.year != today.year:
        label += f", {start.year}"
    return label


def relative_week(start: date, today: date) -> str:
    diff = (start - week_start(today)).days // 7
    if diff == 0:
        return "This week"
    if diff == 1:
        return "Next week"
    if diff == -1:
        return "Last week"
    if diff > 1:
        return f"In {diff} weeks"
    return f"{-diff} weeks ago"


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None
