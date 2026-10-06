"""Home Assistant webhook delivery and the daily dinner-reminder scheduler.

The scheduler runs inside the server process (an asyncio task started at app
startup), so reminders are sent whether or not any browser is open.
"""

import asyncio
import contextlib
import logging
from datetime import date, datetime, time, timedelta

import httpx

from . import config, services
from .dates import day_name

log = logging.getLogger("meal_plan.notifier")

CHECK_INTERVAL_SECONDS = 20
# If the server was down at reminder time, still send when it comes back
# within this window (but never twice for the same day/time).
CATCH_UP_WINDOW = timedelta(minutes=30)
RETRY_DELAYS = (3, 15)


def build_payload(d: date, meal: dict | None, *, test: bool = False) -> dict:
    payload = {
        "event": "dinner_reminder",
        "date": d.isoformat(),
        "day": day_name(d),
        "meal_id": str(meal["id"]) if meal else None,
        "meal_name": meal["name"] if meal else "No meal planned",
        "description": meal["description"] if meal else "",
    }
    if meal and meal.get("image_path") and config.APP_BASE_URL:
        payload["image_url"] = f"{config.APP_BASE_URL}/uploads/{meal['image_path']}"
    if test:
        payload["test"] = True
    return payload


async def post_webhook(url: str, payload: dict) -> tuple[bool, int | None, str | None]:
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.post(url, json=payload)
        ok = 200 <= resp.status_code < 300
        return ok, resp.status_code, None if ok else (resp.text[:300] or resp.reason_phrase)
    except httpx.HTTPError as exc:
        return False, None, f"{type(exc).__name__}: {exc}"[:300] or type(exc).__name__


async def send(url: str, payload: dict, kind: str, retries: tuple[int, ...] = ()) -> dict:
    ok, status, error = await post_webhook(url, payload)
    for delay in retries:
        if ok:
            break
        await asyncio.sleep(delay)
        ok, status, error = await post_webhook(url, payload)
    services.add_webhook_log(kind, payload, ok, status, error)
    log.info("Webhook %s -> %s (status=%s ok=%s)", kind, payload.get("meal_name"), status, ok)
    return {"success": ok, "response_status": status, "error": error, "payload": payload}


async def send_test(url: str | None = None) -> dict:
    settings = services.get_settings()
    url = (url if url is not None else settings["home_assistant_webhook_url"]).strip()
    if not url:
        return {"success": False, "response_status": None, "error": "No webhook URL configured.", "payload": None}
    today = datetime.now(services.timezone_of(settings)).date()
    meal = services.get_assignment(today)
    payload = build_payload(today, meal, test=True)
    if not meal:
        payload["meal_name"] = "Test notification"
        payload["description"] = "My Meal Plan is connected to Home Assistant."
    return await send(url, payload, "test")


def next_reminder(settings: dict, now: datetime | None = None) -> datetime | None:
    if not settings["notification_enabled"] or not settings["home_assistant_webhook_url"]:
        return None
    tz = services.timezone_of(settings)
    now = now or datetime.now(tz)
    hh, mm = map(int, settings["notification_time"].split(":"))
    candidate = datetime.combine(now.date(), time(hh, mm), tz)
    key = f"{now.date().isoformat()} {settings['notification_time']}"
    if now > candidate and (now - candidate > CATCH_UP_WINDOW or settings["last_reminder_key"] == key):
        candidate = datetime.combine(now.date() + timedelta(days=1), time(hh, mm), tz)
    return candidate


async def check_and_send(now: datetime | None = None) -> dict | None:
    """Send today's reminder if it is due. Returns the send result, or None."""
    settings = services.get_settings()
    url = settings["home_assistant_webhook_url"]
    if not settings["notification_enabled"] or not url:
        return None
    tz = services.timezone_of(settings)
    now = (now or datetime.now(tz)).astimezone(tz)
    hh, mm = map(int, settings["notification_time"].split(":"))
    due = datetime.combine(now.date(), time(hh, mm), tz)
    if now < due or now - due > CATCH_UP_WINDOW:
        return None
    key = f"{now.date().isoformat()} {settings['notification_time']}"
    if settings["last_reminder_key"] == key:
        return None
    # Mark first so a slow/failed request can never cause duplicate reminders.
    services.set_last_reminder_key(key)
    meal = services.get_assignment(now.date())
    if meal is None and settings["notify_only_if_scheduled"]:
        log.info("No dinner planned for %s – reminder skipped", now.date())
        return None
    return await send(url, build_payload(now.date(), meal), "scheduled", RETRY_DELAYS)


async def run_scheduler(stop: asyncio.Event) -> None:
    log.info("Dinner reminder scheduler started")
    while not stop.is_set():
        try:
            await check_and_send()
        except Exception:  # never let the loop die
            log.exception("Reminder check failed")
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=CHECK_INTERVAL_SECONDS)
    log.info("Dinner reminder scheduler stopped")
