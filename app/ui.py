"""Server-rendered pages and HTMX fragments."""

import json
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from zoneinfo import available_timezones

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from . import config, images, notifier, services
from .dates import (
    DAY_COLORS,
    day_index,
    day_name,
    relative_week,
    short_date,
    today_in,
    week_label,
    week_start,
)

router = APIRouter()
templates = Jinja2Templates(directory=config.APP_DIR / "templates")


# ------------------------------------------------------------------- jinja helpers


def time12(value: str) -> str:
    try:
        hh, mm = map(int, value.split(":"))
    except (ValueError, AttributeError):
        return value
    suffix = "AM" if hh < 12 else "PM"
    return f"{(hh % 12) or 12}:{mm:02d} {suffix}"


def local_dt(value: str | datetime | None) -> str:
    if not value:
        return ""
    dt = datetime.fromisoformat(value) if isinstance(value, str) else value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    dt = dt.astimezone(services.timezone_of(services.get_settings()))
    return f"{dt:%b} {dt.day}, {time12(dt.strftime('%H:%M'))}"


def day_style(d: date) -> str:
    tint, ink = DAY_COLORS[day_index(d)]
    return f"--day-tint:{tint};--day-ink:{ink}"


templates.env.filters["time12"] = time12
templates.env.filters["local_dt"] = local_dt
templates.env.filters["short_date"] = short_date
templates.env.globals["day_style"] = day_style
templates.env.globals["day_name"] = day_name


@lru_cache
def timezone_choices() -> list[str]:
    return sorted(tz for tz in available_timezones() if "/" in tz and not tz.startswith(("posix/", "right/")))


def render(request: Request, name: str, status_code: int = 200, headers: dict | None = None, **ctx) -> HTMLResponse:
    return templates.TemplateResponse(request, name, ctx, status_code=status_code, headers=headers)


def hx_headers(
    toast: str | None = None,
    toast_type: str = "success",
    close_modal: bool = False,
    refresh_week: bool = False,
    retarget: str | None = None,
) -> dict:
    events: dict = {}
    if toast:
        events["toast"] = {"message": toast, "type": toast_type}
    if close_modal:
        events["closeModal"] = True
    if refresh_week:
        events["refreshWeek"] = True
    headers = {}
    if events:
        headers["HX-Trigger"] = json.dumps(events)
    if retarget:
        headers["HX-Retarget"] = retarget
        headers["HX-Reswap"] = "outerHTML"
    return headers


def current_today() -> date:
    return today_in(services.get_settings()["timezone"])


def week_context(start: date) -> dict:
    today = current_today()
    start = week_start(start)
    days = services.get_week(start)
    for d in days:
        d["short"] = d["day"][:3].upper()
        d["is_today"] = d["date"] == today
        d["style"] = day_style(d["date"])
    planned = sum(1 for d in days if d["meal"])
    prev_start = start - timedelta(days=7)
    return {
        "start": start,
        "days": days,
        "today": today,
        "label": week_label(start, today),
        "relative": relative_week(start, today),
        "is_current": start == week_start(today),
        "prev_start": prev_start,
        "next_start": start + timedelta(days=7),
        "planned_count": planned,
        "prev_planned_count": services.week_meal_count(prev_start),
        "library_count": services.count_meals(),
    }


def week_response(request: Request, d: date, **hx) -> HTMLResponse:
    """Re-render the week region containing ``d`` (wherever the request came from)."""
    return render(
        request,
        "partials/week.html",
        headers=hx_headers(retarget="#week-region", **hx),
        **week_context(d),
    )


async def read_upload(upload: UploadFile | None) -> bytes:
    if upload is None or not upload.filename:
        return b""
    return await upload.read()


# -------------------------------------------------------------------------- pages


@router.get("/", response_class=HTMLResponse)
def index(request: Request, week: str | None = None):
    start = _parse(week) or current_today()
    return render(request, "index.html", **week_context(start))


@router.get("/ui/week", response_class=HTMLResponse)
def week_region(request: Request, start: str | None = None):
    return render(request, "partials/week.html", **week_context(_parse(start) or current_today()))


def _parse(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


# ------------------------------------------------------------------ schedule edits


@router.post("/ui/schedule/swap", response_class=HTMLResponse)
def ui_swap(request: Request, from_date: date = Form(...), to_date: date = Form(...)):
    services.swap(from_date, to_date)
    return week_response(request, to_date)


@router.post("/ui/week/copy-last", response_class=HTMLResponse)
def ui_copy_last_week(request: Request, start: date = Form(...)):
    copied = services.copy_week(services.previous_week(start), start)
    if not copied:
        return week_response(request, start, toast="Last week has no meals to copy", toast_type="info")
    return week_response(request, start, toast=f"Copied {copied} meal{'s' if copied != 1 else ''} from last week")


@router.post("/ui/week/clear", response_class=HTMLResponse)
def ui_clear_week(request: Request, start: date = Form(...)):
    removed = services.clear_week(start)
    msg = "Week cleared · your saved meals are still in the library" if removed else "This week is already empty"
    return week_response(request, start, toast=msg, toast_type="success" if removed else "info")


@router.post("/ui/day/{d}/random", response_class=HTMLResponse)
def ui_random(request: Request, d: date):
    planned = {day["meal"]["id"] for day in services.get_week(d) if day["meal"]}
    meal = services.random_meal(planned)
    if meal is None:
        return week_response(request, d, toast="Add some meals to your library first", toast_type="info")
    services.assign(d, meal["id"])
    return week_response(request, d, toast=f"Random pick for {day_name(d)}: {meal['name']}")


@router.post("/ui/day/{d}/assign", response_class=HTMLResponse)
def ui_assign(request: Request, d: date, meal_id: int = Form(...)):
    try:
        meal = services.assign(d, meal_id)
    except services.NotFound:
        return week_response(request, d, toast="That meal no longer exists", toast_type="error")
    return week_response(request, d, toast=f"{meal['name']} planned for {day_name(d)}")


@router.post("/ui/day/{d}/remove", response_class=HTMLResponse)
def ui_remove(request: Request, d: date):
    meal = services.unassign(d)
    msg = f"Removed from {day_name(d)} · {meal['name']} is still in your library" if meal else "Nothing to remove"
    return week_response(request, d, toast=msg, close_modal=True)


# --------------------------------------------------------------------- day editor


def day_modal(
    request: Request,
    d: date,
    meal: dict | None,
    *,
    picked: bool = False,
    errors: str | None = None,
    form: dict | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    current = services.get_assignment(d)
    return render(
        request,
        "partials/day_modal.html",
        status_code=status_code,
        d=d,
        day=day_name(d),
        current=current,
        meal=meal,
        picked=picked,
        errors=errors,
        form=form or {},
        library_count=services.count_meals(),
    )


@router.get("/ui/day/{d}/edit", response_class=HTMLResponse)
def ui_day_edit(request: Request, d: date, meal_id: int | None = None, new: bool = False, name: str = ""):
    if new:
        return day_modal(request, d, None, form={"name": name} if name else None)
    if meal_id is not None:
        try:
            return day_modal(request, d, services.get_meal(meal_id), picked=True)
        except services.NotFound:
            pass
    return day_modal(request, d, services.get_assignment(d))


@router.get("/ui/day/{d}/picker", response_class=HTMLResponse)
def ui_day_picker(request: Request, d: date, q: str = ""):
    meals = services.list_meals(q, limit=8)
    return render(request, "partials/picker_results.html", d=d, meals=meals, q=q)


@router.post("/ui/day/{d}/save", response_class=HTMLResponse)
async def ui_day_save(
    request: Request,
    d: date,
    meal_id: str = Form(""),
    name: str = Form(""),
    description: str = Form(""),
    remove_image: str = Form(""),
    save_as_new: str = Form(""),
    image: UploadFile | None = File(None),
):
    existing = None
    if meal_id.isdigit():
        try:
            existing = services.get_meal(int(meal_id))
        except services.NotFound:
            existing = None
    form = {"name": name, "description": description}
    try:
        name, description = services.clean_meal_fields(name, description)
        data = await read_upload(image)
        new_image = await run_in_threadpool(images.save_image, data) if data else None
    except (services.ValidationError, images.ImageError) as exc:
        return day_modal(request, d, existing, picked=bool(existing), errors=str(exc), form=form)

    if existing and not save_as_new:
        meal = services.update_meal(existing["id"], name, description)
        if new_image:
            meal = services.set_meal_image(meal["id"], new_image)
        elif remove_image:
            meal = services.set_meal_image(meal["id"], None)
    else:
        img = new_image
        if not img and existing and not remove_image:
            img = images.copy_image(existing["image_path"])
        meal = services.create_meal(name, description, img)

    services.assign(d, meal["id"])
    return week_response(request, d, toast=f"{meal['name']} planned for {day_name(d)}", close_modal=True)


# ------------------------------------------------------------------- meal library


def library_context(week: date | None, q: str = "") -> dict:
    start = week_start(week or current_today())
    days = services.get_week(start)
    for day in days:
        day["style"] = day_style(day["date"])
        day["short"] = day["day"][:3]
    return {"meals": services.list_meals(q), "q": q, "week": start, "week_days": days}


@router.get("/ui/library", response_class=HTMLResponse)
def ui_library(request: Request, week: str | None = None, q: str = ""):
    return render(request, "partials/library.html", **library_context(_parse(week), q))


@router.get("/ui/library/list", response_class=HTMLResponse)
def ui_library_list(request: Request, week: str | None = None, q: str = ""):
    return render(request, "partials/library_list.html", **library_context(_parse(week), q))


def meal_form(
    request: Request,
    week: date | None,
    meal: dict | None,
    errors: str | None = None,
    form: dict | None = None,
    headers: dict | None = None,
) -> HTMLResponse:
    return render(
        request,
        "partials/meal_form.html",
        headers=headers,
        meal=meal,
        week=week_start(week or current_today()),
        errors=errors,
        form=form or {},
    )


@router.get("/ui/library/new", response_class=HTMLResponse)
def ui_library_new(request: Request, week: str | None = None):
    return meal_form(request, _parse(week), None)


@router.get("/ui/library/{meal_id}/edit", response_class=HTMLResponse)
def ui_library_edit(request: Request, meal_id: int, week: str | None = None):
    try:
        meal = services.get_meal(meal_id)
    except services.NotFound:
        return render(request, "partials/library.html", **library_context(_parse(week)))
    return meal_form(request, _parse(week), meal)


@router.post("/ui/library/save", response_class=HTMLResponse)
async def ui_library_save(
    request: Request,
    week: str = Form(""),
    meal_id: str = Form(""),
    name: str = Form(""),
    description: str = Form(""),
    remove_image: str = Form(""),
    image: UploadFile | None = File(None),
):
    wk = _parse(week)
    existing = None
    if meal_id.isdigit():
        try:
            existing = services.get_meal(int(meal_id))
        except services.NotFound:
            existing = None
    try:
        name, description = services.clean_meal_fields(name, description)
        data = await read_upload(image)
        new_image = await run_in_threadpool(images.save_image, data) if data else None
    except (services.ValidationError, images.ImageError) as exc:
        return meal_form(request, wk, existing, errors=str(exc), form={"name": name, "description": description})

    if existing:
        meal = services.update_meal(existing["id"], name, description)
        if new_image:
            meal = services.set_meal_image(meal["id"], new_image)
        elif remove_image:
            meal = services.set_meal_image(meal["id"], None)
        msg = f"Saved changes to {meal['name']}"
    else:
        meal = services.create_meal(name, description, new_image)
        msg = f"{meal['name']} added to your library"
    return render(
        request,
        "partials/library.html",
        headers=hx_headers(toast=msg, refresh_week=True),
        **library_context(wk),
    )


@router.post("/ui/library/{meal_id}/duplicate", response_class=HTMLResponse)
def ui_library_duplicate(request: Request, meal_id: int, week: str = Form("")):
    try:
        copy = services.duplicate_meal(meal_id)
    except services.NotFound:
        return render(request, "partials/library.html", **library_context(_parse(week)))
    return meal_form(request, _parse(week), copy, headers=hx_headers(toast=f"Created {copy['name']}"))


@router.delete("/ui/library/{meal_id}", response_class=HTMLResponse)
def ui_library_delete(request: Request, meal_id: int, week: str | None = None, q: str = ""):
    try:
        meal = services.delete_meal(meal_id)
        headers = hx_headers(toast=f"{meal['name']} deleted permanently", refresh_week=True)
    except services.NotFound:
        headers = None
    return render(
        request,
        "partials/library.html",
        headers=headers,
        **library_context(_parse(week), q),
    )


# ----------------------------------------------------------------------- settings


def settings_context(errors: dict | None = None, form: dict | None = None) -> dict:
    s = services.get_settings()
    if form:
        s.update(form)
    nxt = notifier.next_reminder(services.get_settings())
    return {
        "s": s,
        "errors": errors or {},
        "timezones": timezone_choices(),
        "next_reminder": local_dt(nxt) if nxt else None,
        "logs": services.list_webhook_logs(20),
    }


@router.get("/ui/settings", response_class=HTMLResponse)
def ui_settings(request: Request):
    return render(request, "partials/settings.html", **settings_context())


@router.put("/ui/settings", response_class=HTMLResponse)
def ui_settings_save(
    request: Request,
    home_assistant_webhook_url: str = Form(""),
    notification_time: str = Form("17:00"),
    timezone_name: str = Form("America/New_York", alias="timezone"),
    notification_enabled: str = Form(""),
    notify_only_if_scheduled: str = Form(""),
):
    form = {
        "home_assistant_webhook_url": home_assistant_webhook_url,
        "notification_time": notification_time,
        "timezone": timezone_name,
        "notification_enabled": bool(notification_enabled),
        "notify_only_if_scheduled": bool(notify_only_if_scheduled),
    }
    try:
        services.update_settings(form)
    except services.ValidationError as exc:
        return render(request, "partials/settings_form.html", **settings_context(getattr(exc, "errors", {}), form))
    return render(
        request,
        "partials/settings_form.html",
        headers=hx_headers(toast="Settings saved", refresh_week=True),
        **settings_context(),
    )


@router.post("/ui/settings/test", response_class=HTMLResponse)
async def ui_settings_test(request: Request, home_assistant_webhook_url: str = Form("")):
    url = home_assistant_webhook_url.strip()
    if url:
        try:
            services.validate_settings({"home_assistant_webhook_url": url})
        except services.ValidationError as exc:
            result = {"success": False, "response_status": None, "error": str(exc)}
            return render(request, "partials/test_result.html", result=result, logs=services.list_webhook_logs(20))
    result = await notifier.send_test(url or None)
    return render(request, "partials/test_result.html", result=result, logs=services.list_webhook_logs(20))


@router.get("/ui/settings/logs", response_class=HTMLResponse)
def ui_settings_logs(request: Request):
    return render(request, "partials/webhook_logs.html", logs=services.list_webhook_logs(20))
