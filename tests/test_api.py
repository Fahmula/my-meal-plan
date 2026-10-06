from datetime import date

from app import config


def make_meal(client, name="Beef Tacos", description="Minced beef, tortillas, cheese, lettuce and fresh toppings"):
    r = client.post("/api/meals", json={"name": name, "description": description})
    assert r.status_code == 201, r.text
    return r.json()


def test_meal_crud_and_search(client):
    tacos = make_meal(client)
    assert tacos["id"] and tacos["created_at"] and tacos["updated_at"]
    make_meal(client, "Salmon & Veggies", "Baked salmon")

    assert [m["name"] for m in client.get("/api/meals").json()] == ["Beef Tacos", "Salmon & Veggies"]
    assert [m["name"] for m in client.get("/api/meals?q=taco").json()] == ["Beef Tacos"]

    r = client.put(f"/api/meals/{tacos['id']}", json={"name": "Chicken Tacos", "description": "x"})
    assert r.json()["name"] == "Chicken Tacos"

    assert client.post("/api/meals", json={"name": "   "}).status_code == 422
    assert client.get("/api/meals/9999").status_code == 404
    assert client.delete(f"/api/meals/{tacos['id']}").json()["deleted"] is True
    assert client.get(f"/api/meals/{tacos['id']}").status_code == 404


def test_removing_from_week_keeps_preset(client):
    tacos = make_meal(client)
    assert client.put("/api/schedule/2026-10-05", json={"meal_id": tacos["id"]}).status_code == 200
    week = client.get("/api/schedule?start=2026-10-05").json()
    assert week["start"] == "2026-10-04"  # Sunday
    assert [d["day"] for d in week["days"]][0] == "Sunday"
    assert week["days"][1]["meal"]["name"] == "Beef Tacos"

    r = client.delete("/api/schedule/2026-10-05")
    assert r.json()["removed"] is True
    assert client.get("/api/schedule?start=2026-10-05").json()["days"][1]["meal"] is None
    # Preset survives and can be reused months later.
    assert client.get(f"/api/meals/{tacos['id']}").status_code == 200
    client.put("/api/schedule/2027-01-12", json={"meal_id": tacos["id"]})
    client.put("/api/schedule/2027-01-13", json={"meal_id": tacos["id"]})
    days = client.get("/api/schedule?start=2027-01-12").json()["days"]
    assert sum(1 for d in days if d["meal"]) == 2


def test_swap_and_move(client):
    tacos = make_meal(client)
    salmon = make_meal(client, "Salmon & Veggies", "")
    client.put("/api/schedule/2026-10-05", json={"meal_id": tacos["id"]})  # Monday
    client.put("/api/schedule/2026-10-06", json={"meal_id": salmon["id"]})  # Tuesday

    r = client.post("/api/schedule/swap", json={"from_date": "2026-10-05", "to_date": "2026-10-06"})
    assert r.json()["result"] == "swapped"
    days = client.get("/api/schedule?start=2026-10-04").json()["days"]
    assert days[1]["meal"]["name"] == "Salmon & Veggies"
    assert days[2]["meal"]["name"] == "Beef Tacos"

    r = client.post("/api/schedule/swap", json={"from_date": "2026-10-06", "to_date": "2026-10-08"})
    assert r.json()["result"] == "moved"
    days = client.get("/api/schedule?start=2026-10-04").json()["days"]
    assert days[2]["meal"] is None
    assert days[4]["meal"]["name"] == "Beef Tacos"


def test_weeks_are_independent_and_copy_clear(client):
    tacos = make_meal(client)
    client.put("/api/schedule/2026-10-05", json={"meal_id": tacos["id"]})
    client.put("/api/schedule/2026-10-15", json={"meal_id": tacos["id"]})  # next week Thursday

    r = client.post("/api/schedule/copy-last-week", json={"start": "2026-10-11"})
    assert r.json()["copied"] == 1
    days = r.json()["days"]
    assert days[1]["meal"]["name"] == "Beef Tacos"  # Monday copied
    assert days[4]["meal"] is None  # replaced, since last week's Thursday was empty

    r = client.post("/api/schedule/clear-week", json={"start": "2026-10-11"})
    assert r.json()["removed"] == 1
    # Previous week untouched, preset untouched.
    assert client.get("/api/schedule?start=2026-10-04").json()["days"][1]["meal"]["name"] == "Beef Tacos"
    assert len(client.get("/api/meals").json()) == 1


def test_delete_preset_removes_its_assignments(client):
    tacos = make_meal(client)
    client.put("/api/schedule/2026-10-05", json={"meal_id": tacos["id"]})
    client.delete(f"/api/meals/{tacos['id']}")
    assert client.get("/api/schedule?start=2026-10-05").json()["days"][1]["meal"] is None


def test_image_upload_and_duplicate(client, png_bytes):
    tacos = make_meal(client)
    r = client.post(f"/api/meals/{tacos['id']}/image", files={"image": ("t.png", png_bytes, "image/png")})
    assert r.status_code == 200, r.text
    meal = r.json()
    assert meal["image_path"].endswith(".webp")
    assert (config.UPLOAD_DIR / meal["image_path"]).exists()
    assert client.get(meal["image_url"]).status_code == 200

    copy = client.post(f"/api/meals/{tacos['id']}/duplicate").json()
    assert copy["name"] == "Beef Tacos (copy)"
    assert copy["image_path"] and copy["image_path"] != meal["image_path"]

    bad = client.post(f"/api/meals/{tacos['id']}/image", files={"image": ("x.png", b"not an image", "image/png")})
    assert bad.status_code == 422

    client.delete(f"/api/meals/{tacos['id']}")
    assert not (config.UPLOAD_DIR / meal["image_path"]).exists()
    assert (config.UPLOAD_DIR / copy["image_path"]).exists()


def test_settings_validation(client):
    s = client.get("/api/settings").json()
    assert s["timezone"] == "America/New_York"
    assert s["notification_time"] == "17:00"
    assert s["notification_enabled"] is True
    assert s["notify_only_if_scheduled"] is True

    r = client.put("/api/settings", json={"home_assistant_webhook_url": "not a url"})
    assert r.status_code == 422
    r = client.put("/api/settings", json={"notification_time": "25:00"})
    assert r.status_code == 422
    r = client.put("/api/settings", json={"timezone": "Mars/Base"})
    assert r.status_code == 422

    r = client.put(
        "/api/settings",
        json={
            "home_assistant_webhook_url": "http://ha.local:8123/api/webhook/meal_plan_dinner",
            "notification_time": "18:30",
        },
    )
    assert r.status_code == 200
    assert r.json()["notification_time"] == "18:30"
    assert r.json()["next_reminder"]


def test_bad_dates_rejected(client):
    assert client.put("/api/schedule/2026-13-40", json={"meal_id": 1}).status_code == 422
    assert client.put("/api/schedule/2026-10-05", json={"meal_id": 999}).status_code == 404


def test_today_endpoint(client):
    r = client.get("/api/schedule/today").json()
    assert date.fromisoformat(r["date"])
