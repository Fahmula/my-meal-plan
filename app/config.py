"""Runtime configuration, read from environment variables."""

import os
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent

DATA_DIR = Path(os.environ.get("DATA_DIR", APP_DIR.parent / "data")).resolve()
DB_PATH = Path(os.environ.get("DB_PATH", DATA_DIR / "meal-plan.db"))
UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", DATA_DIR / "uploads"))

# Initial timezone used the very first time the settings row is created.
DEFAULT_TIMEZONE = os.environ.get("DEFAULT_TIMEZONE", "America/New_York")

# Optional public URL of this app (e.g. http://192.168.1.20:3000). When set,
# webhook payloads include an absolute image_url Home Assistant can display.
APP_BASE_URL = os.environ.get("APP_BASE_URL", "").rstrip("/")

# Turn off the background reminder loop (useful for tests / extra replicas).
SCHEDULER_ENABLED = os.environ.get("SCHEDULER_ENABLED", "true").lower() not in ("0", "false", "no")

MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_MB", "15")) * 1024 * 1024


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
