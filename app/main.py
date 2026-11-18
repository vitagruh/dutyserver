from __future__ import annotations

import csv
import html
import io
import json
import random
import secrets
import sqlite3
import statistics
import time
from collections import Counter
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import db, engine, notifier, proofs, security, xlsx
from .holidays import belarus_holidays

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"

WEEKDAY_NAMES = (
    "Понедельник", "Вторник", "Среда", "Четверг",
    "Пятница", "Суббота", "Воскресенье",
)
WEEKDAY_SHORT = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
DUTY_STATUS_LABELS = {
    "planned": "Плановое",
    "done": "Выполнено",
    "missed": "Неявка",
    "cancelled": "Отменено",
}
SOURCE_LABELS = {
    "manual": "Вручную",
    "auto": "Автораспределение",
    "draw": "Жребий",
}
ABSENCE_KIND_LABELS = {
    "vacation": "Отпуск",
    "sick": "Болезнь",
    "trip": "Командировка",
    "other": "Другое",
}
COMP_STATUS_LABELS = {
    "pending": "Не оформлен",
    "scheduled": "Запланирован",
    "used": "Использован",
    "declined": "Отказ",
}
REQUEST_KIND_LABELS = {
    "unavailable": "Не может дежурить",
    "preferred": "Предпочитает не дежурить",
}
REQUEST_STATUS_LABELS = {
    "pending": "Ожидает согласования",
    "approved": "Согласована",
    "declined": "Отклонена",
}
ROLE_LABELS = {
    "admin": "Администратор",
    "teamlead": "Тимлид",
    "employee": "Сотрудник",
}
SESSION_COOKIE = "duty_session"
LOGIN_MAX_ATTEMPTS = 10
LOGIN_WINDOW_SECONDS = 300
CSP_HEADER = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; font-src 'self'; connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'none'; form-action 'self'; "
    "object-src 'none'"
)

_login_failures: dict[str, list[float]] = {}


def _login_key(request: Request, username: str) -> str:
    host = request.client.host if request.client else "unknown"
    return f"{host}|{username.strip().lower()}"


def login_retry_after(key: str) -> int:
    now = time.monotonic()
    attempts = [
        stamp
        for stamp in _login_failures.get(key, [])
        if now - stamp < LOGIN_WINDOW_SECONDS
    ]
    if attempts:
        _login_failures[key] = attempts
    else:
        _login_failures.pop(key, None)
    if len(attempts) >= LOGIN_MAX_ATTEMPTS:
        return max(1, int(LOGIN_WINDOW_SECONDS - (now - attempts[0])) + 1)
    return 0


def note_login_failure(key: str) -> None:
    if len(_login_failures) > 1000:
        _login_failures.clear()
    _login_failures.setdefault(key, []).append(time.monotonic())


def reset_login_failures() -> None:
    _login_failures.clear()


def _secure_cookie(request: Request) -> bool:
    return request.url.scheme == "https"


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    ensure_belarus_holidays()
    with db.db() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = 'session_secret'"
        ).fetchone()
    app.state.session_secret = row["value"] if row else ""
    yield
    notifier.flush()


app = FastAPI(title="Суточные дежурства", lifespan=lifespan)


class PersonIn(BaseModel):
    name: str
    note: str = ""
    email: str = ""
    rocketchat: str = ""


class PersonPatch(BaseModel):
    name: str | None = None
    note: str | None = None
    email: str | None = None
    rocketchat: str | None = None
    active: bool | None = None


class DutyIn(BaseModel):
    date: str
    person_id: int
    note: str = ""


class DutyPatch(BaseModel):
    status: str


class DrawIn(BaseModel):
    date: str
    candidate_ids: list[int] = []
    seed: int | None = None
    mode: str = "load"
    relaxed: bool = False
    replace: bool = False


class AutoPlanIn(BaseModel):
    date_from: str
    date_to: str
    seed: int | None = None


class AbsenceIn(BaseModel):
    person_id: int
    date_from: str
    date_to: str
    kind: str = "vacation"
    note: str = ""


class CompIn(BaseModel):
    status: str
    date: str | None = None


class HolidayIn(BaseModel):
    date: str
    name: str = ""


class HolidaySeedIn(BaseModel):
    year: int | None = None


class MyRequestIn(BaseModel):
    dates: list[str]
    kind: str = "unavailable"
    reason: str = ""


class RequestDecisionIn(BaseModel):
    status: str


class SettingsIn(BaseModel):
    unit_name: str | None = None
    rest_days: int | None = None
    min_gap_days: int | None = None
    weekend_weight: float | None = None
    fairness_power: int | None = None
    comp_enabled: bool | None = None
    comp_valid_days: int | None = None
    history_days: int | None = None
    request_month_limit: int | None = None
    request_horizon_days: int | None = None
    notifications_enabled: bool | None = None
    notify_on_request: bool | None = None
    notify_on_decision: bool | None = None
    notify_on_coverage: bool | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_tls: bool | None = None
    rocketchat_webhook: str | None = None
    public_url: str | None = None


class LoginIn(BaseModel):
    username: str
    password: str


class PasswordIn(BaseModel):
    current_password: str
    new_password: str


class UserIn(BaseModel):
    username: str
    password: str
    role: str = "employee"
    person_id: int | None = None
    email: str = ""
    rocketchat: str = ""
    active: bool = True


class UserPatch(BaseModel):
    username: str | None = None
    password: str | None = None
    role: str | None = None
    person_id: int | None = None
    email: str | None = None
    rocketchat: str | None = None
    active: bool | None = None


class CoverageDismissIn(BaseModel):
    note: str = ""


class CoverageAssignIn(BaseModel):
    person_id: int
    reason: str


class TestNotificationIn(BaseModel):
    channel: str = "email"


def today() -> date:
    return date.today()


def _seeded_years(conn: sqlite3.Connection) -> set[int]:
    row = conn.execute(
        "SELECT value FROM settings WHERE key = 'holidays_seeded_years'"
    ).fetchone()
    raw = row["value"] if row else ""
    return {int(part) for part in raw.split(",") if part.strip().isdigit()}


def _record_seeded_year(conn: sqlite3.Connection, year: int) -> None:
    years = _seeded_years(conn)
    if year in years:
        return
    years.add(year)
    conn.execute(
        "INSERT INTO settings(key, value) VALUES('holidays_seeded_years', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (",".join(str(item) for item in sorted(years)),),
    )


def ensure_belarus_holidays(back: int = 1, forward: int = 1) -> None:
    """Догружает праздники РБ один раз на год, не возвращая удалённые даты."""
    current = today().year
    years = range(current - back, current + forward + 1)
    with db.db() as conn:
        done = _seeded_years(conn)
        pending = [year for year in years if year not in done]
        if not pending:
            return
        with db.transaction(conn):
            for year in pending:
                for day, name in belarus_holidays(year):
                    conn.execute(
                        "INSERT OR IGNORE INTO holidays(date, name) VALUES(?, ?)",
                        (day.isoformat(), name),
                    )
                _record_seeded_year(conn, year)


def parse_day(value: str, field: str = "дата") -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"Некорректная {field}: {value}")


def month_bounds(month: str) -> tuple[date, date]:
    try:
        year_s, month_s = month.split("-")
        year, month = int(year_s), int(month_s)
        if month < 1 or month > 12:
            raise ValueError
        start = date(year, month, 1)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Месяц должен быть в формате ГГГГ-ММ")
    next_start = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, next_start


def settings_out(settings: dict[str, str]) -> dict[str, Any]:
    rules = engine.Rules.from_settings(settings)
    return {
        "unit_name": settings.get("unit_name", "Дежурная служба"),
        "rest_days": rules.rest_days,
        "min_gap_days": rules.min_gap_days,
        "weekend_weight": rules.weekend_weight,
        "fairness_power": rules.fairness_power,
        "comp_enabled": rules.comp_enabled,
        "comp_valid_days": rules.comp_valid_days,
        "history_days": rules.history_days,
        "request_month_limit": int(settings.get("request_month_limit", 10)),
        "request_horizon_days": int(settings.get("request_horizon_days", 90)),
        "notifications_enabled": settings.get("notifications_enabled", "0") == "1",
        "notify_on_request": settings.get("notify_on_request", "1") == "1",
        "notify_on_decision": settings.get("notify_on_decision", "1") == "1",
        "notify_on_coverage": settings.get("notify_on_coverage", "1") == "1",
        "smtp_host": settings.get("smtp_host", ""),
        "smtp_port": int(settings.get("smtp_port", 587)),
        "smtp_user": settings.get("smtp_user", ""),
        "smtp_from": settings.get("smtp_from", ""),
        "smtp_tls": settings.get("smtp_tls", "1") == "1",
        "smtp_password_set": bool(settings.get("smtp_password", "")),
        "rocketchat_webhook": settings.get("rocketchat_webhook", ""),
        "public_url": settings.get("public_url", "http://127.0.0.1:8000"),
    }


def load_people(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(
            "SELECT id, name, note, active, email, rocketchat FROM people "
            "ORDER BY name COLLATE NOCASE"
        )
    ]


def load_duties(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute("SELECT * FROM duties")]


def month_duty_counts(
    duties: list[dict[str, Any]], target: date
) -> Counter[int]:
    counts: Counter[int] = Counter()
    for duty in duties:
        if not engine.is_active_duty(duty):
            continue
        duty_date = engine.as_date(duty["date"])
        if duty_date.year == target.year and duty_date.month == target.month:
            counts[int(duty["person_id"])] += 1
    return counts


def load_absences(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(
            "SELECT a.*, p.name AS person_name FROM absences a "
            "JOIN people p ON p.id = a.person_id ORDER BY a.date_from DESC"
        )
    ]


def load_availability(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(
            "SELECT r.*, p.name AS person_name, p.active AS person_active "
            "FROM availability r JOIN people p ON p.id = r.person_id "
            "ORDER BY r.date_from, p.name COLLATE NOCASE"
        )
    ]


def request_out(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "personId": int(row["person_id"]),
        "personName": row.get("person_name", "—"),
        "dateFrom": row["date_from"],
        "dateTo": row["date_to"],
        "days": (engine.as_date(row["date_to"]) - engine.as_date(row["date_from"])).days + 1,
        "kind": row["kind"],
        "kindLabel": REQUEST_KIND_LABELS.get(row["kind"], row["kind"]),
        "reason": row["reason"],
        "status": row["status"],
        "statusLabel": REQUEST_STATUS_LABELS.get(row["status"], row["status"]),
        "createdAt": row["created_at"],
        "decidedAt": row["decided_at"],
    }


def _month_usage(
    conn: sqlite3.Connection, person_id: int, exclude_id: int | None = None
) -> dict[str, int]:
    usage: dict[str, int] = {}
    rows = conn.execute(
        "SELECT id, date_from, date_to FROM availability "
        "WHERE person_id = ? AND status <> 'declined'",
        (person_id,),
    )
    for row in rows:
        if exclude_id is not None and int(row["id"]) == exclude_id:
            continue
        cursor = engine.as_date(row["date_from"])
        finish = engine.as_date(row["date_to"])
        while cursor <= finish:
            key = cursor.strftime("%Y-%m")
            usage[key] = usage.get(key, 0) + 1
            cursor += timedelta(days=1)
    return usage


def check_request_limit(
    conn: sqlite3.Connection,
    person_id: int,
    days: list[date],
    limit: int,
    exclude_id: int | None = None,
) -> None:
    if limit <= 0:
        return
    usage = _month_usage(conn, person_id, exclude_id)
    extra: dict[str, int] = {}
    for day in days:
        key = day.strftime("%Y-%m")
        extra[key] = extra.get(key, 0) + 1
    for key, count in extra.items():
        already = usage.get(key, 0)
        if already + count > limit:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Лимит заявок — не более {limit} дней в месяц. "
                    f"На {key} уже отмечено {already} из {limit}."
                ),
            )


def check_request_overlap(
    conn: sqlite3.Connection,
    person_id: int,
    start: date,
    finish: date,
    exclude_id: int | None = None,
) -> None:
    for row in conn.execute(
        "SELECT id, date_from, date_to FROM availability "
        "WHERE person_id = ? AND status <> 'declined'",
        (person_id,),
    ):
        if exclude_id is not None and int(row["id"]) == exclude_id:
            continue
        other_start = engine.as_date(row["date_from"])
        other_finish = engine.as_date(row["date_to"])
        if start <= other_finish and other_start <= finish:
            raise HTTPException(
                status_code=409,
                detail=(
                    "На эти даты уже есть заявка "
                    f"{other_start:%d.%m.%Y}–{other_finish:%d.%m.%Y}."
                ),
            )


def merge_date_ranges(days: list[date]) -> list[tuple[date, date]]:
    ranges: list[tuple[date, date]] = []
    for day in sorted(set(days)):
        if ranges and (day - ranges[-1][1]).days == 1:
            ranges[-1] = (ranges[-1][0], day)
        else:
            ranges.append((day, day))
    return ranges


def request_dates(dates: list[str], horizon_days: int) -> list[date]:
    if not dates:
        raise HTTPException(status_code=400, detail="Выберите хотя бы один день")
    start = today()
    last = start + timedelta(days=horizon_days)
    parsed: set[date] = set()
    for value in dates:
        day = parse_day(value, "дата")
        if day < start:
            raise HTTPException(status_code=400, detail="Нельзя отмечать прошедшие дни")
        if day > last:
            raise HTTPException(
                status_code=400,
                detail=f"Заявки принимаются не дальше чем на {horizon_days} дней вперёд",
            )
        parsed.add(day)
    return sorted(parsed)


def user_out(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "username": row["username"],
        "role": row["role"],
        "roleLabel": ROLE_LABELS.get(row["role"], row["role"]),
        "personId": int(row["person_id"]) if row["person_id"] is not None else None,
        "personName": row.get("person_name") or "",
        "email": row["email"],
        "rocketchat": row["rocketchat"],
        "active": bool(row["active"]),
        "lastLoginAt": row["last_login_at"],
        "createdAt": row["created_at"],
    }


def load_users(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT u.*, p.name AS person_name FROM users u "
        "LEFT JOIN people p ON p.id = u.person_id "
        "ORDER BY u.role, u.username COLLATE NOCASE"
    )
    return [user_out(dict(row)) for row in rows]


def current_user(request: Request) -> dict[str, Any]:
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Требуется вход")
    return user


def require_admin(request: Request) -> dict[str, Any]:
    user = current_user(request)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Доступно только администратору")
    return user


def employee_person(conn: sqlite3.Connection, user: dict[str, Any]) -> dict[str, Any]:
    if user["person_id"] is None:
        raise HTTPException(
            status_code=409,
            detail="К учётной записи не привязан сотрудник. Обратитесь к администратору.",
        )
    row = conn.execute(
        "SELECT * FROM people WHERE id = ?", (int(user["person_id"]),)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=409, detail="Сотрудник не найден")
    return dict(row)


def _validate_username(value: str) -> str:
    username = value.strip()
    if not (3 <= len(username) <= 40):
        raise HTTPException(status_code=400, detail="Логин: от 3 до 40 символов")
    if not all(ch.isalnum() or ch in "._-@" for ch in username):
        raise HTTPException(
            status_code=400,
            detail="Логин может содержать буквы, цифры, точку, дефис, подчёркивание и @",
        )
    return username


def _user_row(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row:
    row = conn.execute(
        "SELECT u.*, p.name AS person_name FROM users u "
        "LEFT JOIN people p ON p.id = u.person_id WHERE u.id = ?",
        (user_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Учётная запись не найдена")
    return row


def _check_person_link(
    conn: sqlite3.Connection, person_id: int | None, exclude_user: int | None = None
) -> None:
    if person_id is None:
        return
    if not conn.execute("SELECT 1 FROM people WHERE id = ?", (person_id,)).fetchone():
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    query = "SELECT id FROM users WHERE person_id = ?"
    params: list[Any] = [person_id]
    if exclude_user is not None:
        query += " AND id <> ?"
        params.append(exclude_user)
    if conn.execute(query, params).fetchone():
        raise HTTPException(
            status_code=409, detail="Этот сотрудник уже привязан к другой учётной записи"
        )



def load_holidays(conn: sqlite3.Connection) -> tuple[list[dict[str, Any]], set[str]]:
    rows = [
        dict(row)
        for row in conn.execute("SELECT date, name FROM holidays ORDER BY date")
    ]
    return rows, {row["date"] for row in rows}


def load_comp_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(
            "SELECT c.duty_id, c.date, c.status, c.updated_at, "
            "d.person_id, d.date AS duty_date, d.status AS duty_status "
            "FROM comp_choices c JOIN duties d ON d.id = c.duty_id"
        )
    ]


def blocking_comps(comp_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row for row in comp_rows
        if row.get("status") in engine.COMP_BLOCKING_STATUSES
        and row.get("date") is not None
    ]


def names_map(people: list[dict[str, Any]]) -> dict[int, str]:
    return {int(p["id"]): p["name"] for p in people}


def duty_out(duty: dict[str, Any], names: dict[int, str]) -> dict[str, Any]:
    return {
        "id": duty["id"],
        "personId": int(duty["person_id"]),
        "personName": names.get(int(duty["person_id"]), "—"),
        "status": duty["status"],
        "source": duty["source"],
        "note": duty["note"],
    }


def round_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    candidate["weight"] = round(float(candidate.get("weight", 0)), 4)
    candidate["probability"] = round(float(candidate.get("probability", 0)), 4)
    load = candidate["load"]
    load["weighted"] = round(float(load["weighted"]), 2)
    return candidate


def get_rules(conn: sqlite3.Connection) -> tuple[dict[str, str], engine.Rules]:
    settings = db.load_settings(conn)
    return settings, engine.Rules.from_settings(settings)


def coverage_gaps(
    conn: sqlite3.Connection, start: date, finish: date
) -> list[dict[str, Any]]:
    """Дни без дежурства, где ни один сотрудник не может быть назначен."""
    settings, rules = get_rules(conn)
    people = load_people(conn)
    duties = load_duties(conn)
    absences = load_absences(conn)
    holidays, holiday_set = load_holidays(conn)
    comp_rows = load_comp_rows(conn)
    requests = load_availability(conn)
    holiday_names = {row["date"]: row["name"] for row in holidays}
    reviewed = {
        row["date"]: row["note"]
        for row in conn.execute("SELECT date, note FROM coverage_reviews")
    }
    duty_dates = {
        duty["date"] for duty in duties if engine.is_active_duty(duty)
    }

    gaps: list[dict[str, Any]] = []
    cursor = start
    while cursor <= finish:
        day_iso = cursor.isoformat()
        if day_iso in duty_dates or day_iso in reviewed:
            cursor += timedelta(days=1)
            continue
        evaluation = engine.evaluate_candidates(
            cursor,
            people,
            duties,
            absences,
            blocking_comps(comp_rows),
            holiday_set,
            rules,
            requests=requests,
        )
        if any(candidate["eligible"] for candidate in evaluation):
            cursor += timedelta(days=1)
            continue
        reasons = Counter(
            reason
            for candidate in evaluation
            for reason in candidate["reasons"]
        )
        relaxed = engine.evaluate_candidates(
            cursor,
            people,
            duties,
            absences,
            blocking_comps(comp_rows),
            holiday_set,
            rules,
            requests=requests,
            relax=True,
        )
        relaxed = engine.apply_probabilities(relaxed, rules.fairness_power)
        rescue = sorted(
            (
                {
                    "personId": candidate["person_id"],
                    "personName": candidate["person_name"],
                    "weight": round(float(candidate["weight"]), 4),
                    "probability": round(float(candidate["probability"]), 4),
                    "conflicts": candidate["conflicts"],
                    "load": round(float(candidate["load"]["weighted"]), 2),
                }
                for candidate in relaxed
                if candidate["eligible"]
            ),
            key=lambda item: (-item["probability"], item["personName"]),
        )
        absents = sorted(
            {
                absence["person_name"]
                for absence in absences
                if absence["date_from"] <= day_iso <= absence["date_to"]
            }
        )
        hard = sorted(
            {
                request["person_name"]
                for request in requests
                if request["kind"] == "unavailable"
                and request["status"] == "approved"
                and request["date_from"] <= day_iso <= request["date_to"]
            }
        )
        pending = sorted(
            {
                request["person_name"]
                for request in requests
                if request["kind"] == "unavailable"
                and request["status"] == "pending"
                and request["date_from"] <= day_iso <= request["date_to"]
            }
        )
        gaps.append(
            {
                "date": day_iso,
                "weekday": cursor.weekday(),
                "weekdayName": WEEKDAY_NAMES[cursor.weekday()],
                "dayOff": engine.is_day_off(cursor, holiday_set),
                "holiday": holiday_names.get(day_iso),
                "people": len(evaluation),
                "absents": absents,
                "unavailable": hard,
                "pending": pending,
                "candidates": rescue,
                "reasons": [
                    {"reason": reason, "count": count}
                    for reason, count in reasons.most_common(6)
                ],
            }
        )
        cursor += timedelta(days=1)
    return gaps


def refresh_coverage_alerts() -> int:
    """Уведомляет тимлидов о новых днях без доступных сотрудников."""
    with db.db() as conn:
        settings = db.load_settings(conn)
        if (
            settings.get("notifications_enabled", "0") != "1"
            or settings.get("notify_on_coverage", "1") != "1"
        ):
            return 0
        horizon = int(settings.get("request_horizon_days", 90))
        gaps = coverage_gaps(conn, today(), today() + timedelta(days=horizon))
        gap_dates = {gap["date"] for gap in gaps}
        alerted = {
            row["date"] for row in conn.execute("SELECT date FROM coverage_alerts")
        }

    stale = alerted - gap_dates
    if stale:
        with db.db() as conn:
            conn.executemany(
                "DELETE FROM coverage_alerts WHERE date = ?",
                [(item,) for item in stale],
            )

    fresh = sorted(gap_dates - alerted)
    if not fresh:
        return 0
    with db.db() as conn:
        base = db.load_settings(conn).get("public_url", "").rstrip("/")
    lines = []
    for item in fresh[:20]:
        day = engine.as_date(item)
        lines.append(f"• {day:%d.%m.%Y} ({WEEKDAY_NAMES[day.weekday()]})")
    if len(fresh) > 20:
        lines.append(f"… и ещё {len(fresh) - 20}")
    body = (
        "Ни один сотрудник не может дежурство в эти дни:\n"
        + "\n".join(lines)
        + "\n\nОткройте раздел «Требуют решения», чтобы назначить дежурного или снять день с контроля."
    )
    if base:
        body += f"\n{base}/"
    sent = notifier.enqueue(
        "coverage_gap", "Дни без доступных дежурных", body, teamlead=True
    )
    if sent:
        with db.db() as conn:
            conn.executemany(
                "INSERT OR IGNORE INTO coverage_alerts(date) VALUES(?)",
                [(item,) for item in fresh],
            )
    return len(fresh)



def _session_secret() -> str:
    secret = getattr(app.state, "session_secret", "")
    if secret:
        return secret
    with db.db() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = 'session_secret'"
        ).fetchone()
    app.state.session_secret = row["value"] if row else ""
    return app.state.session_secret


@app.middleware("http")
async def rbac_middleware(request: Request, call_next):
    path = request.url.path
    if (
        path == "/login"
        or path == "/api/auth/login"
        or path == "/api/health"
        or path.startswith("/static/")
    ):
        return await call_next(request)

    payload = security.read_session(
        request.cookies.get(SESSION_COOKIE), _session_secret()
    )
    user: dict[str, Any] | None = None
    if payload:
        with db.db() as conn:
            row = conn.execute(
                "SELECT u.*, p.name AS person_name FROM users u "
                "LEFT JOIN people p ON p.id = u.person_id WHERE u.id = ?",
                (int(payload["uid"]),),
            ).fetchone()
        if (
            row
            and row["active"]
            and row["role"] == payload.get("role")
            and payload.get("pv") == security.password_tag(row["password_hash"])
            and int(payload.get("ep") or 0) == int(row["session_epoch"] or 0)
        ):
            user = dict(row)
    request.state.user = user

    if not user:
        if path.startswith("/api/"):
            return JSONResponse({"detail": "Требуется вход"}, status_code=401)
        return RedirectResponse("/login", status_code=303)

    role = user["role"]
    if path == "/":
        if role == "employee":
            return RedirectResponse("/me", status_code=303)
        return await call_next(request)
    if path == "/me":
        if role != "employee":
            return RedirectResponse("/", status_code=303)
        return await call_next(request)
    if path.startswith("/api/auth/") or path.startswith("/api/me"):
        return await call_next(request)
    if not path.startswith("/api/"):
        return await call_next(request)
    if role == "employee":
        return JSONResponse({"detail": "Недостаточно прав"}, status_code=403)
    if path.startswith("/api/users") or path.startswith("/api/notifications"):
        if role != "admin":
            return JSONResponse(
                {"detail": "Доступно только администратору"}, status_code=403
            )
    return await call_next(request)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
    )
    response.headers.setdefault("Content-Security-Policy", CSP_HEADER)
    if _secure_cookie(request):
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response


@app.get("/login", include_in_schema=False)
def login_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "login.html")


@app.get("/me", include_in_schema=False)
def me_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "my.html")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/auth/login")
def login(payload: LoginIn, request: Request, response: Response) -> dict[str, Any]:
    username = payload.username.strip()
    if not username or not payload.password:
        raise HTTPException(status_code=400, detail="Укажите логин и пароль")
    key = _login_key(request, username)
    retry_after = login_retry_after(key)
    if retry_after:
        raise HTTPException(
            status_code=429,
            detail=(
                "Слишком много неудачных попыток входа. "
                f"Повторите через {retry_after} с."
            ),
            headers={"Retry-After": str(retry_after)},
        )
    with db.db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username,)
        ).fetchone()
        if (
            not row
            or not row["active"]
            or not security.verify_password(payload.password, row["password_hash"])
        ):
            note_login_failure(key)
            raise HTTPException(status_code=401, detail="Неверный логин или пароль")
        _login_failures.pop(key, None)
        conn.execute(
            "UPDATE users SET last_login_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') "
            "WHERE id = ?",
            (row["id"],),
        )
        row = _user_row(conn, int(row["id"]))
    token = security.create_session(
        int(row["id"]),
        row["role"],
        _session_secret(),
        security.password_tag(row["password_hash"]),
        epoch=int(row["session_epoch"] or 0),
    )
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=security.SESSION_TTL_SECONDS,
        httponly=True,
        secure=_secure_cookie(request),
        samesite="lax",
        path="/",
    )
    return {"user": user_out(dict(row))}


@app.get("/api/auth/me")
def auth_me(request: Request) -> dict[str, Any]:
    return {"user": user_out(current_user(request))}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response) -> dict[str, str]:
    user = getattr(request.state, "user", None)
    if user:
        with db.db() as conn:
            conn.execute(
                "UPDATE users SET session_epoch = session_epoch + 1 WHERE id = ?",
                (int(user["id"]),),
            )
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"status": "ok"}


@app.post("/api/auth/password")
def change_password(
    payload: PasswordIn, request: Request, response: Response
) -> dict[str, Any]:
    user = current_user(request)
    error = security.validate_password(payload.new_password)
    if error:
        raise HTTPException(status_code=400, detail=error)
    with db.db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (int(user["id"]),)
        ).fetchone()
        if not row or not security.verify_password(
            payload.current_password, row["password_hash"]
        ):
            raise HTTPException(status_code=400, detail="Текущий пароль указан неверно")
        password_hash = security.hash_password(payload.new_password)
        conn.execute(
            "UPDATE users SET password_hash = ?, "
            "session_epoch = session_epoch + 1 WHERE id = ?",
            (password_hash, row["id"]),
        )
        epoch = int(row["session_epoch"] or 0) + 1
    token = security.create_session(
        int(row["id"]),
        row["role"],
        _session_secret(),
        security.password_tag(password_hash),
        epoch=epoch,
    )
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=security.SESSION_TTL_SECONDS,
        httponly=True,
        secure=_secure_cookie(request),
        samesite="lax",
        path="/",
    )
    return {"status": "ok"}


@app.get("/api/users")
def users_list() -> dict[str, Any]:
    with db.db() as conn:
        users = load_users(conn)
        linked = {
            int(row["person_id"])
            for row in conn.execute(
                "SELECT person_id FROM users WHERE person_id IS NOT NULL"
            )
        }
        people = [
            {"id": int(person["id"]), "name": person["name"]}
            for person in load_people(conn)
            if int(person["id"]) not in linked
        ]
    return {"users": users, "availablePeople": people, "roleLabels": ROLE_LABELS}


@app.post("/api/users")
def create_user(payload: UserIn) -> dict[str, Any]:
    if payload.role not in ROLE_LABELS:
        raise HTTPException(status_code=400, detail="Некорректная роль")
    username = _validate_username(payload.username)
    error = security.validate_password(payload.password)
    if error:
        raise HTTPException(status_code=400, detail=error)
    with db.db() as conn:
        _check_person_link(conn, payload.person_id)
        try:
            cursor = conn.execute(
                "INSERT INTO users"
                "(username, password_hash, role, person_id, email, rocketchat, active) "
                "VALUES(?, ?, ?, ?, ?, ?, ?)",
                (
                    username,
                    security.hash_password(payload.password),
                    payload.role,
                    payload.person_id,
                    payload.email.strip()[:200],
                    payload.rocketchat.strip()[:200],
                    1 if payload.active else 0,
                ),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="Такой логин уже занят")
        row = _user_row(conn, int(cursor.lastrowid))
    return {"user": user_out(dict(row))}


@app.patch("/api/users/{user_id}")
def update_user(user_id: int, payload: UserPatch) -> dict[str, Any]:
    fields = payload.model_fields_set
    with db.db() as conn:
        current = _user_row(conn, user_id)
        updates: dict[str, Any] = {}
        if "username" in fields and payload.username is not None:
            updates["username"] = _validate_username(payload.username)
        if "password" in fields and payload.password:
            error = security.validate_password(payload.password)
            if error:
                raise HTTPException(status_code=400, detail=error)
            updates["password_hash"] = security.hash_password(payload.password)
        if "role" in fields and payload.role is not None:
            if payload.role not in ROLE_LABELS:
                raise HTTPException(status_code=400, detail="Некорректная роль")
            updates["role"] = payload.role
        if "person_id" in fields:
            _check_person_link(conn, payload.person_id, exclude_user=user_id)
            updates["person_id"] = payload.person_id
        if "email" in fields and payload.email is not None:
            updates["email"] = payload.email.strip()[:200]
        if "rocketchat" in fields and payload.rocketchat is not None:
            updates["rocketchat"] = payload.rocketchat.strip()[:200]
        if "active" in fields and payload.active is not None:
            updates["active"] = 1 if payload.active else 0

        loses_admin = (
            current["role"] == "admin"
            and current["active"]
            and (
                updates.get("role", "admin") != "admin"
                or updates.get("active", 1) == 0
            )
        )
        if loses_admin:
            active_admins = conn.execute(
                "SELECT COUNT(*) FROM users WHERE role = 'admin' AND active = 1"
            ).fetchone()[0]
            if active_admins <= 1:
                raise HTTPException(
                    status_code=409,
                    detail="Нельзя оставить систему без активного администратора",
                )
        if updates:
            columns = ", ".join(f"{key} = ?" for key in updates)
            try:
                conn.execute(
                    f"UPDATE users SET {columns} WHERE id = ?",
                    (*updates.values(), user_id),
                )
            except sqlite3.IntegrityError:
                raise HTTPException(status_code=409, detail="Такой логин уже занят")
        row = _user_row(conn, user_id)
    return {"user": user_out(dict(row))}


@app.delete("/api/users/{user_id}")
def delete_user(user_id: int, request: Request) -> dict[str, str]:
    actor = current_user(request)
    if user_id == int(actor["id"]):
        raise HTTPException(status_code=409, detail="Нельзя удалить собственную запись")
    with db.db() as conn:
        current = _user_row(conn, user_id)
        if current["role"] == "admin" and current["active"]:
            active_admins = conn.execute(
                "SELECT COUNT(*) FROM users WHERE role = 'admin' AND active = 1"
            ).fetchone()[0]
            if active_admins <= 1:
                raise HTTPException(
                    status_code=409,
                    detail="Нельзя оставить систему без активного администратора",
                )
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    return {"status": "deleted"}


@app.get("/api/schedule")
def schedule(month: str | None = None) -> dict[str, Any]:
    month = month or today().strftime("%Y-%m")
    start, next_start = month_bounds(month)
    grid_from = start - timedelta(days=start.weekday())
    last_day = next_start - timedelta(days=1)
    grid_to = last_day + timedelta(days=6 - last_day.weekday())

    with db.db() as conn:
        settings, rules = get_rules(conn)
        people = load_people(conn)
        names = names_map(people)
        duties = load_duties(conn)
        holidays, holiday_set = load_holidays(conn)
        comp_rows = load_comp_rows(conn)
        absences = load_absences(conn)
        requests = load_availability(conn)
        coverage_open = len(
            coverage_gaps(conn, today(), today() + timedelta(days=30))
        )

    loads = engine.loads_by_person(people, duties, holiday_set, rules)
    active_duties = [d for d in duties if engine.is_active_duty(d)]
    duty_by_date = {d["date"]: d for d in active_duties}

    rests_by_date: dict[str, list[dict[str, Any]]] = {}
    for duty in active_duties:
        duty_date = engine.as_date(duty["date"])
        for offset in range(1, rules.rest_days + 1):
            rest_date = (duty_date + timedelta(days=offset)).isoformat()
            rests_by_date.setdefault(rest_date, []).append(
                {
                    "personId": int(duty["person_id"]),
                    "personName": names.get(int(duty["person_id"]), "—"),
                    "dutyId": duty["id"],
                    "dutyDate": duty["date"],
                }
            )

    comps_by_date: dict[str, list[dict[str, Any]]] = {}
    for comp in comp_rows:
        if comp["status"] not in engine.COMP_BLOCKING_STATUSES or not comp["date"]:
            continue
        comps_by_date.setdefault(comp["date"], []).append(
            {
                "dutyId": comp["duty_id"],
                "personId": int(comp["person_id"]),
                "personName": names.get(int(comp["person_id"]), "—"),
                "status": comp["status"],
                "date": comp["date"],
            }
        )

    absences_by_date: dict[str, list[dict[str, Any]]] = {}
    for absence in absences:
        cursor = engine.as_date(absence["date_from"])
        finish = engine.as_date(absence["date_to"])
        while cursor <= finish:
            if grid_from <= cursor <= grid_to:
                absences_by_date.setdefault(cursor.isoformat(), []).append(
                    {
                        "id": absence["id"],
                        "personId": int(absence["person_id"]),
                        "personName": absence["person_name"],
                        "kind": absence["kind"],
                        "dateFrom": absence["date_from"],
                        "dateTo": absence["date_to"],
                    }
                )
            cursor += timedelta(days=1)

    requests_by_date: dict[str, list[dict[str, Any]]] = {}
    for request in requests:
        if request["status"] == "declined":
            continue
        cursor = engine.as_date(request["date_from"])
        finish = engine.as_date(request["date_to"])
        while cursor <= finish:
            if grid_from <= cursor <= grid_to:
                requests_by_date.setdefault(cursor.isoformat(), []).append(
                    {
                        "id": request["id"],
                        "personId": int(request["person_id"]),
                        "personName": request["person_name"],
                        "kind": request["kind"],
                        "status": request["status"],
                        "dateFrom": request["date_from"],
                        "dateTo": request["date_to"],
                        "reason": request["reason"],
                    }
                )
            cursor += timedelta(days=1)

    holiday_names = {row["date"]: row["name"] for row in holidays}
    days: list[dict[str, Any]] = []
    cursor = grid_from
    while cursor <= grid_to:
        day_iso = cursor.isoformat()
        duty = duty_by_date.get(day_iso)
        days.append(
            {
                "date": day_iso,
                "inMonth": start <= cursor < next_start,
                "weekday": cursor.weekday(),
                "weekend": cursor.weekday() >= 5,
                "dayOff": engine.is_day_off(cursor, holiday_set),
                "holiday": holiday_names.get(day_iso),
                "duty": duty_out(duty, names) if duty else None,
                "rests": rests_by_date.get(day_iso, []),
                "comps": comps_by_date.get(day_iso, []),
                "absences": absences_by_date.get(day_iso, []),
                "requests": requests_by_date.get(day_iso, []),
            }
        )
        cursor += timedelta(days=1)

    entitlements = engine.weekend_entitlements(
        active_duties, comp_rows, holiday_set, rules, today()
    )
    comp_summary = {"pending": 0, "scheduled": 0, "used": 0, "declined": 0}
    for item in entitlements:
        comp_summary[item["status"]] = comp_summary.get(item["status"], 0) + 1

    with db.db() as conn:
        draw_rows = [
            dict(row)
            for row in conn.execute(
                "SELECT dr.id, dr.date, dr.seed, dr.created_at, dr.candidates, "
                "dr.mode, dr.roll, dr.proof_hash, "
                "p.name AS winner_name FROM draws dr "
                "JOIN people p ON p.id = dr.winner_id "
                "WHERE dr.date BETWEEN ? AND ? "
                "ORDER BY dr.created_at DESC, dr.id DESC",
                (grid_from.isoformat(), grid_to.isoformat()),
            )
        ]
    for row in draw_rows:
        try:
            row["candidates"] = json.loads(row["candidates"])
        except (TypeError, ValueError):
            row["candidates"] = []
        row["winnerName"] = row.pop("winner_name")
        row["createdAt"] = row.pop("created_at")
        row["proofHash"] = row.pop("proof_hash")
        row["proofUrl"] = f"/proof/{row['id']}" if row["proofHash"] else None

    return {
        "today": today().isoformat(),
        "month": month,
        "gridFrom": grid_from.isoformat(),
        "gridTo": grid_to.isoformat(),
        "settings": settings_out(settings),
        "people": [
            {
                "id": int(p["id"]),
                "name": p["name"],
                "note": p["note"],
                "active": bool(p["active"]),
                "load": loads[int(p["id"])],
            }
            for p in people
        ],
        "days": days,
        "holidays": holidays,
        "compSummary": comp_summary,
        "requestSummary": {
            "pending": sum(1 for row in requests if row["status"] == "pending"),
            "approved": sum(1 for row in requests if row["status"] == "approved"),
        },
        "coverageSummary": {"open": coverage_open},
        "draws": draw_rows,
    }


@app.get("/api/candidates")
def candidates(
    day: str = Query(..., alias="date"),
    selected: str | None = None,
) -> dict[str, Any]:
    target = parse_day(day)
    selected_ids: list[int] | None = None
    if selected:
        try:
            selected_ids = [int(part) for part in selected.split(",") if part.strip()]
        except ValueError:
            raise HTTPException(status_code=400, detail="Некорректный список кандидатов")

    with db.db() as conn:
        settings, rules = get_rules(conn)
        people = load_people(conn)
        duties = load_duties(conn)
        absences = load_absences(conn)
        holidays, holiday_set = load_holidays(conn)
        comp_rows = load_comp_rows(conn)
        requests = load_availability(conn)

    evaluation = engine.evaluate_candidates(
        target, people, duties, absences, blocking_comps(comp_rows),
        holiday_set, rules, requests=requests,
    )
    evaluation = engine.apply_probabilities(
        evaluation, rules.fairness_power, selected_ids
    )
    names = names_map(people)
    duty = next(
        (
            d for d in duties
            if engine.is_active_duty(d) and d["date"] == target.isoformat()
        ),
        None,
    )
    holiday_names = {row["date"]: row["name"] for row in holidays}
    return {
        "date": target.isoformat(),
        "dayOff": engine.is_day_off(target, holiday_set),
        "holiday": holiday_names.get(target.isoformat()),
        "duty": duty_out(duty, names) if duty else None,
        "candidates": [round_candidate(c) for c in evaluation],
        "rules": {
            "fairness_power": rules.fairness_power,
            "weekend_weight": rules.weekend_weight,
            "rest_days": rules.rest_days,
            "min_gap_days": rules.min_gap_days,
            "comp_enabled": rules.comp_enabled,
            "comp_valid_days": rules.comp_valid_days,
        },
        "settings": settings_out(settings),
    }


@app.get("/api/roulette")
def roulette_preview(
    day: str = Query(..., alias="date"),
    relaxed: bool = Query(False),
) -> dict[str, Any]:
    target = parse_day(day)
    with db.db() as conn:
        _, rules = get_rules(conn)
        people = load_people(conn)
        duties = load_duties(conn)
        absences = load_absences(conn)
        holidays, holiday_set = load_holidays(conn)
        comp_rows = load_comp_rows(conn)
        requests = load_availability(conn)

    evaluation = engine.evaluate_candidates(
        target, people, duties, absences, blocking_comps(comp_rows),
        holiday_set, rules, requests=requests,
        relax=relaxed, keep_rest_blocking=relaxed,
    )
    month_counts = month_duty_counts(duties, target)
    equal = {
        c["person_id"]: c
        for c in engine.apply_roulette_weights(
            [dict(c) for c in evaluation], "equal", month_counts,
            rules.fairness_power,
        )
    }
    month = {
        c["person_id"]: c
        for c in engine.apply_roulette_weights(
            [dict(c) for c in evaluation], "month", month_counts,
            rules.fairness_power,
        )
    }
    names = names_map(people)
    duty = next(
        (
            d for d in duties
            if engine.is_active_duty(d) and d["date"] == target.isoformat()
        ),
        None,
    )
    holiday_names = {row["date"]: row["name"] for row in holidays}
    candidates = []
    for item in evaluation:
        person_id = int(item["person_id"])
        candidates.append(
            {
                "person_id": person_id,
                "person_name": item["person_name"],
                "eligible": item["eligible"],
                "reasons": item["reasons"],
                "conflicts": item["conflicts"],
                "warnings": item["warnings"],
                "total": item["load"]["total"],
                "weekend": item["load"]["weekend"],
                "weighted": round(float(item["load"]["weighted"]), 2),
                "month_duties": int(month_counts.get(person_id, 0)),
                "equal_weight": round(float(equal[person_id]["weight"]), 4),
                "equal_probability": round(
                    float(equal[person_id]["probability"]), 4
                ),
                "month_weight": round(float(month[person_id]["weight"]), 4),
                "month_probability": round(
                    float(month[person_id]["probability"]), 4
                ),
            }
        )
    return {
        "date": target.isoformat(),
        "month": f"{target.year:04d}-{target.month:02d}",
        "dayOff": engine.is_day_off(target, holiday_set),
        "holiday": holiday_names.get(target.isoformat()),
        "duty": duty_out(duty, names) if duty else None,
        "fairness_power": rules.fairness_power,
        "relaxed": relaxed,
        "candidates": candidates,
    }


@app.post("/api/duties")
def create_duty(payload: DutyIn) -> dict[str, Any]:
    target = parse_day(payload.date)
    target_iso = target.isoformat()
    with db.db() as conn:
        _, rules = get_rules(conn)
        person = conn.execute(
            "SELECT * FROM people WHERE id = ?", (payload.person_id,)
        ).fetchone()
        if not person:
            raise HTTPException(status_code=404, detail="Сотрудник не найден")
        if not person["active"]:
            raise HTTPException(status_code=409, detail="Сотрудник неактивен")
        occupied = conn.execute(
            "SELECT id, person_id FROM duties WHERE date = ? AND status <> 'cancelled'",
            (target_iso,),
        ).fetchone()
        if occupied:
            raise HTTPException(
                status_code=409,
                detail="На этот день уже назначено дежурство. Сначала снимите его.",
            )
        people = load_people(conn)
        duties = load_duties(conn)
        absences = load_absences(conn)
        holidays, holiday_set = load_holidays(conn)
        comp_rows = load_comp_rows(conn)
        requests = load_availability(conn)
        evaluation = engine.evaluate_candidates(
            target, people, duties, absences, blocking_comps(comp_rows),
            holiday_set, rules, requests=requests,
        )
        candidate = next(
            (c for c in evaluation if c["person_id"] == payload.person_id), None
        )
        if not candidate or not candidate["eligible"]:
            reasons = candidate["reasons"] if candidate else ["сотрудник неактивен"]
            raise HTTPException(
                status_code=409,
                detail="Назначение невозможно: " + "; ".join(reasons),
            )
        try:
            cursor = conn.execute(
                "INSERT INTO duties(date, person_id, status, source, note) "
                "VALUES(?, ?, 'planned', 'manual', ?)",
                (target_iso, payload.person_id, payload.note.strip()),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="День уже занят")
        duty = conn.execute(
            "SELECT * FROM duties WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    return {"duty": duty_out(dict(duty), names_map(people))}


@app.patch("/api/duties/{duty_id}")
def patch_duty(duty_id: int, payload: DutyPatch) -> dict[str, Any]:
    if payload.status not in DUTY_STATUS_LABELS:
        raise HTTPException(status_code=400, detail="Некорректный статус дежурства")
    with db.db() as conn:
        duty = conn.execute("SELECT * FROM duties WHERE id = ?", (duty_id,)).fetchone()
        if not duty:
            raise HTTPException(status_code=404, detail="Дежурство не найдено")
        people = load_people(conn)
        try:
            with db.transaction(conn):
                conn.execute(
                    "UPDATE duties SET status = ? WHERE id = ?",
                    (payload.status, duty_id),
                )
                if payload.status in ("cancelled", "missed"):
                    conn.execute(
                        "DELETE FROM comp_choices WHERE duty_id = ?", (duty_id,)
                    )
        except sqlite3.IntegrityError:
            raise HTTPException(
                status_code=409,
                detail="На этот день уже есть другое активное дежурство",
            )
        updated = conn.execute(
            "SELECT * FROM duties WHERE id = ?", (duty_id,)
        ).fetchone()
    if payload.status in ("cancelled", "missed"):
        refresh_coverage_alerts()
    return {"duty": duty_out(dict(updated), names_map(people))}


@app.delete("/api/duties/{duty_id}")
def delete_duty(duty_id: int) -> dict[str, str]:
    with db.db() as conn:
        cursor = conn.execute("DELETE FROM duties WHERE id = ?", (duty_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Дежурство не найдено")
    refresh_coverage_alerts()
    return {"status": "deleted"}


@app.post("/api/draw")
def draw(payload: DrawIn) -> dict[str, Any]:
    target = parse_day(payload.date)
    target_iso = target.isoformat()
    if payload.seed is not None and not (0 <= payload.seed <= 2**63 - 1):
        raise HTTPException(status_code=400, detail="Некорректный seed")

    with db.db() as conn:
        _, rules = get_rules(conn)
        occupied = conn.execute(
            "SELECT id, person_id, status FROM duties "
            "WHERE date = ? AND status <> 'cancelled'",
            (target_iso,),
        ).fetchone()
        if occupied and not payload.replace:
            raise HTTPException(
                status_code=409,
                detail="День уже занят. Включите переигровку, чтобы заменить дежурного.",
            )
        if occupied and occupied["status"] != "planned":
            raise HTTPException(
                status_code=409,
                detail="Переиграть можно только запланированное дежурство.",
            )
        if occupied:
            comp = conn.execute(
                "SELECT status FROM comp_choices WHERE duty_id = ?",
                (occupied["id"],),
            ).fetchone()
            if comp and comp["status"] in engine.COMP_BLOCKING_STATUSES:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Нельзя переиграть день: за текущее дежурство уже "
                        "запланирован или использован отгул."
                    ),
                )
        people = load_people(conn)
        duties = load_duties(conn)
        if occupied:
            duties = [
                d for d in duties if int(d["id"]) != int(occupied["id"])
            ]
        absences = load_absences(conn)
        holidays, holiday_set = load_holidays(conn)
        comp_rows = load_comp_rows(conn)
        requests = load_availability(conn)

        evaluation = engine.evaluate_candidates(
            target, people, duties, absences, blocking_comps(comp_rows),
            holiday_set, rules, requests=requests,
            relax=payload.relaxed, keep_rest_blocking=payload.relaxed,
        )
        by_id = {c["person_id"]: c for c in evaluation}
        eligible = [c for c in evaluation if c["eligible"]]

        chosen_ids = payload.candidate_ids or [c["person_id"] for c in eligible]
        unknown = [pid for pid in chosen_ids if pid not in by_id]
        if unknown:
            raise HTTPException(
                status_code=400, detail=f"Неизвестные сотрудники: {unknown}"
            )
        blocked = [
            f"{by_id[pid]['person_name']}: {'; '.join(by_id[pid]['reasons'])}"
            for pid in chosen_ids
            if not by_id[pid]["eligible"]
        ]
        if blocked:
            raise HTTPException(
                status_code=409,
                detail="В розыгрыше есть недоступные сотрудники — " + " | ".join(blocked),
            )

        if payload.mode not in ("load", *engine.ROULETTE_MODES):
            raise HTTPException(
                status_code=400, detail="Неизвестный режим розыгрыша"
            )
        month_counts = month_duty_counts(duties, target)
        if payload.mode == "load":
            evaluation = engine.apply_probabilities(
                evaluation, rules.fairness_power, chosen_ids
            )
        else:
            evaluation = engine.apply_roulette_weights(
                evaluation, payload.mode, month_counts, rules.fairness_power,
                chosen_ids,
            )
        pool = [c for c in evaluation if c["eligible"] and c["selected"]]
        if not pool:
            raise HTTPException(
                status_code=409,
                detail="Нет доступных кандидатов для розыгрыша",
            )

        seed = payload.seed if payload.seed is not None else secrets.randbits(31)
        rng = random.Random(seed)
        roll = rng.random()
        winner = engine.pick_by_roll(pool, roll)
        if winner is None:
            raise HTTPException(status_code=409, detail="Не удалось выбрать победителя")

        for candidate in pool:
            candidate["month_duties"] = int(
                month_counts.get(candidate["person_id"], 0)
            )
        proof_payload = proofs.build_payload(
            date=target_iso,
            mode=payload.mode,
            seed=seed,
            roll=roll,
            power=rules.fairness_power,
            weekend_weight=rules.weekend_weight,
            month=target.strftime("%Y-%m") if payload.mode == "month" else None,
            candidates=pool,
            winner_id=int(winner["person_id"]),
            winner_name=winner["person_name"],
        )
        proof_json = proofs.canonical_json(proof_payload)
        proof_hash = proofs.digest(proof_payload)

        snapshot = [
            {
                "personId": c["person_id"],
                "name": c["person_name"],
                "total": c["load"]["total"],
                "weekend": c["load"]["weekend"],
                "weighted": round(float(c["load"]["weighted"]), 2),
                "weight": round(float(c["weight"]), 4),
                "probability": round(float(c["probability"]), 4),
                "monthDuties": int(month_counts.get(c["person_id"], 0)),
                "conflicts": c.get("conflicts", []),
                "winner": c["person_id"] == winner["person_id"],
            }
            for c in pool
        ]

        deviations = list(winner.get("conflicts") or [])

        if payload.mode == "equal":
            note = f"Рулетка · равные шансы, seed {seed}"
        elif payload.mode == "month":
            note = f"Рулетка · дежурства за {target:%m.%Y}, seed {seed}"
        else:
            note = f"Жребий, seed {seed}"
        if deviations:
            note += " · отклонения: " + "; ".join(deviations)

        try:
            with db.transaction(conn):
                if occupied:
                    conn.execute(
                        "UPDATE duties SET status = 'cancelled' WHERE id = ?",
                        (occupied["id"],),
                    )
                    conn.execute(
                        "DELETE FROM comp_choices WHERE duty_id = ?",
                        (occupied["id"],),
                    )
                cursor = conn.execute(
                    "INSERT INTO duties(date, person_id, status, source, note) "
                    "VALUES(?, ?, 'planned', 'draw', ?)",
                    (target_iso, winner["person_id"], note),
                )
                draw_cursor = conn.execute(
                    "INSERT INTO draws(date, seed, winner_id, candidates, mode, "
                    "roll, proof, proof_hash) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        target_iso,
                        seed,
                        winner["person_id"],
                        json.dumps(snapshot, ensure_ascii=False),
                        payload.mode,
                        roll,
                        proof_json,
                        proof_hash,
                    ),
                )
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="День уже занят")

    return {
        "date": target_iso,
        "seed": seed,
        "mode": payload.mode,
        "drawId": draw_cursor.lastrowid,
        "roll": roll,
        "proofHash": proof_hash,
        "proofUrl": f"/proof/{draw_cursor.lastrowid}",
        "winner": {
            "personId": winner["person_id"],
            "personName": winner["person_name"],
            "probability": round(float(winner["probability"]), 4),
            "load": winner["load"],
            "monthDuties": int(month_counts.get(winner["person_id"], 0)),
        },
        "deviations": deviations,
        "replacedDutyId": int(occupied["id"]) if occupied else None,
        "candidates": snapshot,
    }


DRAW_MODE_LABELS = {
    "load": "По накопленной нагрузке",
    "month": "Дежурства за месяц",
    "equal": "Равные шансы",
}


def _proof_record(draw_id: int) -> dict[str, Any]:
    with db.db() as conn:
        row = conn.execute(
            "SELECT dr.*, p.name AS winner_name FROM draws dr "
            "JOIN people p ON p.id = dr.winner_id WHERE dr.id = ?",
            (draw_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Розыгрыш не найден")
    try:
        snapshot = json.loads(row["candidates"])
    except (TypeError, ValueError):
        snapshot = []
    mode = row["mode"] or "load"
    record: dict[str, Any] = {
        "drawId": int(row["id"]),
        "date": row["date"],
        "seed": int(row["seed"]),
        "winnerId": int(row["winner_id"]),
        "winnerName": row["winner_name"],
        "mode": mode,
        "modeLabel": DRAW_MODE_LABELS.get(mode, mode),
        "roll": row["roll"],
        "createdAt": row["created_at"],
        "proofHash": row["proof_hash"],
        "proofUrl": f"/proof/{row['id']}",
        "available": bool(row["proof"] and row["proof_hash"]),
        "snapshot": snapshot,
    }
    if not record["available"]:
        record["reason"] = (
            "Розыгрыш создан до включения проверяемых пруфов: seed и ставки "
            "сохранены, но криптографическая печать недоступна."
        )
        return record
    try:
        payload = json.loads(row["proof"])
    except (TypeError, ValueError):
        record["available"] = False
        record["reason"] = "Пакет пруфа повреждён и не читается."
        return record
    check = proofs.verify(payload, str(row["proof_hash"]))
    record.update(
        {
            "payload": payload,
            "canonical": check["canonical"],
            "checks": check["checks"],
            "verified": check["verified"],
            "intervals": check["intervals"],
            "replayedWinnerId": check["replayedWinnerId"],
            "replayedWinnerName": check["replayedWinnerName"],
            "totalWeight": check["totalWeight"],
            "threshold": check["threshold"],
            "algorithm": proofs.ALGORITHM,
        }
    )
    return record


@app.get("/api/proof/{draw_id}")
def proof_api(draw_id: int) -> dict[str, Any]:
    return _proof_record(draw_id)


def _proof_page_html(record: dict[str, Any] | None, draw_id: int) -> str:
    if record is None:
        return """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<title>Пруф не найден</title><link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' fill='%23191512'/%3E%3Crect x='6' y='6' width='52' height='52' fill='%23d6221f'/%3E%3Ctext x='32' y='44' font-family='Arial Narrow,Arial' font-size='30' font-weight='700' text-anchor='middle' fill='%23f8f3e7'%3E24%3C/text%3E%3C/svg%3E"><link rel="stylesheet" href="/static/style.css"></head>
<body><main class="proof-page"><h1>Розыгрыш не найден</h1>
<p><a class="btn" href="/">Вернуться к графику</a> <button class="btn btn--ghost lang-toggle" type="button" data-lang-toggle>EN</button></p></main>
<script src="/static/i18n.js"></script></body></html>"""

    date_label = ""
    try:
        date_label = f"{engine.as_date(record['date']):%d.%m.%Y}"
    except ValueError:
        date_label = record["date"]

    if not record["available"]:
        verdict_class = "proof-verdict--legacy"
        verdict_text = "АРХИВНАЯ ЗАПИСЬ"
        verdict_note = record.get("reason", "")
        rows = "".join(
            f"<tr><td>{html.escape(str(item.get('name', '—')))}</td>"
            f"<td class=\"num\">{html.escape(str(item.get('total', '—')))}</td>"
            f"<td class=\"num\">{html.escape(str(item.get('weekend', '—')))}</td>"
            f"<td class=\"num\">{float(item.get('weighted', 0)):.2f}</td>"
            f"<td class=\"num\">{float(item.get('probability', 0)) * 100:.2f}%</td>"
            f"<td>{'<span class=\"pill pill--used\">выбран</span>' if item.get('winner') else ''}</td></tr>"
            for item in record.get("snapshot", [])
        )
        body = f"""
        <section class="panel">
          <div class="panel__head"><h2>Кандидаты из архива</h2></div>
          <div class="table-wrap"><table class="table">
            <thead><tr><th>Кандидат</th><th class="num">Дежурств</th><th class="num">Выходных</th><th class="num">Нагрузка</th><th class="num">Вероятность</th><th></th></tr></thead>
            <tbody>{rows or '<tr><td colspan="6">Нет данных</td></tr>'}</tbody>
          </table></div>
        </section>"""
        details = f"""
        <div class="proof-meta">
          <div><span>Дата</span><b>{html.escape(date_label)}</b></div>
          <div><span>Победитель</span><b>{html.escape(record['winnerName'])}</b></div>
          <div><span>Seed</span><b><code>{record['seed']}</code></b></div>
          <div><span>Режим</span><b>{html.escape(record['modeLabel'])}</b></div>
        </div>"""
        checks_html = ""
        canonical_html = ""
    else:
        payload = record["payload"]
        checks = record["checks"]
        verified = bool(record["verified"])
        verdict_class = "proof-verdict--ok" if verified else "proof-verdict--fail"
        verdict_text = "ПОДТВЕРЖДЕНО" if verified else "НЕ СОВПАЛО"
        verdict_note = (
            "Печать совпадает, повторный пересчёт даёт того же победителя."
            if verified
            else "Хэш или пересчёт не совпали. Результат нельзя считать доказуемым."
        )
        month_map = {
            int(item["personId"]): int(item.get("monthDuties", 0))
            for item in payload.get("candidates", [])
        }
        rows = ""
        for item in record["intervals"]:
            winner = int(item["personId"]) == int(record["winnerId"])
            rows += f"""
              <tr class="{'row--selected' if winner else ''}">
                <td>{html.escape(item['name'])}{' <span class="pill pill--used">выбран</span>' if winner else ''}</td>
                <td class="num">{month_map.get(int(item['personId']), 0)}</td>
                <td class="num">{item['weight']:.6f}</td>
                <td class="num">{item['probability'] * 100:.4f}%</td>
                <td class="num mono">{item['from']:.6f} – {item['to']:.6f}</td>
              </tr>"""
        checks_html = "".join(
            f"<li class=\"{'is-ok' if value else 'is-fail'}\">"
            f"{'✓' if value else '✗'} {html.escape(label)}</li>"
            for label, value in (
                ("SHA-256 пакета совпадает с печатью", checks["hashMatches"]),
                ("Сумма весов положительна", checks["weightsPositive"]),
                ("Сумма вероятностей равна 1", checks["probabilitiesSum"]),
                ("Пересчёт даёт указанного победителя", checks["winnerMatches"]),
            )
        )
        details = f"""
        <div class="proof-meta">
          <div><span>Дата</span><b>{html.escape(date_label)}</b></div>
          <div><span>Победитель</span><b>{html.escape(record['winnerName'])}</b></div>
          <div><span>Режим</span><b>{html.escape(record['modeLabel'])}</b></div>
          <div><span>Seed</span><b><code>{record['seed']}</code></b></div>
          <div><span>Случайное число (roll)</span><b class="mono">{record['roll']:.12f}</b></div>
          <div><span>Сумма весов</span><b class="mono">{record['totalWeight']:.6f}</b></div>
          <div><span>Порог roll × Σвесов</span><b class="mono">{record['threshold']:.6f}</b></div>
          <div><span>Алгоритм</span><b>{html.escape(record['algorithm'])}</b></div>
        </div>
        <section class="panel">
          <div class="panel__head">
            <h2>Пакет жеребьёвки</h2>
            <span class="small muted">победитель — первый интервал, накрывающий порог</span>
          </div>
          <div class="table-wrap"><table class="table">
            <thead><tr><th>Кандидат</th><th class="num">Дежурств в месяце</th><th class="num">Вес</th><th class="num">Вероятность</th><th class="num">Интервал</th></tr></thead>
            <tbody>{rows}</tbody>
          </table></div>
        </section>
        <section class="panel">
          <div class="panel__head"><h2>Проверка</h2></div>
          <ul class="proof-checks">{checks_html}</ul>
        </section>"""
        canonical_html = f"""
        <section class="panel">
          <div class="panel__head"><h2>Канонический пакет</h2></div>
          <pre class="proof-pre">{html.escape(record['canonical'])}</pre>
        </section>"""
        body = ""

    manual = (
        "import hashlib, json\n"
        "payload = json.loads(open('proof.json', encoding='utf-8').read())\n"
        "canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))\n"
        "print(hashlib.sha256(canonical.encode('utf-8')).hexdigest())\n"
        "\n"
        "total = sum(c['weight'] for c in payload['candidates'])\n"
        "threshold = payload['roll'] * total\n"
        "acc = 0\n"
        "for c in payload['candidates']:\n"
        "    acc += c['weight']\n"
        "    if threshold < acc:\n"
        "        print('winner', c['personId'])\n"
        "        break\n"
    )
    hash_block = ""
    if record.get("proofHash"):
        hash_block = f"""
        <div class="proof-hash">
          <span>SHA-256 печать</span>
          <code>{html.escape(record['proofHash'])}</code>
        </div>"""

    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Пруф жеребьёвки №{record['drawId']} — дежурства</title>
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' fill='%23191512'/%3E%3Crect x='6' y='6' width='52' height='52' fill='%23d6221f'/%3E%3Ctext x='32' y='44' font-family='Arial Narrow,Arial' font-size='30' font-weight='700' text-anchor='middle' fill='%23f8f3e7'%3E24%3C/text%3E%3C/svg%3E">
  <script src="/static/theme.js"></script>
  <script src="/static/i18n.js"></script>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
<main class="proof-page">
  <header class="proof-head">
    <div>
      <div class="eyebrow">Проверяемый жребий · пакет №{record['drawId']}</div>
      <h1 class="page-title">Пруф жеребьёвки</h1>
      <p class="page-sub">Канонический JSON, SHA-256 и повторный пересчёт выбора. Данные не зависят от текущего состояния графика.</p>
    </div>
    <div class="proof-actions">
      <button class="btn btn--ghost lang-toggle" type="button" data-lang-toggle>EN</button>
      <button class="btn btn--ghost" type="button" data-theme-toggle>Тёмная</button>
      <a class="btn btn--ghost" href="/api/proof/{record['drawId']}">JSON</a>
      <a class="btn btn--ghost" href="/">К графику</a>
    </div>
  </header>

  <div class="proof-verdict {verdict_class}">
    <b>{verdict_text}</b>
    <span>{html.escape(verdict_note)}</span>
  </div>

  {details}
  {hash_block}
  {body}
  {canonical_html}

  <section class="panel">
    <div class="panel__head"><h2>Как проверить самому</h2></div>
    <p class="small muted">Сохраните JSON пакета как <code>proof.json</code> и выполните код. Хэш должен совпасть с печатью, а победитель — с записью.</p>
    <pre class="proof-pre">{html.escape(manual)}</pre>
  </section>

  <div class="note-panel">
    <strong>Что это доказывает.</strong> Сервер заранее фиксирует seed, случайное число, веса и вероятности всех участников.
    Любой может пересчитать SHA-256 канонического JSON и убедиться, что победитель выбран именно этим случайным числом.
  </div>
</main>
</body>
</html>"""


@app.get("/proof/{draw_id}", include_in_schema=False)
def proof_page(draw_id: int) -> HTMLResponse:
    try:
        record = _proof_record(draw_id)
    except HTTPException:
        return HTMLResponse(_proof_page_html(None, draw_id), status_code=404)
    return HTMLResponse(_proof_page_html(record, draw_id))


@app.post("/api/auto-plan")
def auto_plan(payload: AutoPlanIn) -> dict[str, Any]:
    start = parse_day(payload.date_from, "дата начала")
    finish = parse_day(payload.date_to, "дата окончания")
    if start > finish:
        raise HTTPException(status_code=400, detail="Дата начала позже даты окончания")
    if (finish - start).days > 122:
        raise HTTPException(status_code=400, detail="Максимальный период — 123 дня")

    seed = payload.seed if payload.seed is not None else secrets.randbits(31)
    if not (0 <= seed <= 2**63 - 1):
        raise HTTPException(status_code=400, detail="Некорректный seed")

    with db.db() as conn:
        _, rules = get_rules(conn)
        people = load_people(conn)
        duties = load_duties(conn)
        absences = load_absences(conn)
        holidays, holiday_set = load_holidays(conn)
        comp_rows = load_comp_rows(conn)
        requests = load_availability(conn)

        plan = engine.build_auto_plan(
            people, duties, absences, blocking_comps(comp_rows), holiday_set,
            rules, start, finish, seed, requests=requests,
        )
        assigned = plan["assigned"]
        try:
            with db.transaction(conn):
                for item in assigned:
                    conn.execute(
                        "INSERT INTO duties(date, person_id, status, source, note) "
                        "VALUES(?, ?, 'planned', 'auto', ?)",
                        (item["date"], item["person_id"], f"Автораспределение, seed {seed}"),
                    )
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="Расписание изменилось, повторите")

    refresh_coverage_alerts()
    return {
        "seed": seed,
        "count": len(assigned),
        "assigned": assigned,
        "skipped": plan["skipped"],
    }


@app.get("/api/people")
def people_list() -> dict[str, Any]:
    with db.db() as conn:
        people = load_people(conn)
    return {"people": people}


@app.post("/api/people")
def create_person(payload: PersonIn) -> dict[str, Any]:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Укажите имя сотрудника")
    if len(name) > 120:
        raise HTTPException(status_code=400, detail="Слишком длинное имя")
    with db.db() as conn:
        cursor = conn.execute(
            "INSERT INTO people(name, note, active, email, rocketchat) "
            "VALUES(?, ?, 1, ?, ?)",
            (
                name,
                payload.note.strip()[:200],
                payload.email.strip()[:200],
                payload.rocketchat.strip()[:200],
            ),
        )
        person = conn.execute(
            "SELECT id, name, note, active, email, rocketchat FROM people WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
    return {"person": dict(person)}


@app.patch("/api/people/{person_id}")
def patch_person(person_id: int, payload: PersonPatch) -> dict[str, Any]:
    with db.db() as conn:
        current = conn.execute(
            "SELECT * FROM people WHERE id = ?", (person_id,)
        ).fetchone()
        if not current:
            raise HTTPException(status_code=404, detail="Сотрудник не найден")
        updates: dict[str, Any] = {}
        if payload.name is not None:
            name = payload.name.strip()
            if not name:
                raise HTTPException(status_code=400, detail="Имя не может быть пустым")
            updates["name"] = name[:120]
        if payload.note is not None:
            updates["note"] = payload.note.strip()[:200]
        if payload.email is not None:
            updates["email"] = payload.email.strip()[:200]
        if payload.rocketchat is not None:
            updates["rocketchat"] = payload.rocketchat.strip()[:200]
        if payload.active is not None:
            updates["active"] = 1 if payload.active else 0
        if updates:
            columns = ", ".join(f"{key} = ?" for key in updates)
            conn.execute(
                f"UPDATE people SET {columns} WHERE id = ?",
                (*updates.values(), person_id),
            )
        person = conn.execute(
            "SELECT id, name, note, active, email, rocketchat FROM people WHERE id = ?",
            (person_id,),
        ).fetchone()
    return {"person": dict(person)}


@app.get("/api/absences")
def absences_list() -> dict[str, Any]:
    with db.db() as conn:
        rows = load_absences(conn)
    return {"absences": rows, "kinds": ABSENCE_KIND_LABELS}


@app.post("/api/absences")
def create_absence(payload: AbsenceIn) -> dict[str, Any]:
    if payload.kind not in ABSENCE_KIND_LABELS:
        raise HTTPException(status_code=400, detail="Некорректный тип отсутствия")
    start = parse_day(payload.date_from, "дата начала")
    finish = parse_day(payload.date_to, "дата окончания")
    if finish < start:
        raise HTTPException(status_code=400, detail="Дата окончания раньше даты начала")
    if (finish - start).days > 365:
        raise HTTPException(status_code=400, detail="Слишком длинный период отсутствия")
    with db.db() as conn:
        person = conn.execute(
            "SELECT * FROM people WHERE id = ?", (payload.person_id,)
        ).fetchone()
        if not person:
            raise HTTPException(status_code=404, detail="Сотрудник не найден")
        conflicts = [
            row["date"]
            for row in conn.execute(
                "SELECT date FROM duties WHERE person_id = ? AND status <> 'cancelled' "
                "AND date BETWEEN ? AND ? ORDER BY date",
                (payload.person_id, start.isoformat(), finish.isoformat()),
            )
        ]
        if conflicts:
            raise HTTPException(
                status_code=409,
                detail="Сначала снимите дежурства на эти даты: " + ", ".join(conflicts),
            )
        cursor = conn.execute(
            "INSERT INTO absences(person_id, date_from, date_to, kind, note) "
            "VALUES(?, ?, ?, ?, ?)",
            (
                payload.person_id,
                start.isoformat(),
                finish.isoformat(),
                payload.kind,
                payload.note.strip()[:200],
            ),
        )
        row = conn.execute(
            "SELECT a.*, p.name AS person_name FROM absences a "
            "JOIN people p ON p.id = a.person_id WHERE a.id = ?",
            (cursor.lastrowid,),
        ).fetchone()
    refresh_coverage_alerts()
    return {"absence": dict(row)}


@app.delete("/api/absences/{absence_id}")
def delete_absence(absence_id: int) -> dict[str, str]:
    with db.db() as conn:
        cursor = conn.execute("DELETE FROM absences WHERE id = ?", (absence_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Отсутствие не найдено")
    return {"status": "deleted"}


@app.get("/api/requests")
def requests_list(
    status: str | None = None, person_id: int | None = None
) -> dict[str, Any]:
    with db.db() as conn:
        rows = load_availability(conn)
    if status:
        rows = [row for row in rows if row["status"] == status]
    if person_id is not None:
        rows = [row for row in rows if int(row["person_id"]) == person_id]
    order = {"pending": 0, "approved": 1, "declined": 2}
    rows.sort(key=lambda row: (order.get(row["status"], 9), row["date_from"]))
    counts = {"pending": 0, "approved": 0, "declined": 0}
    with db.db() as conn:
        for row in load_availability(conn):
            counts[row["status"]] = counts.get(row["status"], 0) + 1
    return {
        "requests": [request_out(row) for row in rows],
        "counts": counts,
        "kindLabels": REQUEST_KIND_LABELS,
        "statusLabels": REQUEST_STATUS_LABELS,
    }


@app.patch("/api/requests/{request_id}")
def decide_request(request_id: int, payload: RequestDecisionIn) -> dict[str, Any]:
    if payload.status not in ("approved", "declined"):
        raise HTTPException(status_code=400, detail="Некорректный статус заявки")
    with db.db() as conn:
        row = conn.execute(
            "SELECT * FROM availability WHERE id = ?", (request_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Заявка не найдена")
        if payload.status == "approved":
            start = engine.as_date(row["date_from"])
            finish = engine.as_date(row["date_to"])
            conflicts = sorted(
                duty["date"]
                for duty in load_duties(conn)
                if engine.is_active_duty(duty)
                and int(duty["person_id"]) == int(row["person_id"])
                and start <= engine.as_date(duty["date"]) <= finish
            )
            if conflicts:
                pretty = ", ".join(f"{engine.as_date(d):%d.%m.%Y}" for d in conflicts)
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "На эти дни у сотрудника дежурство: "
                        f"{pretty}. Сначала переназначьте его."
                    ),
                )
        conn.execute(
            "UPDATE availability SET status = ?, "
            "decided_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE id = ?",
            (payload.status, request_id),
        )
        updated = conn.execute(
            "SELECT r.*, p.name AS person_name FROM availability r "
            "JOIN people p ON p.id = r.person_id WHERE r.id = ?",
            (request_id,),
        ).fetchone()
    result = request_out(dict(updated))
    notifier.enqueue(
        "request_decided",
        f"Заявка {REQUEST_STATUS_LABELS[payload.status].lower()}",
        (
            f"Ваша заявка «{result['kindLabel']}» на {result['dateFrom']}–{result['dateTo']} "
            f"{REQUEST_STATUS_LABELS[payload.status].lower()}."
            + (
                "\nСогласованные дни исключены из распределения дежурств."
                if payload.status == "approved"
                else ""
            )
        ),
        person_id=int(updated["person_id"]),
    )
    if payload.status == "approved":
        refresh_coverage_alerts()
    return {"request": result}


@app.delete("/api/requests/{request_id}")
def delete_request(request_id: int) -> dict[str, str]:
    with db.db() as conn:
        cursor = conn.execute("DELETE FROM availability WHERE id = ?", (request_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Заявка не найдена")
    return {"status": "deleted"}


@app.get("/api/coverage")
def coverage_list(
    date_from: str | None = None, date_to: str | None = None
) -> dict[str, Any]:
    start = parse_day(date_from, "дата начала") if date_from else today()
    finish = parse_day(date_to, "дата окончания") if date_to else start + timedelta(days=90)
    if finish < start:
        raise HTTPException(status_code=400, detail="Дата окончания раньше даты начала")
    if (finish - start).days > 366:
        raise HTTPException(status_code=400, detail="Максимальный период — 367 дней")
    with db.db() as conn:
        gaps = coverage_gaps(conn, start, finish)
        reviewed = [
            dict(row)
            for row in conn.execute(
                "SELECT r.date, r.note, r.created_at, u.username FROM coverage_reviews r "
                "LEFT JOIN users u ON u.id = r.created_by "
                "WHERE r.date BETWEEN ? AND ? ORDER BY r.date",
                (start.isoformat(), finish.isoformat()),
            )
        ]
        overrides = [
            dict(row)
            for row in conn.execute(
                "SELECT o.date, o.reason, o.created_at, p.name AS person_name, "
                "u.username FROM coverage_overrides o "
                "JOIN people p ON p.id = o.person_id "
                "LEFT JOIN users u ON u.id = o.created_by "
                "WHERE o.date BETWEEN ? AND ? ORDER BY o.date DESC, o.id DESC",
                (start.isoformat(), finish.isoformat()),
            )
        ]
    return {
        "today": today().isoformat(),
        "dateFrom": start.isoformat(),
        "dateTo": finish.isoformat(),
        "days": gaps,
        "reviewed": reviewed,
        "overrides": overrides,
        "count": len(gaps),
    }


@app.post("/api/coverage/{day}/dismiss")
def dismiss_coverage(
    day: str, payload: CoverageDismissIn, request: Request
) -> dict[str, Any]:
    target = parse_day(day, "дата")
    if target < today():
        raise HTTPException(status_code=400, detail="Прошедший день нельзя снять с контроля")
    user = current_user(request)
    with db.db() as conn:
        occupied = conn.execute(
            "SELECT id FROM duties WHERE date = ? AND status <> 'cancelled'",
            (target.isoformat(),),
        ).fetchone()
        if occupied:
            raise HTTPException(
                status_code=409, detail="На этот день уже назначено дежурство"
            )
        conn.execute(
            "INSERT INTO coverage_reviews(date, note, created_by) VALUES(?, ?, ?) "
            "ON CONFLICT(date) DO UPDATE SET note = excluded.note, "
            "created_by = excluded.created_by, "
            "created_at = strftime('%Y-%m-%dT%H:%M:%SZ','now')",
            (target.isoformat(), payload.note.strip()[:300], int(user["id"])),
        )
        conn.execute(
            "DELETE FROM coverage_alerts WHERE date = ?", (target.isoformat(),)
        )
    return {"date": target.isoformat(), "status": "dismissed"}


@app.delete("/api/coverage/{day}")
def reopen_coverage(day: str) -> dict[str, str]:
    target = parse_day(day, "дата")
    with db.db() as conn:
        cursor = conn.execute(
            "DELETE FROM coverage_reviews WHERE date = ?", (target.isoformat(),)
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="День не снят с контроля")
    return {"status": "reopened"}


@app.post("/api/coverage/{day}/assign")
def assign_coverage(
    day: str, payload: CoverageAssignIn, request: Request
) -> dict[str, Any]:
    target = parse_day(day, "дата")
    if target < today():
        raise HTTPException(status_code=400, detail="Нельзя назначать дежурство в прошлое")
    reason = payload.reason.strip()
    if len(reason) < 5:
        raise HTTPException(
            status_code=400, detail="Опишите причину решения (не короче 5 символов)"
        )
    user = current_user(request)
    with db.db() as conn:
        _, rules = get_rules(conn)
        person = conn.execute(
            "SELECT * FROM people WHERE id = ?", (payload.person_id,)
        ).fetchone()
        if not person:
            raise HTTPException(status_code=404, detail="Сотрудник не найден")
        if not person["active"]:
            raise HTTPException(status_code=409, detail="Сотрудник неактивен")
        occupied = conn.execute(
            "SELECT id FROM duties WHERE date = ? AND status <> 'cancelled'",
            (target.isoformat(),),
        ).fetchone()
        if occupied:
            raise HTTPException(
                status_code=409,
                detail="На этот день уже назначено дежурство. Сначала снимите его.",
            )
        people = load_people(conn)
        duties = load_duties(conn)
        absences = load_absences(conn)
        holidays, holiday_set = load_holidays(conn)
        comp_rows = load_comp_rows(conn)
        requests = load_availability(conn)
        evaluation = engine.evaluate_candidates(
            target, people, duties, absences, blocking_comps(comp_rows),
            holiday_set, rules, requests=requests,
        )
        candidate = next(
            (item for item in evaluation if item["person_id"] == payload.person_id),
            None,
        )
        warnings = candidate["reasons"] if candidate else []
        try:
            with db.transaction(conn):
                cursor = conn.execute(
                    "INSERT INTO duties(date, person_id, status, source, note) "
                    "VALUES(?, ?, 'planned', 'manual', ?)",
                    (
                        target.isoformat(),
                        payload.person_id,
                        f"Решение тимлида: {reason}",
                    ),
                )
                conn.execute(
                    "INSERT INTO coverage_overrides(date, person_id, reason, created_by) "
                    "VALUES(?, ?, ?, ?)",
                    (target.isoformat(), payload.person_id, reason, int(user["id"])),
                )
                conn.execute(
                    "DELETE FROM coverage_reviews WHERE date = ?",
                    (target.isoformat(),),
                )
                conn.execute(
                    "DELETE FROM coverage_alerts WHERE date = ?",
                    (target.isoformat(),),
                )
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="День уже занят")
        duty = conn.execute(
            "SELECT * FROM duties WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        names = names_map(people)

    notifier.enqueue(
        "coverage_override",
        "Назначено дежурство",
        (
            f"Вам назначено дежурство на {target:%d.%m.%Y} решением тимлида.\n"
            f"Причина: {reason}\n"
            "Если дата не подходит, свяжитесь с тимлидом."
        ),
        person_id=int(payload.person_id),
    )
    return {
        "duty": duty_out(dict(duty), names),
        "warnings": warnings,
    }


@app.get("/api/me")
def my_data(request: Request) -> dict[str, Any]:
    user = current_user(request)
    with db.db() as conn:
        settings, _ = get_rules(conn)
        person = employee_person(conn, user)
        person_id = int(person["id"])
        requests = [
            row for row in load_availability(conn)
            if int(row["person_id"]) == person_id
        ]
        duties = [
            duty for duty in load_duties(conn)
            if engine.is_active_duty(duty) and int(duty["person_id"]) == person_id
        ]
        holidays, _ = load_holidays(conn)

    horizon_days = int(settings.get("request_horizon_days", 90))
    horizon_to = today() + timedelta(days=horizon_days)
    earliest = today() - timedelta(days=31)
    visible_duties = [
        {
            "date": duty["date"],
            "status": duty["status"],
            "source": duty["source"],
        }
        for duty in duties
        if earliest <= engine.as_date(duty["date"]) <= horizon_to
    ]
    visible_duties.sort(key=lambda item: item["date"])
    return {
        "unitName": settings.get("unit_name", "Дежурная служба"),
        "user": user_out(user),
        "person": {
            "id": person_id,
            "name": person["name"],
            "note": person["note"],
            "active": bool(person["active"]),
        },
        "today": today().isoformat(),
        "horizonTo": horizon_to.isoformat(),
        "horizonDays": horizon_days,
        "monthLimit": int(settings.get("request_month_limit", 10)),
        "requests": [request_out(row) for row in requests],
        "duties": visible_duties,
        "holidays": [
            row for row in holidays
            if today().isoformat() <= row["date"] <= horizon_to.isoformat()
        ],
        "kindLabels": REQUEST_KIND_LABELS,
        "statusLabels": REQUEST_STATUS_LABELS,
    }


@app.post("/api/me/requests")
def my_create_request(payload: MyRequestIn, request: Request) -> dict[str, Any]:
    if payload.kind not in REQUEST_KIND_LABELS:
        raise HTTPException(status_code=400, detail="Некорректный тип заявки")
    user = current_user(request)
    reason = payload.reason.strip()[:200]
    with db.db() as conn:
        settings, _ = get_rules(conn)
        person = employee_person(conn, user)
        if not person["active"]:
            raise HTTPException(status_code=409, detail="Сотрудник неактивен")
        person_id = int(person["id"])
        horizon_days = int(settings.get("request_horizon_days", 90))
        limit = int(settings.get("request_month_limit", 10))
        days = request_dates(payload.dates, horizon_days)
        ranges = merge_date_ranges(days)
        for start, finish in ranges:
            check_request_overlap(conn, person_id, start, finish)
        check_request_limit(conn, person_id, days, limit)

        created_ids: list[int] = []
        with db.transaction(conn):
            for start, finish in ranges:
                cursor = conn.execute(
                    "INSERT INTO availability"
                    "(person_id, date_from, date_to, kind, reason, status) "
                    "VALUES(?, ?, ?, ?, ?, 'pending')",
                    (
                        person_id,
                        start.isoformat(),
                        finish.isoformat(),
                        payload.kind,
                        reason,
                    ),
                )
                created_ids.append(int(cursor.lastrowid))
        placeholders = ",".join("?" for _ in created_ids)
        rows = conn.execute(
            "SELECT r.*, p.name AS person_name FROM availability r "
            f"JOIN people p ON p.id = r.person_id WHERE r.id IN ({placeholders}) "
            "ORDER BY r.date_from",
            created_ids,
        ).fetchall()

    periods = ", ".join(
        f"{start:%d.%m.%Y}–{finish:%d.%m.%Y}" if start != finish else f"{start:%d.%m.%Y}"
        for start, finish in ranges
    )
    notifier.enqueue(
        "request_created",
        f"Новая заявка: {person['name']}",
        (
            f"{person['name']} подал(а) заявку «{REQUEST_KIND_LABELS[payload.kind]}».\n"
            f"Дни: {periods}\n"
            f"Причина: {reason or 'не указана'}\n\n"
            "Согласуйте или отклоните заявку в разделе «Заявки»."
        ),
        teamlead=True,
    )
    return {
        "created": [request_out(dict(row)) for row in rows],
        "count": len(rows),
    }


@app.delete("/api/me/requests/{request_id}")
def my_delete_request(request_id: int, request: Request) -> dict[str, str]:
    user = current_user(request)
    with db.db() as conn:
        person = employee_person(conn, user)
        row = conn.execute(
            "SELECT * FROM availability WHERE id = ? AND person_id = ?",
            (request_id, int(person["id"])),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Заявка не найдена")
        if row["status"] != "pending":
            raise HTTPException(
                status_code=409,
                detail="Отозвать можно только заявку, ожидающую согласования",
            )
        conn.execute("DELETE FROM availability WHERE id = ?", (request_id,))
    return {"status": "deleted"}


@app.get("/api/comps")
def comps_list() -> dict[str, Any]:
    with db.db() as conn:
        _, rules = get_rules(conn)
        people = load_people(conn)
        duties = load_duties(conn)
        holidays, holiday_set = load_holidays(conn)
        comp_rows = load_comp_rows(conn)
    names = names_map(people)
    active = {
        int(p["id"]): bool(p["active"]) for p in people
    }
    entitlements = engine.weekend_entitlements(
        duties, comp_rows, holiday_set, rules, today()
    )
    for item in entitlements:
        item["personName"] = names.get(item["person_id"], "—")
        item["personActive"] = active.get(item["person_id"], False)
    status_order = {"pending": 0, "scheduled": 1, "used": 2, "declined": 3}
    entitlements.sort(
        key=lambda item: (
            status_order.get(item["status"], 9),
            -engine.as_date(item["duty_date"]).toordinal(),
        )
    )
    counts = {"pending": 0, "scheduled": 0, "used": 0, "declined": 0}
    for item in entitlements:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    return {
        "today": today().isoformat(),
        "comps": entitlements,
        "counts": counts,
        "compEnabled": rules.comp_enabled,
        "compValidDays": rules.comp_valid_days,
        "statusLabels": COMP_STATUS_LABELS,
    }


@app.put("/api/comps/{duty_id}")
def update_comp(duty_id: int, payload: CompIn) -> dict[str, Any]:
    if payload.status not in COMP_STATUS_LABELS:
        raise HTTPException(status_code=400, detail="Некорректный статус отгула")
    with db.db() as conn:
        _, rules = get_rules(conn)
        if not rules.comp_enabled:
            raise HTTPException(status_code=400, detail="Отгулы отключены в настройках")
        duty = conn.execute("SELECT * FROM duties WHERE id = ?", (duty_id,)).fetchone()
        if not duty:
            raise HTTPException(status_code=404, detail="Дежурство не найдено")
        if duty["status"] in ("cancelled", "missed"):
            raise HTTPException(
                status_code=409, detail="За отменённое/несостоявшееся дежурство отгул не даётся"
            )
        people = load_people(conn)
        duties = load_duties(conn)
        absences = load_absences(conn)
        holidays, holiday_set = load_holidays(conn)
        comp_rows = load_comp_rows(conn)
        if not engine.is_day_off(engine.as_date(duty["date"]), holiday_set):
            raise HTTPException(
                status_code=400, detail="Отгул даётся только за выходное/праздничное дежурство"
            )

        existing = next(
            (row for row in comp_rows if int(row["duty_id"]) == duty_id), None
        )
        if payload.status == "pending":
            conn.execute("DELETE FROM comp_choices WHERE duty_id = ?", (duty_id,))
        elif payload.status == "declined":
            conn.execute(
                "INSERT INTO comp_choices(duty_id, date, status, updated_at) "
                "VALUES(?, NULL, 'declined', strftime('%Y-%m-%dT%H:%M:%SZ','now')) "
                "ON CONFLICT(duty_id) DO UPDATE SET date = NULL, "
                "status = 'declined', updated_at = excluded.updated_at",
                (duty_id,),
            )
        else:
            raw_date = payload.date or (existing["date"] if existing else None)
            if not raw_date:
                raise HTTPException(status_code=400, detail="Укажите дату отгула")
            comp_date = parse_day(raw_date, "дата отгула")
            error = engine.validate_comp_date(
                comp_date,
                engine.as_date(duty["date"]),
                int(duty["person_id"]),
                duties,
                absences,
                blocking_comps(comp_rows),
                holiday_set,
                rules,
                ignore_duty_id=duty_id,
            )
            if error:
                raise HTTPException(status_code=409, detail=error)
            conn.execute(
                "INSERT INTO comp_choices(duty_id, date, status, updated_at) "
                "VALUES(?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ','now')) "
                "ON CONFLICT(duty_id) DO UPDATE SET date = excluded.date, "
                "status = excluded.status, updated_at = excluded.updated_at",
                (duty_id, comp_date.isoformat(), payload.status),
            )

        comp_rows = load_comp_rows(conn)
        entitlements = engine.weekend_entitlements(
            duties, comp_rows, holiday_set, rules, today()
        )
        item = next(
            (entry for entry in entitlements if entry["duty_id"] == duty_id), None
        )
        names = names_map(people)
        if item:
            item["personName"] = names.get(item["person_id"], "—")
    return {"comp": item}


@app.get("/api/holidays")
def holidays_list() -> dict[str, Any]:
    with db.db() as conn:
        rows, _ = load_holidays(conn)
    return {"holidays": rows}


@app.post("/api/holidays")
def create_holiday(payload: HolidayIn) -> dict[str, Any]:
    day = parse_day(payload.date, "дата праздника")
    name = payload.name.strip()[:120] or "Праздник"
    with db.db() as conn:
        conn.execute(
            "INSERT INTO holidays(date, name) VALUES(?, ?) "
            "ON CONFLICT(date) DO UPDATE SET name = excluded.name",
            (day.isoformat(), name),
        )
    return {"holiday": {"date": day.isoformat(), "name": name}}


@app.delete("/api/holidays/{holiday_date}")
def delete_holiday(holiday_date: str) -> dict[str, str]:
    day = parse_day(holiday_date, "дата праздника")
    with db.db() as conn:
        cursor = conn.execute("DELETE FROM holidays WHERE date = ?", (day.isoformat(),))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Праздник не найден")
    return {"status": "deleted"}


@app.post("/api/holidays/seed")
def seed_holidays(payload: HolidaySeedIn) -> dict[str, Any]:
    year = payload.year or today().year
    if year < 2000 or year > 2100:
        raise HTTPException(status_code=400, detail="Год вне поддерживаемого диапазона")
    with db.db() as conn:
        before = conn.total_changes
        for day, name in belarus_holidays(year):
            conn.execute(
                "INSERT OR IGNORE INTO holidays(date, name) VALUES(?, ?)",
                (day.isoformat(), name),
            )
        inserted = conn.total_changes - before
        _record_seeded_year(conn, year)
        rows = [
            dict(row)
            for row in conn.execute(
                "SELECT date, name FROM holidays WHERE date LIKE ? ORDER BY date",
                (f"{year}-%",),
            )
        ]
    return {"year": year, "inserted": inserted, "holidays": rows}


@app.get("/api/stats")
def stats() -> dict[str, Any]:
    with db.db() as conn:
        settings, rules = get_rules(conn)
        people = load_people(conn)
        duties = load_duties(conn)
        holidays, holiday_set = load_holidays(conn)
        comp_rows = load_comp_rows(conn)
        requests = load_availability(conn)
        reviews = conn.execute("SELECT COUNT(*) FROM coverage_reviews").fetchone()[0]
        overrides = conn.execute("SELECT COUNT(*) FROM coverage_overrides").fetchone()[0]
        horizon = min(int(settings.get("request_horizon_days", 90)), 180)
        gaps = coverage_gaps(conn, today(), today() + timedelta(days=horizon))
    loads = engine.loads_by_person(people, duties, holiday_set, rules)
    entitlements = engine.weekend_entitlements(
        duties, comp_rows, holiday_set, rules, today()
    )
    comps_by_person: dict[int, dict[str, int]] = {}
    for item in entitlements:
        bucket = comps_by_person.setdefault(
            item["person_id"],
            {"pending": 0, "scheduled": 0, "used": 0, "declined": 0},
        )
        bucket[item["status"]] += 1

    next_duty: dict[int, str] = {}
    last_duty: dict[int, str] = {}
    for duty in duties:
        if not engine.is_active_duty(duty):
            continue
        pid = int(duty["person_id"])
        if duty["date"] >= today().isoformat():
            if pid not in next_duty or duty["date"] < next_duty[pid]:
                next_duty[pid] = duty["date"]
        elif pid not in last_duty or duty["date"] > last_duty[pid]:
            last_duty[pid] = duty["date"]

    month_keys: list[str] = []
    cursor = today().replace(day=1)
    for offset in range(11, -1, -1):
        index = cursor.year * 12 + (cursor.month - 1) - offset
        year, month = index // 12, index % 12 + 1
        month_keys.append(f"{year:04d}-{month:02d}")

    result: list[dict[str, Any]] = []
    for person in people:
        pid = int(person["id"])
        person_duties = [
            duty for duty in duties
            if int(duty["person_id"]) == pid and engine.is_active_duty(duty)
        ]
        counts = {
            status: sum(1 for duty in person_duties if duty["status"] == status)
            for status in ("planned", "done", "missed")
        }
        by_weekday = [0] * 7
        by_month = Counter(duty["date"][:7] for duty in person_duties)
        for duty in person_duties:
            by_weekday[engine.as_date(duty["date"]).weekday()] += 1
        comps = comps_by_person.get(
            pid, {"pending": 0, "scheduled": 0, "used": 0, "declined": 0}
        )
        total = int(loads[pid]["total"])
        result.append(
            {
                "id": pid,
                "name": person["name"],
                "note": person["note"],
                "email": person["email"],
                "rocketchat": person["rocketchat"],
                "active": bool(person["active"]),
                "load": loads[pid],
                "counts": counts,
                "byWeekday": by_weekday,
                "byMonth": [by_month.get(key, 0) for key in month_keys],
                "weekendShare": (
                    round(int(loads[pid]["weekend"]) / total, 3) if total else 0.0
                ),
                "nextDuty": next_duty.get(pid),
                "lastDuty": last_duty.get(pid),
                "comps": comps,
            }
        )

    active_loads = [
        entry["load"]["weighted"]
        for entry in result
        if entry["active"] and entry["load"]["total"] > 0
    ]
    fairness: dict[str, Any] = {"mean": 0.0, "stdev": 0.0, "cv": 0.0, "spread": 0.0}
    if active_loads:
        mean = statistics.fmean(active_loads)
        stdev = statistics.pstdev(active_loads) if len(active_loads) > 1 else 0.0
        fairness = {
            "mean": round(mean, 2),
            "stdev": round(stdev, 2),
            "cv": round(stdev / mean, 3) if mean else 0.0,
            "spread": round(max(active_loads) - min(active_loads), 2),
        }

    all_duties = [d for d in duties if engine.is_active_duty(d)]
    totals = {
        "people": sum(1 for p in people if p["active"]),
        "duties": len(all_duties),
        "weekend": sum(
            1 for d in all_duties
            if engine.is_day_off(engine.as_date(d["date"]), holiday_set)
        ),
        "compsUsed": sum(1 for item in entitlements if item["status"] == "used"),
        "compsPending": sum(1 for item in entitlements if item["status"] == "pending"),
        "requestsPending": sum(1 for r in requests if r["status"] == "pending"),
        "coverageGaps": len(gaps),
        "compsScheduled": sum(
            1 for item in entitlements if item["status"] == "scheduled"
        ),
    }

    weekdays = [
        {
            "weekday": index,
            "name": name,
            "short": WEEKDAY_SHORT[index],
            "total": 0,
            "dayOff": 0,
            "workday": 0,
        }
        for index, name in enumerate(WEEKDAY_NAMES)
    ]
    for duty in all_duties:
        day = engine.as_date(duty["date"])
        bucket = weekdays[day.weekday()]
        bucket["total"] += 1
        if engine.is_day_off(day, holiday_set):
            bucket["dayOff"] += 1
        else:
            bucket["workday"] += 1

    month_counts: dict[str, dict[str, int]] = {}
    for duty in all_duties:
        key = duty["date"][:7]
        bucket = month_counts.setdefault(key, {"total": 0, "dayOff": 0})
        bucket["total"] += 1
        if engine.is_day_off(engine.as_date(duty["date"]), holiday_set):
            bucket["dayOff"] += 1
    months: list[dict[str, Any]] = []
    for key in month_keys:
        year, month = int(key[:4]), int(key[5:7])
        counts = month_counts.get(key, {"total": 0, "dayOff": 0})
        months.append(
            {
                "month": key,
                "label": f"{month:02d}.{year}",
                "total": counts["total"],
                "dayOff": counts["dayOff"],
            }
        )

    request_summary = {
        "pending": sum(1 for r in requests if r["status"] == "pending"),
        "approved": sum(1 for r in requests if r["status"] == "approved"),
        "declined": sum(1 for r in requests if r["status"] == "declined"),
        "unavailable": sum(1 for r in requests if r["kind"] == "unavailable"),
        "preferred": sum(1 for r in requests if r["kind"] == "preferred"),
    }

    duty_dates = {duty["date"] for duty in all_duties}
    horizon_days = 0
    unassigned = 0
    day_cursor = today()
    horizon_end = today() + timedelta(days=horizon)
    while day_cursor <= horizon_end:
        horizon_days += 1
        if day_cursor.isoformat() not in duty_dates:
            unassigned += 1
        day_cursor += timedelta(days=1)

    with db.db() as conn:
        draw_rows = conn.execute(
            "SELECT dr.id, dr.date, dr.seed, dr.mode, dr.roll, dr.proof, "
            "dr.proof_hash, p.name AS winner_name FROM draws dr "
            "JOIN people p ON p.id = dr.winner_id "
            "ORDER BY dr.id DESC LIMIT 12"
        ).fetchall()
    draw_audit: list[dict[str, Any]] = []
    for row in draw_rows:
        verified: bool | None = None
        if row["proof"] and row["proof_hash"]:
            try:
                verified = proofs.verify(
                    json.loads(row["proof"]), str(row["proof_hash"])
                )["verified"]
            except (TypeError, ValueError):
                verified = False
        mode = row["mode"] or "load"
        draw_audit.append(
            {
                "id": int(row["id"]),
                "date": row["date"],
                "seed": int(row["seed"]),
                "mode": mode,
                "modeLabel": DRAW_MODE_LABELS.get(mode, mode),
                "winner": row["winner_name"],
                "proofHash": row["proof_hash"],
                "proofUrl": f"/proof/{row['id']}" if row["proof_hash"] else None,
                "verified": verified,
            }
        )

    return {
        "today": today().isoformat(),
        "stats": result,
        "fairness": fairness,
        "totals": totals,
        "weekdays": weekdays,
        "months": months,
        "requests": request_summary,
        "coverage": {
            "open": len(gaps),
            "dismissed": int(reviews),
            "overrides": int(overrides),
            "horizonDays": horizon_days,
            "unassigned": unassigned,
        },
        "draws": draw_audit,
        "weekendWeight": rules.weekend_weight,
        "fairnessPower": rules.fairness_power,
    }


def _csv_cell(value: Any) -> str:
    """Защита от формул Excel/Calc в пользовательских полях."""
    text = "" if value is None else str(value)
    if text.lstrip()[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


@app.get("/api/export")
def export_csv(
    month: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> Response:
    if date_from or date_to:
        start = parse_day(date_from or "2000-01-01", "дата начала")
        finish = parse_day(date_to or today().isoformat(), "дата окончания")
        if start > finish:
            raise HTTPException(status_code=400, detail="Дата начала позже даты окончания")
        label = f"{start.isoformat()}_{finish.isoformat()}"
    else:
        month = month or today().strftime("%Y-%m")
        start, next_start = month_bounds(month)
        finish = next_start - timedelta(days=1)
        label = month

    with db.db() as conn:
        _, rules = get_rules(conn)
        holidays, holiday_set = load_holidays(conn)
        rows = [
            dict(row)
            for row in conn.execute(
                "SELECT d.date, d.status, d.source, d.note, p.name, "
                "c.date AS comp_date, c.status AS comp_status "
                "FROM duties d JOIN people p ON p.id = d.person_id "
                "LEFT JOIN comp_choices c ON c.duty_id = d.id "
                "WHERE d.status <> 'cancelled' AND d.date BETWEEN ? AND ? "
                "ORDER BY d.date",
                (start.isoformat(), finish.isoformat()),
            )
        ]
    holiday_names = {row["date"]: row["name"] for row in holidays}

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow(
        [
            "Дата", "День недели", "Дежурный", "Тип дня", "Статус",
            "Источник", "Отгул за дежурство", "Примечание",
        ]
    )
    for row in rows:
        day = engine.as_date(row["date"])
        if day.isoformat() in holiday_names:
            day_type = "Праздник: " + holiday_names[day.isoformat()]
        elif day.weekday() >= 5:
            day_type = "Выходной"
        else:
            day_type = "Рабочий"
        comp = ""
        if row["comp_date"]:
            comp = f"{row['comp_date']} ({COMP_STATUS_LABELS.get(row['comp_status'], '')})"
        writer.writerow(
            [
                f"{day.day:02d}.{day.month:02d}.{day.year}",
                WEEKDAY_NAMES[day.weekday()],
                _csv_cell(row["name"]),
                day_type,
                DUTY_STATUS_LABELS.get(row["status"], row["status"]),
                SOURCE_LABELS.get(row["source"], row["source"]),
                comp,
                _csv_cell(row["note"]),
            ]
        )

    content = "\ufeff" + buffer.getvalue()
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="duties_{label}.csv"'
        },
    )


@app.get("/api/export/schedule.xlsx")
def export_schedule_xlsx(
    month: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> Response:
    if date_from or date_to:
        start = parse_day(date_from or today().isoformat(), "дата начала")
        finish = parse_day(date_to or today().isoformat(), "дата окончания")
        label = f"{start.isoformat()}_{finish.isoformat()}"
    else:
        month = month or today().strftime("%Y-%m")
        start, next_start = month_bounds(month)
        finish = next_start - timedelta(days=1)
        label = month
    if start > finish:
        raise HTTPException(status_code=400, detail="Дата начала позже даты окончания")
    if (finish - start).days > 366:
        raise HTTPException(status_code=400, detail="Максимальный период — 367 дней")

    with db.db() as conn:
        settings = db.load_settings(conn)
        people = load_people(conn)
        holidays, holiday_set = load_holidays(conn)
        rows = [
            dict(row)
            for row in conn.execute(
                "SELECT d.date, d.status, d.source, d.note, d.person_id, p.name, "
                "c.date AS comp_date, c.status AS comp_status "
                "FROM duties d JOIN people p ON p.id = d.person_id "
                "LEFT JOIN comp_choices c ON c.duty_id = d.id "
                "WHERE d.status <> 'cancelled' AND d.date BETWEEN ? AND ? "
                "ORDER BY d.date",
                (start.isoformat(), finish.isoformat()),
            )
        ]

    duties_by_date = {row["date"]: row for row in rows}
    holiday_names = {row["date"]: row["name"] for row in holidays}
    unit = settings.get("unit_name", "Дежурная служба")
    weekend_count = sum(
        1 for row in rows
        if engine.is_day_off(engine.as_date(row["date"]), holiday_set)
    )
    subtitle = (
        f"{unit} · период: {start:%d.%m.%Y} — {finish:%d.%m.%Y} · "
        f"дежурств: {len(rows)} (выходных и праздничных: {weekend_count})"
    )

    table: list[list[xlsx.Cell]] = [
        [("ГРАФИК СУТОЧНЫХ ДЕЖУРСТВ", xlsx.TITLE)],
        [(subtitle, xlsx.SUBTITLE)],
        [
            ("№", xlsx.HEADER),
            ("Дата", xlsx.HEADER),
            ("День недели", xlsx.HEADER),
            ("Тип дня", xlsx.HEADER),
            ("Дежурный", xlsx.HEADER),
            ("Статус", xlsx.HEADER),
            ("Отгул за дежурство", xlsx.HEADER),
            ("Примечание", xlsx.HEADER),
        ],
    ]
    heights = {1: 26, 2: 15, 3: 30}
    cursor = start
    number = 0
    while cursor <= finish:
        number += 1
        day_iso = cursor.isoformat()
        duty = duties_by_date.get(day_iso)
        holiday = holiday_names.get(day_iso)
        is_weekend = cursor.weekday() >= 5
        if holiday:
            day_type = f"Праздник: {holiday}"
            left, center, bold = xlsx.HOLIDAY, xlsx.HOLIDAY_CENTER, xlsx.BOLD_HOLIDAY
        elif is_weekend:
            day_type = "Выходной"
            left, center, bold = xlsx.WEEKEND, xlsx.WEEKEND_CENTER, xlsx.BOLD_WEEKEND
        else:
            day_type = "Рабочий"
            left, center, bold = xlsx.BODY, xlsx.BODY_CENTER, xlsx.BOLD

        comp = "—"
        if duty and duty["comp_date"]:
            comp_day = engine.as_date(duty["comp_date"])
            comp = (
                f"{comp_day:%d.%m.%Y} "
                f"({COMP_STATUS_LABELS.get(duty['comp_status'], duty['comp_status'])})"
            )
        table.append(
            [
                (number, center),
                (f"{cursor:%d.%m.%Y}", center),
                (WEEKDAY_NAMES[cursor.weekday()], center),
                (day_type, left),
                (duty["name"] if duty else "—", bold if duty else left),
                (
                    DUTY_STATUS_LABELS.get(duty["status"], duty["status"])
                    if duty else "—",
                    center,
                ),
                (comp, left),
                (duty["note"] if duty else "", left),
            ]
        )
        heights[len(table)] = 20
        cursor += timedelta(days=1)

    merges = ["A1:H1", "A2:H2"]
    table.append([])
    for line in (
        "Начальник подразделения: ________________________ / ________________________ /",
        "Составил: ________________________ / ________________________ /",
        "«___» ________________ 20___ г.",
    ):
        table.append([(line, xlsx.SIGNATURE)])
        row_number = len(table)
        merges.append(f"A{row_number}:H{row_number}")

    dates = []
    cursor = start
    while cursor <= finish:
        dates.append(cursor)
        cursor += timedelta(days=1)

    duty_person = {
        row["date"]: int(row["person_id"]) for row in rows
    }
    people_with_duty = set(duty_person.values())
    matrix_people = [
        person for person in people
        if person["active"] or int(person["id"]) in people_with_duty
    ]
    matrix_people.sort(key=lambda person: person["name"].lower())

    matrix: list[list[xlsx.Cell]] = [
        [("ТАБЛИЦА ДЕЖУРСТВ: ФИО / ДАТА", xlsx.TITLE)],
        [
            (
                f"{subtitle} · Д — дежурство; розовый столбец — выходной; "
                "жёлтый — праздник",
                xlsx.SUBTITLE,
            )
        ],
        [("ФИО \\ Дата", xlsx.HEADER)]
        + [
            (
                f"{day.day:02d}",
                xlsx.HOLIDAY_HEAD if day.isoformat() in holiday_names
                else xlsx.WEEKEND_HEAD if day.weekday() >= 5
                else xlsx.HEADER,
            )
            for day in dates
        ]
        + [("Всего", xlsx.HEADER), ("Вых.", xlsx.HEADER)],
        [("День недели", xlsx.HEADER)]
        + [
            (
                WEEKDAY_SHORT[day.weekday()],
                xlsx.HOLIDAY_HEAD if day.isoformat() in holiday_names
                else xlsx.WEEKEND_HEAD if day.weekday() >= 5
                else xlsx.HEADER,
            )
            for day in dates
        ]
        + [("", xlsx.HEADER), ("", xlsx.HEADER)],
    ]
    matrix_heights = {1: 26, 2: 15, 3: 19, 4: 16}
    for person in matrix_people:
        person_id = int(person["id"])
        total = 0
        day_off_total = 0
        matrix_row: list[xlsx.Cell] = [(person["name"], xlsx.BOLD)]
        for day in dates:
            day_iso = day.isoformat()
            if duty_person.get(day_iso) == person_id:
                matrix_row.append(("Д", xlsx.MATRIX_DUTY))
                total += 1
                if engine.is_day_off(day, holiday_set):
                    day_off_total += 1
            elif day_iso in holiday_names:
                matrix_row.append(("", xlsx.HOLIDAY_CENTER))
            elif day.weekday() >= 5:
                matrix_row.append(("", xlsx.WEEKEND_CENTER))
            else:
                matrix_row.append(("", xlsx.BODY_CENTER))
        matrix_row.extend([(total, xlsx.TOTAL), (day_off_total, xlsx.TOTAL)])
        matrix.append(matrix_row)
        matrix_heights[len(matrix)] = 17

    last_column = xlsx.column_name(len(dates) + 2)
    matrix_merges = [f"A1:{last_column}1", f"A2:{last_column}2", "A3:A4"]
    matrix.append([])
    for line in (
        "Начальник подразделения: ________________________ / ________________________ /",
        "Составил: ________________________ / ________________________ /",
        "«___» ________________ 20___ г.",
    ):
        matrix.append([(line, xlsx.SIGNATURE)])
        row_number = len(matrix)
        matrix_merges.append(f"A{row_number}:{last_column}{row_number}")

    content = xlsx.build_workbook(
        [
            xlsx.Sheet(
                "ФИО-Дата",
                matrix,
                widths=[26] + [4.8] * len(dates) + [7, 7],
                merges=matrix_merges,
                row_heights=matrix_heights,
                freeze_rows=4,
                freeze_cols=1,
                print_title_rows=(3, 4),
                print_title_column=True,
                orientation="landscape",
                fit_to_width=None,
                scale=65,
                footer=(unit, "Стр. &P из &N", f"{start:%d.%m.%Y} — {finish:%d.%m.%Y}"),
            ),
            xlsx.Sheet(
                "Список",
                table,
                widths=[5, 12, 15, 22, 26, 14, 20, 34],
                merges=merges,
                row_heights=heights,
                freeze_rows=3,
                print_title_rows=(3, 3),
                orientation="landscape",
                footer=(unit, "Стр. &P из &N", f"{start:%d.%m.%Y} — {finish:%d.%m.%Y}"),
            ),
        ]
    )
    return Response(
        content=content,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": (
                f'attachment; filename="duty_schedule_{label}.xlsx"'
            ),
            "Cache-Control": "no-store",
        },
    )


@app.get("/api/settings")
def get_settings() -> dict[str, Any]:
    with db.db() as conn:
        settings = db.load_settings(conn)
    return {"settings": settings_out(settings)}


@app.put("/api/settings")
def update_settings(payload: SettingsIn, request: Request) -> dict[str, Any]:
    data = payload.model_dump(exclude_none=True)
    admin_only = {
        "notifications_enabled", "notify_on_request", "notify_on_decision",
        "notify_on_coverage", "smtp_host", "smtp_port", "smtp_user",
        "smtp_password", "smtp_from", "smtp_tls", "rocketchat_webhook",
        "public_url",
    }
    if admin_only & set(data) and current_user(request)["role"] != "admin":
        raise HTTPException(
            status_code=403, detail="Уведомления настраивает только администратор"
        )

    with db.db() as conn:
        current = db.load_settings(conn)
        updates: dict[str, str] = {}

        if "unit_name" in data:
            name = str(data["unit_name"]).strip()
            if not name or len(name) > 80:
                raise HTTPException(
                    status_code=400, detail="Название подразделения: 1–80 символов"
                )
            updates["unit_name"] = name

        for key in (
            "rest_days", "min_gap_days", "weekend_weight", "fairness_power",
            "comp_enabled", "comp_valid_days", "history_days",
            "request_month_limit", "request_horizon_days", "smtp_port",
        ):
            if key not in data:
                continue
            value = data[key]
            if key == "comp_enabled":
                updates[key] = "1" if bool(value) else "0"
                continue
            kind, low, high = db.SETTINGS_SPEC[key]
            number = float(value) if kind == "float" else int(value)
            if number < low or number > high:
                raise HTTPException(
                    status_code=400,
                    detail=f"Значение {key} должно быть от {low} до {high}",
                )
            updates[key] = str(number)

        for key in (
            "notifications_enabled", "notify_on_request", "notify_on_decision",
            "notify_on_coverage", "smtp_tls",
        ):
            if key in data:
                updates[key] = "1" if bool(data[key]) else "0"

        for key, limit in (
            ("smtp_host", 200), ("smtp_user", 200), ("smtp_from", 200),
            ("rocketchat_webhook", 500), ("public_url", 300),
        ):
            if key in data:
                value = str(data[key]).strip()[:limit]
                if key in ("rocketchat_webhook", "public_url") and value:
                    parsed = urlparse(value)
                    if parsed.scheme not in ("http", "https") or not parsed.netloc:
                        raise HTTPException(
                            status_code=400,
                            detail=(
                                "Адрес вебхука и публичный адрес должны "
                                "начинаться с http:// или https://"
                            ),
                        )
                updates[key] = value

        if "smtp_password" in data and str(data["smtp_password"]):
            updates["smtp_password"] = str(data["smtp_password"])[:200]

        merged = {**current, **updates}
        rest = int(merged["rest_days"])
        gap = int(merged["min_gap_days"])
        if gap < rest + 1:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Минимальный интервал между дежурствами должен быть "
                    f"не меньше {rest + 1} (отсыпной + 1 день)"
                ),
            )
        settings = db.save_settings(conn, updates)
    return {"settings": settings_out(settings)}


@app.get("/api/notifications")
def notifications_list(limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    with db.db() as conn:
        rows = [
            dict(row)
            for row in conn.execute(
                "SELECT id, channel, recipient, subject, event, status, attempts, "
                "last_error, created_at, sent_at FROM notification_outbox "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            )
        ]
        counts = {
            row["status"]: row["count"]
            for row in conn.execute(
                "SELECT status, COUNT(*) AS count FROM notification_outbox GROUP BY status"
            )
        }
    return {
        "notifications": [
            {
                "id": row["id"],
                "channel": row["channel"],
                "recipient": row["recipient"],
                "subject": row["subject"],
                "event": row["event"],
                "status": row["status"],
                "attempts": row["attempts"],
                "error": row["last_error"],
                "createdAt": row["created_at"],
                "sentAt": row["sent_at"],
            }
            for row in rows
        ],
        "counts": {
            "pending": counts.get("pending", 0),
            "sent": counts.get("sent", 0),
            "error": counts.get("error", 0),
        },
    }


@app.post("/api/notifications/test")
def notification_test(
    payload: TestNotificationIn, request: Request
) -> dict[str, Any]:
    user = current_user(request)
    channel = payload.channel
    if channel not in ("email", "rocketchat"):
        raise HTTPException(status_code=400, detail="Некорректный канал")
    with db.db() as conn:
        row = conn.execute(
            "SELECT email, rocketchat FROM users WHERE id = ?", (int(user["id"]),)
        ).fetchone()
    recipient = row["email"] if channel == "email" else row["rocketchat"]
    if not recipient:
        raise HTTPException(
            status_code=400,
            detail=(
                "У вашей учётной записи не заполнен "
                + ("email" if channel == "email" else "Rocket.Chat")
            ),
        )
    result = notifier.send_test(
        channel,
        recipient,
        "Проверка уведомлений",
        "Это тестовое сообщение из системы учёта дежурств.",
    )
    return result


@app.post("/api/notifications/retry")
def notification_retry() -> dict[str, int]:
    return {"sent": notifier.retry_failed()}


@app.exception_handler(sqlite3.IntegrityError)
async def integrity_error_handler(_, exc: sqlite3.IntegrityError) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={"detail": "Конфликт данных: возможно, день уже занят другим дежурством"},
    )


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
