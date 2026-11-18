from __future__ import annotations

import os
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from . import security

BASE_DIR = Path(__file__).resolve().parent.parent
_db_env = os.environ.get("DUTY_DB", "duty.db")
DB_PATH = Path(_db_env).expanduser()
if not DB_PATH.is_absolute():
    DB_PATH = (BASE_DIR / DB_PATH).resolve()

SCHEMA = """
CREATE TABLE IF NOT EXISTS people (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    email TEXT NOT NULL DEFAULT '',
    rocketchat TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'employee'
        CHECK (role IN ('admin','teamlead','employee')),
    person_id INTEGER REFERENCES people(id) ON DELETE SET NULL,
    email TEXT NOT NULL DEFAULT '',
    rocketchat TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    session_epoch INTEGER NOT NULL DEFAULT 0,
    last_login_at TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_users_person
    ON users(person_id) WHERE person_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS coverage_reviews (
    date TEXT PRIMARY KEY,
    note TEXT NOT NULL DEFAULT '',
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS coverage_alerts (
    date TEXT PRIMARY KEY,
    sent_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS coverage_overrides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    reason TEXT NOT NULL,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS ix_overrides_date ON coverage_overrides(date);

CREATE TABLE IF NOT EXISTS notification_outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT NOT NULL CHECK (channel IN ('email','rocketchat')),
    recipient TEXT NOT NULL,
    subject TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL,
    event TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','sent','error','skipped')),
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    sent_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_outbox_status ON notification_outbox(status, id);

CREATE TABLE IF NOT EXISTS duties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE RESTRICT,
    status TEXT NOT NULL DEFAULT 'planned'
        CHECK (status IN ('planned','done','missed','cancelled')),
    source TEXT NOT NULL DEFAULT 'manual'
        CHECK (source IN ('manual','auto','draw')),
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_duties_active_date
    ON duties(date) WHERE status <> 'cancelled';
CREATE INDEX IF NOT EXISTS ix_duties_person ON duties(person_id, date);

CREATE TABLE IF NOT EXISTS absences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    date_from TEXT NOT NULL,
    date_to TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'vacation'
        CHECK (kind IN ('vacation','sick','trip','other')),
    note TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_absences_person
    ON absences(person_id, date_from, date_to);

CREATE TABLE IF NOT EXISTS comp_choices (
    duty_id INTEGER PRIMARY KEY REFERENCES duties(id) ON DELETE CASCADE,
    date TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','scheduled','used','declined')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS holidays (
    date TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS availability (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    date_from TEXT NOT NULL,
    date_to TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'unavailable'
        CHECK (kind IN ('unavailable','preferred')),
    reason TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','approved','declined')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    decided_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_availability_person
    ON availability(person_id, date_from, date_to);
CREATE INDEX IF NOT EXISTS ix_availability_status ON availability(status);

CREATE TABLE IF NOT EXISTS absence_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    date_from TEXT NOT NULL,
    date_to TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'vacation'
        CHECK (kind IN ('vacation','trip')),
    reason TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','approved','declined')),
    absence_id INTEGER REFERENCES absences(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    decided_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_absence_requests_person
    ON absence_requests(person_id, date_from, date_to);
CREATE INDEX IF NOT EXISTS ix_absence_requests_status ON absence_requests(status);

CREATE TABLE IF NOT EXISTS draws (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    seed INTEGER NOT NULL,
    winner_id INTEGER NOT NULL REFERENCES people(id) ON DELETE RESTRICT,
    candidates TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'load',
    roll REAL,
    proof TEXT,
    proof_hash TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS ix_draws_date ON draws(date);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

DEFAULT_SETTINGS: dict[str, str] = {
    "unit_name": "Дежурная служба",
    "rest_days": "1",
    "min_gap_days": "2",
    "weekend_weight": "1.5",
    "fairness_power": "2",
    "comp_enabled": "1",
    "comp_valid_days": "60",
    "history_days": "0",
    "request_month_limit": "10",
    "request_horizon_days": "90",
    "notifications_enabled": "0",
    "notify_on_request": "1",
    "notify_on_decision": "1",
    "notify_on_coverage": "1",
    "smtp_host": "",
    "smtp_port": "587",
    "smtp_user": "",
    "smtp_password": "",
    "smtp_from": "",
    "smtp_tls": "1",
    "rocketchat_webhook": "",
    "public_url": "http://127.0.0.1:8000",
}

SETTINGS_SPEC: dict[str, tuple[str, float, float]] = {
    "rest_days": ("int", 0, 7),
    "min_gap_days": ("int", 1, 30),
    "weekend_weight": ("float", 1.0, 3.0),
    "fairness_power": ("int", 1, 4),
    "comp_enabled": ("int", 0, 1),
    "comp_valid_days": ("int", 1, 365),
    "history_days": ("int", 0, 3650),
    "request_month_limit": ("int", 0, 31),
    "request_horizon_days": ("int", 1, 365),
    "notifications_enabled": ("int", 0, 1),
    "notify_on_request": ("int", 0, 1),
    "notify_on_decision": ("int", 0, 1),
    "notify_on_coverage": ("int", 0, 1),
    "smtp_port": ("int", 1, 65535),
    "smtp_tls": ("int", 0, 1),
}


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=15, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 15000")
    return conn


@contextmanager
def db():
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def transaction(conn: sqlite3.Connection):
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    else:
        conn.execute("COMMIT")


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with db() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(people)")}
        if "email" not in columns:
            conn.execute("ALTER TABLE people ADD COLUMN email TEXT NOT NULL DEFAULT ''")
        if "rocketchat" not in columns:
            conn.execute(
                "ALTER TABLE people ADD COLUMN rocketchat TEXT NOT NULL DEFAULT ''"
            )
        if "token" in columns:
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_people_token "
                "ON people(token) WHERE token IS NOT NULL"
            )
        user_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(users)")
        }
        if "session_epoch" not in user_columns:
            conn.execute(
                "ALTER TABLE users ADD COLUMN session_epoch INTEGER NOT NULL DEFAULT 0"
            )
        draw_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(draws)")
        }
        if "mode" not in draw_columns:
            conn.execute(
                "ALTER TABLE draws ADD COLUMN mode TEXT NOT NULL DEFAULT 'load'"
            )
        if "roll" not in draw_columns:
            conn.execute("ALTER TABLE draws ADD COLUMN roll REAL")
        if "proof" not in draw_columns:
            conn.execute("ALTER TABLE draws ADD COLUMN proof TEXT")
        if "proof_hash" not in draw_columns:
            conn.execute("ALTER TABLE draws ADD COLUMN proof_hash TEXT")
        for key, value in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)",
                (key, value),
            )
        if conn.execute(
            "SELECT 1 FROM settings WHERE key = 'session_secret'"
        ).fetchone() is None:
            conn.execute(
                "INSERT INTO settings(key, value) VALUES('session_secret', ?)",
                (secrets.token_urlsafe(48),),
            )
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            username = os.environ.get("DUTY_ADMIN_USER", "admin").strip() or "admin"
            password = os.environ.get("DUTY_ADMIN_PASSWORD", "").strip()
            generated = not password
            if generated:
                password = secrets.token_urlsafe(9)
            conn.execute(
                "INSERT INTO users(username, password_hash, role) VALUES(?, ?, 'admin')",
                (username, security.hash_password(password)),
            )
            if generated:
                print(
                    f"Создан администратор «{username}», пароль: {password}. "
                    "Смените его после входа.",
                    flush=True,
                )


def load_settings(conn: sqlite3.Connection) -> dict[str, str]:
    result = dict(DEFAULT_SETTINGS)
    for row in conn.execute("SELECT key, value FROM settings"):
        result[row["key"]] = row["value"]
    return result


def save_settings(conn: sqlite3.Connection, values: dict[str, str]) -> dict[str, str]:
    with transaction(conn):
        for key, value in values.items():
            conn.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
    return load_settings(conn)
