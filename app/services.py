"""Data access for meals, the weekly schedule, settings and webhook logs.

Meal presets (``meals``) and calendar assignments (``weekly_schedule``) are
independent: removing a meal from a date never touches the preset, and the
same preset can be planned on any number of dates.
"""

import json
import random
import re
import sqlite3
from datetime import date, timedelta
from zoneinfo import ZoneInfo, available_timezones

from . import images
from .dates import day_name, week_dates, week_start
from .db import connect, utcnow

NAME_MAX = 120
DESCRIPTION_MAX = 500


class NotFound(LookupError):
    pass


class ValidationError(ValueError):
    pass


# --------------------------------------------------------------------------- meals


def _meal(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    meal = dict(row)
    meal["image_url"] = images.url_for(meal["image_path"])
    return meal


def clean_meal_fields(name: str | None, description: str | None) -> tuple[str, str]:
    name = re.sub(r"\s+", " ", (name or "")).strip()
    description = (description or "").strip()
    if not name:
        raise ValidationError("Please give the meal a name.")
    if len(name) > NAME_MAX:
        raise ValidationError(f"Meal name must be {NAME_MAX} characters or fewer.")
    if len(description) > DESCRIPTION_MAX:
        raise ValidationError(f"Description must be {DESCRIPTION_MAX} characters or fewer.")
    return name, description


def list_meals(query: str | None = None, limit: int | None = None) -> list[dict]:
    sql = """
        SELECT m.*, (SELECT COUNT(*) FROM weekly_schedule s WHERE s.meal_id = m.id) AS times_planned
        FROM meals m
    """
    params: list = []
    if query and query.strip():
        like = f"%{query.strip()}%"
        sql += " WHERE m.name LIKE ? OR m.description LIKE ?"
        params += [like, like]
    sql += " ORDER BY m.name COLLATE NOCASE, m.id"
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    with connect() as conn:
        return [_meal(r) for r in conn.execute(sql, params)]


def count_meals() -> int:
    with connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM meals").fetchone()[0]


def get_meal(meal_id: int) -> dict:
    with connect() as conn:
        row = conn.execute(
            """SELECT m.*, (SELECT COUNT(*) FROM weekly_schedule s WHERE s.meal_id = m.id) AS times_planned
               FROM meals m WHERE m.id = ?""",
            (meal_id,),
        ).fetchone()
    if row is None:
        raise NotFound(f"Meal {meal_id} not found.")
    return _meal(row)


def create_meal(name: str, description: str = "", image_path: str | None = None) -> dict:
    name, description = clean_meal_fields(name, description)
    now = utcnow()
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO meals (name, description, image_path, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (name, description, image_path, now, now),
        )
        meal_id = cur.lastrowid
    return get_meal(meal_id)


def update_meal(meal_id: int, name: str, description: str) -> dict:
    name, description = clean_meal_fields(name, description)
    with connect() as conn:
        cur = conn.execute(
            "UPDATE meals SET name = ?, description = ?, updated_at = ? WHERE id = ?",
            (name, description, utcnow(), meal_id),
        )
        if cur.rowcount == 0:
            raise NotFound(f"Meal {meal_id} not found.")
    return get_meal(meal_id)


def set_meal_image(meal_id: int, image_path: str | None) -> dict:
    old = get_meal(meal_id)["image_path"]
    with connect() as conn:
        conn.execute(
            "UPDATE meals SET image_path = ?, updated_at = ? WHERE id = ?",
            (image_path, utcnow(), meal_id),
        )
    if old and old != image_path:
        images.delete_image(old)
    return get_meal(meal_id)


def delete_meal(meal_id: int) -> dict:
    """Permanently delete a preset (and, necessarily, the dates it was planned on)."""
    meal = get_meal(meal_id)
    with connect() as conn:
        conn.execute("DELETE FROM meals WHERE id = ?", (meal_id,))
    images.delete_image(meal["image_path"])
    return meal


def duplicate_meal(meal_id: int) -> dict:
    meal = get_meal(meal_id)
    name = meal["name"]
    copy_name = f"{name} (copy)"[:NAME_MAX]
    return create_meal(copy_name, meal["description"], images.copy_image(meal["image_path"]))


def random_meal(exclude_ids: set[int] | None = None) -> dict | None:
    meals = list_meals()
    if not meals:
        return None
    fresh = [m for m in meals if m["id"] not in (exclude_ids or set())]
    return random.choice(fresh or meals)


# ------------------------------------------------------------------------ schedule


def get_assignment(d: date) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            """SELECT m.* FROM weekly_schedule s JOIN meals m ON m.id = s.meal_id WHERE s.date = ?""",
            (d.isoformat(),),
        ).fetchone()
    return _meal(row)


def get_week(start: date) -> list[dict]:
    """Seven day entries (Sunday first) for the week containing ``start``."""
    days = week_dates(start)
    with connect() as conn:
        rows = conn.execute(
            """SELECT s.date AS planned_date, m.* FROM weekly_schedule s
               JOIN meals m ON m.id = s.meal_id
               WHERE s.date BETWEEN ? AND ?""",
            (days[0].isoformat(), days[-1].isoformat()),
        ).fetchall()
    by_date = {}
    for row in rows:
        meal = dict(row)
        planned = meal.pop("planned_date")
        meal["image_url"] = images.url_for(meal["image_path"])
        by_date[planned] = meal
    return [{"date": d, "day": day_name(d), "meal": by_date.get(d.isoformat())} for d in days]


def assign(d: date, meal_id: int) -> dict:
    meal = get_meal(meal_id)  # raises NotFound
    now = utcnow()
    with connect() as conn:
        conn.execute(
            """INSERT INTO weekly_schedule (date, meal_id, created_at, updated_at) VALUES (?, ?, ?, ?)
               ON CONFLICT (date) DO UPDATE SET meal_id = excluded.meal_id, updated_at = excluded.updated_at""",
            (d.isoformat(), meal_id, now, now),
        )
    return meal


def unassign(d: date) -> dict | None:
    """Remove whatever is planned on a date. The meal preset is kept."""
    meal = get_assignment(d)
    with connect() as conn:
        conn.execute("DELETE FROM weekly_schedule WHERE date = ?", (d.isoformat(),))
    return meal


def swap(a: date, b: date) -> str:
    """Swap the meals on two dates (or move one if the other is empty).

    Returns ``"swapped"``, ``"moved"`` or ``"noop"``.
    """
    if a == b:
        return "noop"
    now = utcnow()
    with connect() as conn:
        rows = dict(
            conn.execute(
                "SELECT date, meal_id FROM weekly_schedule WHERE date IN (?, ?)",
                (a.isoformat(), b.isoformat()),
            ).fetchall()
        )
        meal_a, meal_b = rows.get(a.isoformat()), rows.get(b.isoformat())
        if meal_a is None and meal_b is None:
            return "noop"
        conn.execute("DELETE FROM weekly_schedule WHERE date IN (?, ?)", (a.isoformat(), b.isoformat()))
        for target, meal_id in ((b, meal_a), (a, meal_b)):
            if meal_id is not None:
                conn.execute(
                    "INSERT INTO weekly_schedule (date, meal_id, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (target.isoformat(), meal_id, now, now),
                )
    return "swapped" if meal_a is not None and meal_b is not None else "moved"


def week_meal_count(start: date) -> int:
    return sum(1 for d in get_week(start) if d["meal"])


def copy_week(source_start: date, target_start: date) -> int:
    """Replace the target week with the source week's plan. Returns meals copied."""
    source = week_dates(source_start)
    target = week_dates(target_start)
    now = utcnow()
    with connect() as conn:
        rows = dict(
            conn.execute(
                "SELECT date, meal_id FROM weekly_schedule WHERE date BETWEEN ? AND ?",
                (source[0].isoformat(), source[-1].isoformat()),
            ).fetchall()
        )
        if not rows:
            return 0
        conn.execute(
            "DELETE FROM weekly_schedule WHERE date BETWEEN ? AND ?",
            (target[0].isoformat(), target[-1].isoformat()),
        )
        for src, dst in zip(source, target, strict=True):
            meal_id = rows.get(src.isoformat())
            if meal_id is not None:
                conn.execute(
                    "INSERT INTO weekly_schedule (date, meal_id, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (dst.isoformat(), meal_id, now, now),
                )
    return len(rows)


def clear_week(start: date) -> int:
    days = week_dates(start)
    with connect() as conn:
        cur = conn.execute(
            "DELETE FROM weekly_schedule WHERE date BETWEEN ? AND ?",
            (days[0].isoformat(), days[-1].isoformat()),
        )
        return cur.rowcount


def previous_week(start: date) -> date:
    return week_start(start) - timedelta(days=7)


# ------------------------------------------------------------------------ settings

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def get_settings() -> dict:
    with connect() as conn:
        row = conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    s = dict(row)
    s["notification_enabled"] = bool(s["notification_enabled"])
    s["notify_only_if_scheduled"] = bool(s["notify_only_if_scheduled"])
    return s


def validate_settings(data: dict) -> dict:
    """Validate a (partial) settings dict. Returns cleaned values; raises ValidationError."""
    clean: dict = {}
    errors: dict[str, str] = {}
    if "home_assistant_webhook_url" in data:
        url = (data["home_assistant_webhook_url"] or "").strip()
        if url and not re.match(r"^https?://[^\s/$.?#][^\s]*$", url, re.I):
            errors["home_assistant_webhook_url"] = "Enter a full URL starting with http:// or https://"
        clean["home_assistant_webhook_url"] = url
    if "notification_time" in data:
        value = (data["notification_time"] or "").strip()[:5]
        if not _TIME_RE.match(value):
            errors["notification_time"] = "Use a 24-hour time such as 17:00."
        clean["notification_time"] = value
    if "timezone" in data:
        tz = (data["timezone"] or "").strip()
        if tz not in available_timezones():
            errors["timezone"] = "Unknown timezone."
        clean["timezone"] = tz
    for key in ("notification_enabled", "notify_only_if_scheduled"):
        if key in data:
            clean[key] = bool(data[key])
    if errors:
        err = ValidationError("; ".join(errors.values()))
        err.errors = errors  # type: ignore[attr-defined]
        raise err
    return clean


def update_settings(data: dict) -> dict:
    clean = validate_settings(data)
    if clean:
        cols = ", ".join(f"{k} = ?" for k in clean)
        values = [int(v) if isinstance(v, bool) else v for v in clean.values()]
        with connect() as conn:
            conn.execute(f"UPDATE settings SET {cols} WHERE id = 1", values)
    return get_settings()


def set_last_reminder_key(key: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE settings SET last_reminder_key = ? WHERE id = 1", (key,))


def timezone_of(settings: dict) -> ZoneInfo:
    try:
        return ZoneInfo(settings["timezone"])
    except Exception:
        return ZoneInfo("UTC")


# -------------------------------------------------------------------- webhook logs

LOG_KEEP = 500


def add_webhook_log(
    kind: str,
    payload: dict,
    success: bool,
    response_status: int | None,
    error: str | None = None,
) -> None:
    meal_id = payload.get("meal_id")
    with connect() as conn:
        # meal_id may reference a meal deleted moments ago – store NULL then.
        exists = meal_id and conn.execute("SELECT 1 FROM meals WHERE id = ?", (int(meal_id),)).fetchone()
        conn.execute(
            """INSERT INTO webhook_logs (timestamp, kind, meal_id, meal_name, payload, response_status, success, error)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                utcnow(),
                kind,
                int(meal_id) if exists else None,
                payload.get("meal_name"),
                json.dumps(payload),
                response_status,
                int(success),
                error,
            ),
        )
        conn.execute(
            "DELETE FROM webhook_logs WHERE id NOT IN (SELECT id FROM webhook_logs ORDER BY id DESC LIMIT ?)",
            (LOG_KEEP,),
        )


def list_webhook_logs(limit: int = 50) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM webhook_logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    logs = []
    for row in rows:
        log = dict(row)
        log["success"] = bool(log["success"])
        log["payload"] = json.loads(log["payload"])
        logs.append(log)
    return logs
