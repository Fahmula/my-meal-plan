import json
from datetime import date

from app import services


def test_index_renders_seven_days(client):
    r = client.get("/?week=2026-10-05")
    assert r.status_code == 200
    html = r.text
    assert "My Meal Plan" in html and "A simple plan for a delicious week" in html
    for day in ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]:
        assert day in html
    assert html.count('class="day-card') == 7
    assert "Oct 4 – Oct 10" in html
    assert html.count("No meal planned") == 7


def test_day_save_creates_preset_and_assigns(client, png_bytes):
    r = client.post(
        "/ui/day/2026-10-05/save",
        data={"name": "Beef Tacos", "description": "Minced beef"},
        files={"image": ("t.png", png_bytes, "image/png")},
    )
    assert r.status_code == 200
    assert r.headers["HX-Retarget"] == "#week-region"
    events = json.loads(r.headers["HX-Trigger"])
    assert events["closeModal"] and "Monday" in events["toast"]["message"]
    assert "Beef Tacos" in r.text
    meal = services.list_meals()[0]
    assert meal["image_path"]

    # Remove from week keeps the preset
    r = client.post("/ui/day/2026-10-05/remove")
    assert "still in your library" in json.loads(r.headers["HX-Trigger"])["toast"]["message"]
    assert services.count_meals() == 1


def test_day_save_validation_rerenders_form(client):
    r = client.post("/ui/day/2026-10-05/save", data={"name": "  "})
    assert r.status_code == 200
    assert "HX-Retarget" not in r.headers
    assert "Please give the meal a name" in r.text


def test_picker_and_select_existing(client):
    meal = services.create_meal("Beef Tacos", "Minced beef")
    r = client.get("/ui/day/2026-10-06/picker?q=taco")
    assert "Beef Tacos" in r.text
    r = client.get(f"/ui/day/2026-10-06/edit?meal_id={meal['id']}")
    assert 'value="Beef Tacos"' in r.text and "Selected from your library" in r.text
    # Save as new creates a variation without touching the original.
    client.post(
        "/ui/day/2026-10-06/save",
        data={"meal_id": str(meal["id"]), "name": "Spicy Tacos", "description": "Hot", "save_as_new": "1"},
    )
    names = sorted(m["name"] for m in services.list_meals())
    assert names == ["Beef Tacos", "Spicy Tacos"]


def test_ui_swap_random_copy_clear(client):
    a = services.create_meal("A")
    services.create_meal("B")
    services.assign(date(2026, 10, 5), a["id"])
    r = client.post("/ui/schedule/swap", data={"from_date": "2026-10-05", "to_date": "2026-10-07"})
    assert r.status_code == 200
    assert services.get_assignment(date(2026, 10, 7))["name"] == "A"

    r = client.post("/ui/day/2026-10-08/random")
    assert "Random pick" in json.loads(r.headers["HX-Trigger"])["toast"]["message"]

    r = client.post("/ui/week/copy-last", data={"start": "2026-10-11"})
    assert "Copied 2 meals" in json.loads(r.headers["HX-Trigger"])["toast"]["message"]
    r = client.post("/ui/week/clear", data={"start": "2026-10-11"})
    assert "Week cleared" in json.loads(r.headers["HX-Trigger"])["toast"]["message"]
    assert services.count_meals() == 2


def test_library_flow(client):
    r = client.get("/ui/library?week=2026-10-04")
    assert "No saved meals yet" in r.text
    r = client.post("/ui/library/save", data={"week": "2026-10-04", "name": "Pasta", "description": "Tomato"})
    assert "Pasta" in r.text
    meal = services.list_meals()[0]
    r = client.post(f"/ui/library/{meal['id']}/duplicate", data={"week": "2026-10-04"})
    assert "Pasta (copy)" in r.text
    r = client.delete(f"/ui/library/{meal['id']}?week=2026-10-04")
    assert "deleted permanently" in json.loads(r.headers["HX-Trigger"])["toast"]["message"]
    assert [m["name"] for m in services.list_meals()] == ["Pasta (copy)"]


def test_settings_ui(client):
    assert "Home Assistant Webhook URL" in client.get("/ui/settings").text
    r = client.put(
        "/ui/settings",
        data={"home_assistant_webhook_url": "nope", "notification_time": "17:00", "timezone": "America/New_York"},
    )
    assert "Enter a full URL" in r.text
    r = client.put(
        "/ui/settings",
        data={
            "home_assistant_webhook_url": "http://ha:8123/api/webhook/meal_plan_dinner",
            "notification_time": "17:30",
            "timezone": "Europe/London",
            "notification_enabled": "1",
        },
    )
    s = services.get_settings()
    assert s["timezone"] == "Europe/London" and s["notification_time"] == "17:30"
    assert s["notify_only_if_scheduled"] is False
