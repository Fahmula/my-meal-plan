"""JSON REST API (/api/...)."""

from datetime import date

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from . import images, notifier, services
from .dates import day_name, today_in, week_dates, week_start

router = APIRouter(prefix="/api")


def _not_found(exc: services.NotFound):
    raise HTTPException(status_code=404, detail=str(exc))


def _invalid(exc: services.ValidationError):
    detail = getattr(exc, "errors", None) or str(exc)
    raise HTTPException(status_code=422, detail=detail)


class MealIn(BaseModel):
    name: str = Field(..., max_length=services.NAME_MAX)
    description: str = Field("", max_length=services.DESCRIPTION_MAX)


class AssignIn(BaseModel):
    meal_id: int


class SwapIn(BaseModel):
    from_date: date
    to_date: date


class WeekIn(BaseModel):
    start: date


class SettingsIn(BaseModel):
    home_assistant_webhook_url: str | None = None
    notification_enabled: bool | None = None
    notification_time: str | None = Field(None, description="24h HH:MM")
    timezone: str | None = None
    notify_only_if_scheduled: bool | None = None


class TestIn(BaseModel):
    url: str | None = None


def _serialize_week(start: date) -> dict:
    return {
        "start": week_start(start).isoformat(),
        "end": week_dates(start)[-1].isoformat(),
        "days": [{"date": d["date"].isoformat(), "day": d["day"], "meal": d["meal"]} for d in services.get_week(start)],
    }


@router.get("/health")
def health():
    return {"status": "ok"}


# --------------------------------------------------------------------------- meals


@router.get("/meals")
def list_meals(q: str | None = None):
    return services.list_meals(q)


@router.post("/meals", status_code=201)
def create_meal(body: MealIn):
    try:
        return services.create_meal(body.name, body.description)
    except services.ValidationError as exc:
        _invalid(exc)


@router.get("/meals/{meal_id}")
def get_meal(meal_id: int):
    try:
        return services.get_meal(meal_id)
    except services.NotFound as exc:
        _not_found(exc)


@router.put("/meals/{meal_id}")
def update_meal(meal_id: int, body: MealIn):
    try:
        return services.update_meal(meal_id, body.name, body.description)
    except services.NotFound as exc:
        _not_found(exc)
    except services.ValidationError as exc:
        _invalid(exc)


@router.delete("/meals/{meal_id}")
def delete_meal(meal_id: int):
    """Permanently delete a meal preset from the library."""
    try:
        meal = services.delete_meal(meal_id)
    except services.NotFound as exc:
        _not_found(exc)
    return {"deleted": True, "id": meal["id"], "name": meal["name"]}


@router.post("/meals/{meal_id}/duplicate", status_code=201)
def duplicate_meal(meal_id: int):
    try:
        return services.duplicate_meal(meal_id)
    except services.NotFound as exc:
        _not_found(exc)


@router.post("/meals/{meal_id}/image")
async def upload_meal_image(meal_id: int, image: UploadFile = File(...)):
    try:
        services.get_meal(meal_id)
    except services.NotFound as exc:
        _not_found(exc)
    data = await image.read()
    try:
        name = await run_in_threadpool(images.save_image, data)
    except images.ImageError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return services.set_meal_image(meal_id, name)


@router.delete("/meals/{meal_id}/image")
def delete_meal_image(meal_id: int):
    try:
        return services.set_meal_image(meal_id, None)
    except services.NotFound as exc:
        _not_found(exc)


# ------------------------------------------------------------------------ schedule


@router.get("/schedule")
def get_schedule(start: date | None = Query(None, description="Any date in the week (YYYY-MM-DD)")):
    if start is None:
        start = today_in(services.get_settings()["timezone"])
    return _serialize_week(start)


@router.get("/schedule/today")
def get_today():
    today = today_in(services.get_settings()["timezone"])
    return {"date": today.isoformat(), "day": day_name(today), "meal": services.get_assignment(today)}


@router.put("/schedule/{day}")
def assign_day(day: date, body: AssignIn):
    try:
        meal = services.assign(day, body.meal_id)
    except services.NotFound as exc:
        _not_found(exc)
    return {"date": day.isoformat(), "day": day_name(day), "meal": meal}


@router.delete("/schedule/{day}")
def unassign_day(day: date):
    """Remove the meal planned on a date. The meal preset stays in the library."""
    meal = services.unassign(day)
    return {"date": day.isoformat(), "removed": meal is not None, "meal_id": meal["id"] if meal else None}


@router.post("/schedule/swap")
def swap_days(body: SwapIn):
    result = services.swap(body.from_date, body.to_date)
    return {"result": result, "from_date": body.from_date.isoformat(), "to_date": body.to_date.isoformat()}


@router.post("/schedule/copy-last-week")
def copy_last_week(body: WeekIn):
    copied = services.copy_week(services.previous_week(body.start), body.start)
    return {"copied": copied, **_serialize_week(body.start)}


@router.post("/schedule/clear-week")
def clear_week(body: WeekIn):
    removed = services.clear_week(body.start)
    return {"removed": removed, **_serialize_week(body.start)}


# ------------------------------------------------------------------------ settings


@router.get("/settings")
def get_settings():
    s = services.get_settings()
    s.pop("id", None)
    nxt = notifier.next_reminder(s)
    s["next_reminder"] = nxt.isoformat() if nxt else None
    return s


@router.put("/settings")
def put_settings(body: SettingsIn):
    try:
        services.update_settings(body.model_dump(exclude_none=True))
    except services.ValidationError as exc:
        _invalid(exc)
    return get_settings()


@router.post("/home-assistant/test")
async def test_webhook(body: TestIn | None = None):
    return await notifier.send_test(body.url if body else None)


@router.get("/webhook-logs")
def webhook_logs(limit: int = Query(50, ge=1, le=500)):
    return services.list_webhook_logs(limit)
