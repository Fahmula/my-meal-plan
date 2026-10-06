import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from app import notifier, services

NY = ZoneInfo("America/New_York")


class FakePost:
    def __init__(self, status=200):
        self.calls = []
        self.status = status

    async def __call__(self, url, payload):
        self.calls.append((url, payload))
        ok = 200 <= self.status < 300
        return ok, self.status, None if ok else "boom"


def setup(monkeypatch, status=200, **settings):
    fake = FakePost(status)
    monkeypatch.setattr(notifier, "post_webhook", fake)
    monkeypatch.setattr(notifier, "RETRY_DELAYS", ())
    services.update_settings({"home_assistant_webhook_url": "http://ha:8123/api/webhook/x", **settings})
    return fake


def run(coro):
    return asyncio.run(coro)


def test_sends_once_at_reminder_time(monkeypatch):
    fake = setup(monkeypatch)
    meal = services.create_meal("Beef Tacos", "Minced beef, tortillas, cheese, lettuce and fresh toppings")
    services.assign(datetime(2026, 10, 5).date(), meal["id"])

    assert run(notifier.check_and_send(datetime(2026, 10, 5, 16, 59, tzinfo=NY))) is None
    result = run(notifier.check_and_send(datetime(2026, 10, 5, 17, 0, 10, tzinfo=NY)))
    assert result["success"] is True
    payload = fake.calls[0][1]
    assert payload == {
        "event": "dinner_reminder",
        "date": "2026-10-05",
        "day": "Monday",
        "meal_id": str(meal["id"]),
        "meal_name": "Beef Tacos",
        "description": "Minced beef, tortillas, cheese, lettuce and fresh toppings",
    }
    # Not sent twice the same day.
    assert run(notifier.check_and_send(datetime(2026, 10, 5, 17, 1, tzinfo=NY))) is None
    assert len(fake.calls) == 1
    log = services.list_webhook_logs()[0]
    assert log["success"] and log["response_status"] == 200 and log["kind"] == "scheduled"


def test_skips_empty_day_when_notify_only_if_scheduled(monkeypatch):
    fake = setup(monkeypatch)
    assert run(notifier.check_and_send(datetime(2026, 10, 5, 17, 0, tzinfo=NY))) is None
    assert fake.calls == []


def test_sends_empty_day_when_option_off(monkeypatch):
    fake = setup(monkeypatch, notify_only_if_scheduled=False)
    run(notifier.check_and_send(datetime(2026, 10, 5, 17, 0, tzinfo=NY)))
    assert fake.calls[0][1]["meal_name"] == "No meal planned"
    assert fake.calls[0][1]["meal_id"] is None


def test_disabled_and_catch_up_window(monkeypatch):
    fake = setup(monkeypatch, notification_enabled=False, notify_only_if_scheduled=False)
    run(notifier.check_and_send(datetime(2026, 10, 5, 17, 0, tzinfo=NY)))
    assert fake.calls == []
    services.update_settings({"notification_enabled": True})
    # Server came back long after reminder time: do not send a stale reminder.
    run(notifier.check_and_send(datetime(2026, 10, 5, 19, 0, tzinfo=NY)))
    assert fake.calls == []
    # Within the catch-up window it still sends.
    run(notifier.check_and_send(datetime(2026, 10, 5, 17, 20, tzinfo=NY)))
    assert len(fake.calls) == 1


def test_changing_time_allows_new_reminder_same_day(monkeypatch):
    fake = setup(monkeypatch, notify_only_if_scheduled=False)
    run(notifier.check_and_send(datetime(2026, 10, 5, 17, 0, tzinfo=NY)))
    services.update_settings({"notification_time": "18:00"})
    run(notifier.check_and_send(datetime(2026, 10, 5, 18, 0, tzinfo=NY)))
    assert len(fake.calls) == 2


def test_failed_webhook_is_logged(monkeypatch):
    setup(monkeypatch, status=500, notify_only_if_scheduled=False)
    result = run(notifier.check_and_send(datetime(2026, 10, 5, 17, 0, tzinfo=NY)))
    assert result["success"] is False
    log = services.list_webhook_logs()[0]
    assert log["success"] is False and log["response_status"] == 500


def test_test_endpoint(client, monkeypatch):
    fake = setup(monkeypatch)
    r = client.post("/api/home-assistant/test").json()
    assert r["success"] is True
    assert fake.calls[0][1]["test"] is True
    assert client.get("/api/webhook-logs").json()[0]["kind"] == "test"


def test_test_without_url(client):
    r = client.post("/api/home-assistant/test").json()
    assert r["success"] is False
    assert "No webhook URL" in r["error"]


def test_real_http_failure_is_reported():
    ok, status, error = run(notifier.post_webhook("http://127.0.0.1:9/api/webhook/x", {"a": 1}))
    assert ok is False and status is None and error
