"""SQLite connection handling and schema."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from . import config

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    image_path  TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_meals_name ON meals (name COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS weekly_schedule (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    date       TEXT NOT NULL UNIQUE,
    meal_id    INTEGER NOT NULL REFERENCES meals (id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_schedule_meal ON weekly_schedule (meal_id);

CREATE TABLE IF NOT EXISTS settings (
    id                         INTEGER PRIMARY KEY CHECK (id = 1),
    home_assistant_webhook_url TEXT NOT NULL DEFAULT '',
    notification_enabled       INTEGER NOT NULL DEFAULT 1,
    notification_time          TEXT NOT NULL DEFAULT '17:00',
    timezone                   TEXT NOT NULL DEFAULT 'America/New_York',
    notify_only_if_scheduled   INTEGER NOT NULL DEFAULT 1,
    last_reminder_key          TEXT
);

CREATE TABLE IF NOT EXISTS webhook_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,
    kind            TEXT NOT NULL,
    meal_id         INTEGER REFERENCES meals (id) ON DELETE SET NULL,
    meal_name       TEXT,
    payload         TEXT NOT NULL,
    response_status INTEGER,
    success         INTEGER NOT NULL,
    error           TEXT
);
"""


def utcnow() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Open a connection, commit on success, roll back on error."""
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    config.ensure_dirs()
    with connect() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT OR IGNORE INTO settings (id, timezone) VALUES (1, ?)",
            (config.DEFAULT_TIMEZONE,),
        )
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
