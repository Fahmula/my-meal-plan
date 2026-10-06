# My Meal Plan

*A simple plan for a delicious week.*

A small, self-hosted web app for planning your family's dinners from **Sunday to Saturday**.
Reusable meal presets, drag-and-drop scheduling that works on phones, independent schedules
for every week, and a daily **Home Assistant** webhook so your phone can tell you what's for dinner.

**Stack:** Python 3 · FastAPI · Jinja2 · htmx · Tailwind CSS 4 + daisyUI 5 · SortableJS · SQLite · Docker

*Built with the help of AI (Claude by Anthropic).*

---

## Features

- **Weekly dashboard:** seven pastel day cards (Sun–Sat) with photo, meal name and description.
- **Meal Library (presets):** meals are stored separately from the calendar. Removing a meal from
  a day never deletes the preset; pick it again weeks later and the name, description and
  photo come back. Add, edit, duplicate, search, plan or permanently delete meals.
- **Drag and drop:** drag a meal onto another day to **swap** the two, or onto an empty day to
  **move** it. Works with mouse and touch (long-press on phones). The UI updates instantly and the
  change is saved straight away.
- **Week navigation:** previous / next week and *This Week*. Every week has its own schedule.
- **Quick assignment:** searchable meal picker in the day editor, plus **+ Create New Meal**.
- **Extras:** Copy Last Week, Clear Week, *Surprise me* (random meal on an empty day),
  Duplicate Meal.
- **Home Assistant:** the server POSTs tonight's dinner to your webhook at the reminder time
  you choose. No browser has to stay open. Includes a test button and webhook history.
- **Images:** phone photos are auto-rotated, resized and stored as WebP in the data volume.
- **Persistence:** SQLite plus images in a single `/data` volume that survives container updates.

---

## Quick start (Docker Compose)

Prerequisites: Docker with the Compose plugin on your home server.

```bash
git clone <this repo> my-meal-plan
```

```bash
cd my-meal-plan
```

```bash
cp .env.example .env
```

Edit `.env` if you want a different port, data folder or user (see [Configuration](#configuration)).

**Option A: use the prebuilt image.** GitHub Actions builds `ghcr.io/fahmula/my-meal-plan:latest`
on every push to `main`. The repository is private, so the image is too: log in once with a GitHub
personal access token (classic) that has the `read:packages` scope:

```bash
echo YOUR_TOKEN | docker login ghcr.io -u fahmula --password-stdin
```

```bash
docker compose pull
```

```bash
docker compose up -d
```

**Option B: build on the server.**

```bash
docker compose up -d --build
```

Open **http://YOUR-SERVER-IP:3000** (or whichever `APP_PORT` you chose).

Useful commands:

```bash
docker compose logs -f
```

```bash
docker compose ps
```

```bash
docker compose down
```

### Updating

With the prebuilt image:

```bash
docker compose pull && docker compose up -d
```

When building from source:

```bash
git pull && docker compose up -d --build
```

Your meals, schedules, settings and images live in `./data` (or your `DATA_PATH`) on the
host, so rebuilding or recreating the container never touches them.

### Backups

Everything is in the data folder:

```
data/
├── meal-plan.db      # SQLite database (meals, schedules, settings, webhook history)
└── uploads/          # meal photos (.webp)
```

Back up that folder (ideally while the container is stopped, or with `sqlite3 data/meal-plan.db ".backup backup.db"`).

---

## Unraid

An Unraid template lives in [`unraid/my-meal-plan.xml`](unraid/my-meal-plan.xml). It uses the
prebuilt image, stores data in `/mnt/user/appdata/my-meal-plan` and runs as `nobody:users` (99:100).

**1. Make the image pullable.** The repository is private, so its image is private too. The easiest
fix is to make the *package* public (the source code stays private): on GitHub open
**Packages → my-meal-plan → Package settings → Change visibility → Public**.

> If you'd rather keep it private, you have to run `docker login ghcr.io` on Unraid (with a token
> that has `read:packages`). Unraid keeps `/root` in RAM, so that login is lost on every reboot
> and updates will fail until you log in again.

**2. Add the template.** Open the Unraid terminal (the `>_` icon top right) and run:

```bash
curl -fsSL -o /boot/config/plugins/dockerMan/templates-user/my-my-meal-plan.xml https://raw.githubusercontent.com/Fahmula/my-meal-plan/main/unraid/my-meal-plan.xml
```

While the repository is private that URL needs authentication. Instead, copy
`unraid/my-meal-plan.xml` to the flash share as
`\\TOWER\flash\config\plugins\dockerMan\templates-user\my-my-meal-plan.xml`
(user templates must start with `my-`).

**3. Install.** Go to **Docker → Add Container**, choose **my-meal-plan** from the
**Template** dropdown, check the port and Data path, and click **Apply**. Open it with
**WebUI** from the container's menu on the Docker tab.

**Icon.** Unraid downloads the icon from GitHub, which doesn't work while the repository is
private. To get the icon anyway, copy `unraid/icon.png` to
`\\TOWER\flash\config\plugins\dockerMan\images\my-meal-plan-icon.png`.

**Updates.** Every push to `main` publishes a new `:latest`. Click **Check for Updates** on the
Docker tab, then **apply update**. Your data in appdata is kept.

---

## Configuration

All options go in `.env` (read automatically by Docker Compose):

| Variable           | Default            | Description |
|--------------------|--------------------|-------------|
| `APP_PORT`         | `3000`             | Host port for the web UI (`APP_PORT:3000`). |
| `DATA_PATH`        | `./data`           | Host folder for the database and images. |
| `PUID` / `PGID`    | `1000` / `1000`    | User/group that owns files in `DATA_PATH` (run `id` on the host). The container drops root privileges to this user. |
| `TZ`               | `America/New_York` | Container clock (log timestamps). |
| `DEFAULT_TIMEZONE` | `America/New_York` | Initial app timezone on first start. Change it later in **Settings**. |
| `APP_BASE_URL`     | *(empty)*          | Optional URL you use to open the app, e.g. `http://192.168.1.20:3000`. When set, webhooks include an `image_url` Home Assistant can attach to the notification. |
| `LOG_LEVEL`        | `info`             | `debug`, `info`, `warning` or `error`. |

The reminder time, timezone and webhook URL are set in the app under **Settings**. Nothing about
your Home Assistant is hard-coded.

> There is no login. The app is meant for your home network. Don't expose it directly to the
> internet; put it behind a VPN or an authenticating reverse proxy if you need remote access.

---

## Home Assistant integration

Every day at the **Dinner Reminder Time** (in the app's timezone) the backend looks up today's
dinner and sends an HTTP `POST` to your Home Assistant webhook:

```json
{
  "event": "dinner_reminder",
  "date": "2026-10-05",
  "day": "Monday",
  "meal_id": "1",
  "meal_name": "Beef Tacos",
  "description": "Minced beef, tortillas, cheese, lettuce and fresh toppings"
}
```

- `image_url` is added when `APP_BASE_URL` is set and the meal has a photo.
- **Send Test Notification** sends the same payload with `"test": true` (using today's meal, or a
  sample message if nothing is planned).
- With **Notify only if a meal is scheduled** turned off, empty days send
  `"meal_name": "No meal planned"` and `"meal_id": null`.
- Each reminder is sent once per day. Failed requests are retried twice, and every attempt shows
  up in **Settings → Webhook history** (time, meal, success/failed, HTTP code).
- If the server was down at reminder time, it still sends when it comes back within 30 minutes.

### 1. Create the automation in Home Assistant

In Home Assistant go to **Settings → Automations & scenes → Create automation → Create new
automation**, open the **⋮ menu → Edit in YAML**, paste the following, and replace
`notify.mobile_app_your_phone` with your phone's notify action (find it under
**Developer tools → Actions**, search for `notify.mobile_app`):

```yaml
alias: Dinner Tonight notification
description: Sent by My Meal Plan at the dinner reminder time
mode: queued
triggers:
  - trigger: webhook
    webhook_id: meal_plan_dinner
    allowed_methods:
      - POST
    local_only: true
conditions:
  - condition: template
    value_template: "{{ trigger.json.event == 'dinner_reminder' }}"
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: Dinner Tonight
      message: |-
        {{ trigger.json.meal_name }}
        {{ trigger.json.description }}
```

Save it. On your phone the notification will read:

> **Dinner Tonight**
> Beef Tacos
> Minced beef, tortillas, cheese, lettuce and fresh toppings

**Optional: show the meal photo.** Set `APP_BASE_URL` in `.env`, restart the container, and add
this under the notify action's `data:` (the phone must be able to reach that URL):

```yaml
      data:
        image: "{{ trigger.json.image_url }}"
```

**Optional: notify several phones.** Add one `notify.mobile_app_…` action per phone, or use a
notify group.

### 2. Point My Meal Plan at the webhook

In the app open **Settings** and enter:

- **Home Assistant Webhook URL:** `http://HOME-ASSISTANT-IP:8123/api/webhook/meal_plan_dinner`
  (the last part must match `webhook_id` above)
- **Dinner Reminder Time:** e.g. `5:00 PM`
- **Timezone:** e.g. `America/New_York`
- **Dinner Reminder Enabled:** on

Press **Save Settings**, then **Send Test Notification**. You should see *Test sent
successfully · HTTP 200* and get a notification on your phone.

### Troubleshooting

- **Use an IP address**, not `homeassistant.local`. mDNS names usually don't resolve inside
  Docker containers.
- **HTTP 200 but no notification:** check the automation's trace in Home Assistant, and that the
  notify action name is right. Home Assistant answers webhooks with 200 even when no automation
  matches, so a typo in the `webhook_id` also looks "successful".
- **Connection refused / timeout:** make sure the server running My Meal Plan can reach port
  8123 on Home Assistant (`curl http://HA-IP:8123` from the Docker host).
- **`local_only: true`** only accepts requests from your local network. If you call Home Assistant
  through a public URL (e.g. Nabu Casa), set it to `false` and use a long random `webhook_id`.
- **Wrong reminder time?** Check the timezone in Settings. The *Next reminder* line shows when the
  next webhook will go out.

---

## Using the app

| I want to… | How |
|---|---|
| Plan a dinner | Tap the **›** arrow (or **+ Add Meal**) on a day, search your library or fill in a new meal, **Save**. |
| Reuse a saved meal | In the day editor, search (e.g. "taco") and tap the result, then **Save**. |
| Move / swap days | Drag a meal onto another day. On phones, press and hold for a moment, then drag. |
| Take a meal off a day | Open the day → **Remove From Week**. The meal stays in your library. |
| Delete a meal forever | **Meal Library** → trash icon → confirm. This also clears it from any planned days. |
| Make a variation | **Meal Library** → duplicate icon, or tick *Save as a new meal instead* in the day editor. |
| Plan from the library | **Meal Library** → **Plan** → pick a day of the week you're viewing. |
| Plan a future week | **Next Week ›**, then plan as usual, or **⋯ → Copy Last Week**. |

---

## REST API

JSON API used by the UI and available for your own scripts. Interactive docs are at
`/api/docs`.

| Method & path | Description |
|---|---|
| `GET /api/meals?q=` | List / search meal presets |
| `POST /api/meals` | Create `{name, description}` |
| `GET /api/meals/{id}` | Get one meal |
| `PUT /api/meals/{id}` | Update `{name, description}` |
| `DELETE /api/meals/{id}` | Permanently delete a preset (and its planned days) |
| `POST /api/meals/{id}/duplicate` | Duplicate a preset (image included) |
| `POST /api/meals/{id}/image` | Upload image (multipart field `image`) |
| `DELETE /api/meals/{id}/image` | Remove image |
| `GET /api/schedule?start=YYYY-MM-DD` | The Sunday–Saturday week containing `start` (defaults to this week) |
| `GET /api/schedule/today` | Today's dinner |
| `PUT /api/schedule/{date}` | Assign `{meal_id}` to a date |
| `DELETE /api/schedule/{date}` | Remove the meal from a date (preset is kept) |
| `POST /api/schedule/swap` | `{from_date, to_date}`: swap, or move if one side is empty |
| `POST /api/schedule/copy-last-week` | `{start}`: replace that week with the previous week's plan |
| `POST /api/schedule/clear-week` | `{start}`: empty that week (presets are kept) |
| `GET /api/settings` / `PUT /api/settings` | Read / update settings (partial updates allowed) |
| `POST /api/home-assistant/test` | Send a test webhook (optional body `{url}`) |
| `GET /api/webhook-logs?limit=50` | Webhook history |
| `GET /api/health` | Health check |

Invalid input returns `422` with a `detail` message; unknown IDs return `404`.

---

## Development

```bash
uv venv .venv && uv pip install --python .venv/bin/python -r requirements-dev.txt
```

```bash
.venv/bin/uvicorn app.main:app --reload --port 3000
```

```bash
.venv/bin/python -m pytest
```

```bash
.venv/bin/ruff check app tests && .venv/bin/ruff format --check app tests
```

### CI

`.github/workflows/ci.yml` runs ruff and the test suite on pushes to `main`/`dev` and on pull
requests. On `main` (push or **Run workflow**) it also builds the Docker image and publishes
`ghcr.io/fahmula/my-meal-plan:latest` and `:sha-<commit>`.

Data goes to `./data` by default (`DATA_DIR` overrides it).

### Styles

The compiled stylesheet `app/static/css/app.css` is committed, so Docker builds need neither
Node.js nor internet access for assets. After changing templates or `app/static/src/app.css`,
rebuild it with the standalone Tailwind CLI. The script downloads Tailwind and daisyUI into
`.tools/` the first time:

```bash
./scripts/build-css.sh
```

Add `--watch` to rebuild on every change.

### Project layout

```
app/
├── main.py            # FastAPI app, static mounts, starts the reminder scheduler
├── api.py             # JSON REST API (/api/…)
├── ui.py              # HTML pages + htmx fragments (/ui/…)
├── services.py        # meals, schedule, settings, webhook-log data access
├── notifier.py        # Home Assistant webhook + daily scheduler loop
├── images.py          # upload validation, EXIF rotation, resize → WebP
├── db.py, dates.py, config.py
├── templates/         # Jinja2 templates (index + partials)
└── static/            # app.js, compiled CSS, vendored htmx/SortableJS, fonts
tests/                 # pytest suite (API, UI fragments, scheduler)
Dockerfile, docker-compose.yml, docker-entrypoint.sh, .env.example
```

The app runs as a **single process on purpose**: the reminder scheduler lives inside it. Don't
run multiple workers or replicas against the same data folder (or set `SCHEDULER_ENABLED=false`
on the extras).
