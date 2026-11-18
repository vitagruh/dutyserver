import io
import shutil
import sqlite3
import subprocess
import zipfile
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import db, security
from app.main import app, reset_login_failures


def weekday_on_or_after(start: date, weekday: int) -> date:
    current = start
    while current.weekday() != weekday:
        current += timedelta(days=1)
    return current


MONDAY = weekday_on_or_after(date(2026, 12, 1), 0)
SATURDAY = weekday_on_or_after(MONDAY + timedelta(days=5), 5)
MONTH = MONDAY.strftime("%Y-%m")

TEST_SECRET = "test-session-secret"
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def client():
    reset_login_failures()
    with TestClient(app) as test_client:
        with db.db() as conn:
            for table in (
                "notification_outbox",
                "coverage_alerts",
                "coverage_overrides",
                "coverage_reviews",
                "availability",
                "comp_choices",
                "draws",
                "duties",
                "absence_requests",
                "absences",
                "holidays",
                "users",
                "people",
            ):
                conn.execute(f"DELETE FROM {table}")
            conn.execute("DELETE FROM settings")
            for key, value in db.DEFAULT_SETTINGS.items():
                conn.execute(
                    "INSERT INTO settings(key, value) VALUES(?, ?)", (key, value)
                )
            conn.execute(
                "INSERT INTO settings(key, value) VALUES('session_secret', ?)",
                (TEST_SECRET,),
            )
            conn.execute(
                "INSERT INTO users(username, password_hash, role) VALUES('admin', ?, 'admin')",
                (security.hash_password("admin123"),),
            )
        app.state.session_secret = TEST_SECRET
        response = test_client.post(
            "/api/auth/login", json={"username": "admin", "password": "admin123"}
        )
        assert response.status_code == 200
        yield test_client


def add_person(client: TestClient, name: str) -> int:
    response = client.post("/api/people", json={"name": name})
    assert response.status_code == 200
    return response.json()["person"]["id"]


def add_account(
    client: TestClient,
    person_id: int,
    username: str,
    password: str = "pass1234",
    role: str = "employee",
    email: str = "",
) -> int:
    response = client.post(
        "/api/users",
        json={
            "username": username,
            "password": password,
            "role": role,
            "person_id": person_id,
            "email": email,
        },
    )
    assert response.status_code == 200
    return response.json()["user"]["id"]


def login_as(username: str, password: str = "pass1234") -> TestClient:
    employee = TestClient(app)
    response = employee.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200
    return employee


def test_duty_rest_draw_and_weekend_comp(client: TestClient):
    ivanov = add_person(client, "Иванов")
    petrov = add_person(client, "Петров")
    sidorov = add_person(client, "Сидоров")

    response = client.post(
        "/api/duties", json={"date": MONDAY.isoformat(), "person_id": ivanov}
    )
    assert response.status_code == 200
    duty_id = response.json()["duty"]["id"]

    tuesday = MONDAY + timedelta(days=1)
    blocked = client.post(
        "/api/duties", json={"date": tuesday.isoformat(), "person_id": ivanov}
    )
    assert blocked.status_code == 409
    assert "отсыпной" in blocked.json()["detail"]

    candidates = client.get(
        "/api/candidates", params={"date": tuesday.isoformat()}
    ).json()["candidates"]
    by_id = {item["person_id"]: item for item in candidates}
    assert by_id[ivanov]["eligible"] is False
    assert by_id[petrov]["eligible"] is True
    assert by_id[petrov]["probability"] == pytest.approx(0.5)

    wednesday = MONDAY + timedelta(days=2)
    draw = client.post(
        "/api/draw",
        json={
            "date": wednesday.isoformat(),
            "candidate_ids": [ivanov, petrov],
            "seed": 12345,
        },
    )
    assert draw.status_code == 200
    payload = draw.json()
    assert payload["winner"]["personId"] in (ivanov, petrov)
    assert len(payload["candidates"]) == 2
    assert sum(item["probability"] for item in payload["candidates"]) == pytest.approx(1.0)

    month = client.get("/api/schedule", params={"month": MONTH}).json()
    assert len(month["draws"]) == 1
    assert month["draws"][0]["seed"] == 12345

    weekend = client.post(
        "/api/duties", json={"date": SATURDAY.isoformat(), "person_id": sidorov}
    )
    assert weekend.status_code == 200
    weekend_duty_id = weekend.json()["duty"]["id"]

    comps = client.get("/api/comps").json()
    entitlement = next(
        item for item in comps["comps"] if item["duty_id"] == weekend_duty_id
    )
    assert entitlement["status"] == "pending"

    comp_date = SATURDAY + timedelta(days=2)
    scheduled = client.put(
        f"/api/comps/{weekend_duty_id}",
        json={"status": "scheduled", "date": comp_date.isoformat()},
    )
    assert scheduled.status_code == 200
    assert scheduled.json()["comp"]["status"] == "scheduled"

    blocked_by_comp = client.post(
        "/api/duties", json={"date": comp_date.isoformat(), "person_id": sidorov}
    )
    assert blocked_by_comp.status_code == 409
    assert "отгул" in blocked_by_comp.json()["detail"]

    absence_conflict = client.post(
        "/api/absences",
        json={
            "person_id": sidorov,
            "date_from": SATURDAY.isoformat(),
            "date_to": (SATURDAY + timedelta(days=1)).isoformat(),
            "kind": "vacation",
        },
    )
    assert absence_conflict.status_code == 409

    removed = client.delete(f"/api/duties/{weekend_duty_id}")
    assert removed.status_code == 200
    assert client.get("/api/comps").json()["comps"] == []

    absence = client.post(
        "/api/absences",
        json={
            "person_id": sidorov,
            "date_from": SATURDAY.isoformat(),
            "date_to": (SATURDAY + timedelta(days=1)).isoformat(),
            "kind": "vacation",
        },
    )
    assert absence.status_code == 200

    schedule = client.get("/api/schedule", params={"month": MONTH}).json()
    saturday_day = next(day for day in schedule["days"] if day["date"] == SATURDAY.isoformat())
    assert saturday_day["duty"] is None
    assert len(saturday_day["absences"]) == 1
    assert client.get("/api/duties").status_code == 405  # no list endpoint, sanity check


def test_auto_plan_fills_empty_days_and_runs_once(client: TestClient):
    for name in ("Иванов", "Петров", "Сидоров"):
        add_person(client, name)
    finish = MONDAY + timedelta(days=20)

    first = client.post(
        "/api/auto-plan",
        json={
            "date_from": MONDAY.isoformat(),
            "date_to": finish.isoformat(),
            "seed": 7,
        },
    )
    assert first.status_code == 200
    assert first.json()["count"] == 21

    with db.db() as conn:
        rows = [dict(row) for row in conn.execute("SELECT * FROM duties")]
    by_person: dict[int, list[date]] = {}
    for row in rows:
        by_person.setdefault(row["person_id"], []).append(date.fromisoformat(row["date"]))
    for dates in by_person.values():
        dates.sort()
        for earlier, later in zip(dates, dates[1:]):
            assert (later - earlier).days >= 2

    second = client.post(
        "/api/auto-plan",
        json={
            "date_from": MONDAY.isoformat(),
            "date_to": finish.isoformat(),
            "seed": 8,
        },
    )
    assert second.status_code == 200
    assert second.json()["count"] == 0
    assert all(
        item["reason"] == "день уже занят" for item in second.json()["skipped"]
    )


def test_settings_validation_and_comp_switch(client: TestClient):
    invalid = client.put(
        "/api/settings", json={"rest_days": 1, "min_gap_days": 1}
    )
    assert invalid.status_code == 400
    assert "интервал" in invalid.json()["detail"]

    updated = client.put("/api/settings", json={"weekend_weight": 2.0})
    assert updated.status_code == 200
    assert updated.json()["settings"]["weekend_weight"] == 2.0

    disabled = client.put("/api/settings", json={"comp_enabled": False})
    assert disabled.status_code == 200
    assert disabled.json()["settings"]["comp_enabled"] is False
    assert client.get("/api/comps").json()["compEnabled"] is False


def test_belarus_holidays_autoseeded_and_deletions_kept(client: TestClient):
    from app.holidays import belarus_holidays
    from app.main import ensure_belarus_holidays

    year = date.today().year
    with db.db() as conn:
        conn.execute("DELETE FROM holidays")
        conn.execute("DELETE FROM settings WHERE key = 'holidays_seeded_years'")

    ensure_belarus_holidays()
    dates = {item["date"] for item in client.get("/api/holidays").json()["holidays"]}
    expected = {day.isoformat() for day, _ in belarus_holidays(year)}
    assert expected <= dates
    assert len([item for item in dates if item.startswith(f"{year}-")]) == len(expected)

    removed = sorted(expected)[0]
    assert client.delete(f"/api/holidays/{removed}").status_code == 200
    ensure_belarus_holidays()
    dates_after = {
        item["date"] for item in client.get("/api/holidays").json()["holidays"]
    }
    assert removed not in dates_after


def test_holidays_seed_and_stats(client: TestClient):
    add_person(client, "Иванов")
    seeded = client.post("/api/holidays/seed", json={"year": 2026})
    assert seeded.status_code == 200
    assert seeded.json()["inserted"] > 5
    dates = [item["date"] for item in seeded.json()["holidays"]]
    assert "2026-04-21" in dates

    stats = client.get("/api/stats").json()
    assert stats["totals"]["people"] == 1
    assert len(stats["stats"]) == 1

    export = client.get("/api/export", params={"month": "2026-12"})
    assert export.status_code == 200
    assert export.text.startswith("\ufeff")
    assert "Дата;День недели" in export.text


def test_employee_account_requests_flow(client: TestClient):
    ivanov = add_person(client, "Иванов")
    add_account(client, ivanov, "ivanov")
    employee = login_as("ivanov")

    assert employee.get("/api/schedule").status_code == 403
    assert employee.get("/api/users").status_code == 403
    assert client.get("/me", follow_redirects=False).status_code == 303

    personal = employee.get("/api/me").json()
    assert personal["person"]["id"] == ivanov
    assert personal["user"]["username"] == "ivanov"
    assert personal["monthLimit"] >= 0

    days = [MONDAY, MONDAY + timedelta(days=2)]
    created = employee.post(
        "/api/me/requests",
        json={
            "dates": [day.isoformat() for day in days],
            "kind": "unavailable",
            "reason": "семейные обстоятельства",
        },
    )
    assert created.status_code == 200
    items = created.json()["created"]
    assert len(items) == 2
    assert all(item["status"] == "pending" for item in items)

    schedule = client.get("/api/schedule", params={"month": MONTH}).json()
    assert schedule["requestSummary"]["pending"] == 2
    monday = next(day for day in schedule["days"] if day["date"] == MONDAY.isoformat())
    assert monday["requests"][0]["personName"] == "Иванов"

    candidates = {
        item["person_id"]: item
        for item in client.get(
            "/api/candidates", params={"date": MONDAY.isoformat()}
        ).json()["candidates"]
    }
    assert candidates[ivanov]["eligible"] is True
    assert any("ждёт согласования" in note for note in candidates[ivanov]["warnings"])

    for item in items:
        response = client.patch(
            f"/api/requests/{item['id']}", json={"status": "approved"}
        )
        assert response.status_code == 200

    candidates = {
        item["person_id"]: item
        for item in client.get(
            "/api/candidates", params={"date": MONDAY.isoformat()}
        ).json()["candidates"]
    }
    assert candidates[ivanov]["eligible"] is False
    assert "не может дежурить" in "; ".join(candidates[ivanov]["reasons"])

    assert employee.post(
        "/api/me/requests", json={"dates": [MONDAY.isoformat()]}
    ).status_code == 409
    assert employee.delete(
        f"/api/me/requests/{items[0]['id']}"
    ).status_code == 409

    second = employee.post(
        "/api/me/requests",
        json={"dates": [(MONDAY + timedelta(days=5)).isoformat()]},
    )
    assert second.status_code == 200
    pending_id = second.json()["created"][0]["id"]
    assert employee.delete(f"/api/me/requests/{pending_id}").status_code == 200
    assert client.delete(f"/api/requests/{items[1]['id']}").status_code == 200


def test_request_limits_and_horizon(client: TestClient):
    ivanov = add_person(client, "Иванов")
    add_account(client, ivanov, "ivanov")
    employee = login_as("ivanov")

    updated = client.put("/api/settings", json={"request_month_limit": 2})
    assert updated.status_code == 200

    days = [MONDAY + timedelta(days=offset) for offset in (0, 2, 4)]
    over_limit = employee.post(
        "/api/me/requests",
        json={"dates": [day.isoformat() for day in days]},
    )
    assert over_limit.status_code == 409
    assert "Лимит" in over_limit.json()["detail"]

    past = date.today() - timedelta(days=1)
    past_response = employee.post(
        "/api/me/requests", json={"dates": [past.isoformat()]}
    )
    assert past_response.status_code == 400

    far = date.today() + timedelta(days=120)
    far_response = employee.post(
        "/api/me/requests", json={"dates": [far.isoformat()]}
    )
    assert far_response.status_code == 400
    assert "90" in far_response.json()["detail"]


def test_approval_blocked_by_existing_duty(client: TestClient):
    ivanov = add_person(client, "Иванов")
    add_person(client, "Петров")
    add_account(client, ivanov, "ivanov")
    employee = login_as("ivanov")

    created = employee.post(
        "/api/me/requests", json={"dates": [MONDAY.isoformat()]}
    )
    request_id = created.json()["created"][0]["id"]

    duty = client.post(
        "/api/duties", json={"date": MONDAY.isoformat(), "person_id": ivanov}
    )
    assert duty.status_code == 200

    blocked = client.patch(
        f"/api/requests/{request_id}", json={"status": "approved"}
    )
    assert blocked.status_code == 409
    assert "дежурство" in blocked.json()["detail"]

    declined = client.patch(
        f"/api/requests/{request_id}", json={"status": "declined"}
    )
    assert declined.status_code == 200

    candidates = {
        item["person_id"]: item
        for item in client.get(
            "/api/candidates", params={"date": MONDAY.isoformat()}
        ).json()["candidates"]
    }
    assert candidates[ivanov]["reasons"] == ["в этот день уже назначено дежурство"]


def test_employee_absence_request_for_vacation_period(client: TestClient):
    ivanov = add_person(client, "Иванов")
    add_person(client, "Петров")
    add_account(client, ivanov, "ivanov")
    employee = login_as("ivanov")

    start = MONDAY
    finish = MONDAY + timedelta(days=4)
    created = employee.post(
        "/api/me/absences",
        json={
            "date_from": start.isoformat(),
            "date_to": finish.isoformat(),
            "kind": "vacation",
            "reason": "плановый отпуск",
        },
    )
    assert created.status_code == 200
    request = created.json()["request"]
    assert request["origin"] == "absence"
    assert request["status"] == "pending"
    assert request["days"] == 5
    assert request["kindLabel"] == "Отпуск"
    request_id = request["id"]

    overlapping = employee.post(
        "/api/me/absences",
        json={
            "date_from": (start + timedelta(days=1)).isoformat(),
            "date_to": (start + timedelta(days=2)).isoformat(),
            "kind": "trip",
        },
    )
    assert overlapping.status_code == 409

    personal = employee.get("/api/me").json()
    assert [item["id"] for item in personal["absenceRequests"]] == [request_id]
    assert personal["absences"] == []

    listing = client.get("/api/requests").json()
    absence_item = next(
        item for item in listing["requests"] if item["origin"] == "absence"
    )
    assert absence_item["personName"] == "Иванов"
    assert listing["kindLabels"]["vacation"] == "Отпуск"
    schedule = client.get("/api/schedule", params={"month": MONTH}).json()
    assert schedule["requestSummary"]["pending"] == 1

    assert employee.patch(
        f"/api/absence-requests/{request_id}", json={"status": "approved"}
    ).status_code == 403

    approved = client.patch(
        f"/api/absence-requests/{request_id}", json={"status": "approved"}
    )
    assert approved.status_code == 200
    assert approved.json()["request"]["status"] == "approved"
    with db.db() as conn:
        absence = conn.execute(
            "SELECT date_from, date_to, kind FROM absences WHERE person_id = ?",
            (ivanov,),
        ).fetchone()
    assert absence is not None
    assert (absence["date_from"], absence["date_to"]) == (
        start.isoformat(),
        finish.isoformat(),
    )
    assert absence["kind"] == "vacation"

    candidates = {
        item["person_id"]: item
        for item in client.get(
            "/api/candidates", params={"date": start.isoformat()}
        ).json()["candidates"]
    }
    assert candidates[ivanov]["eligible"] is False
    assert any("отсутствие" in reason for reason in candidates[ivanov]["reasons"])
    personal = employee.get("/api/me").json()
    assert personal["absences"][0]["kindLabel"] == "Отпуск"

    declined = client.patch(
        f"/api/absence-requests/{request_id}", json={"status": "declined"}
    )
    assert declined.status_code == 200
    with db.db() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM absences WHERE person_id = ?", (ivanov,)
        ).fetchone()[0] == 0
    candidates = {
        item["person_id"]: item
        for item in client.get(
            "/api/candidates", params={"date": start.isoformat()}
        ).json()["candidates"]
    }
    assert candidates[ivanov]["eligible"] is True

    duty = client.post(
        "/api/duties", json={"date": start.isoformat(), "person_id": ivanov}
    )
    assert duty.status_code == 200
    duty_id = duty.json()["duty"]["id"]
    conflict = employee.post(
        "/api/me/absences",
        json={
            "date_from": start.isoformat(),
            "date_to": finish.isoformat(),
            "kind": "trip",
        },
    )
    assert conflict.status_code == 200
    conflict_id = conflict.json()["request"]["id"]
    blocked = client.patch(
        f"/api/absence-requests/{conflict_id}",
        json={"status": "approved"},
    )
    assert blocked.status_code == 409
    assert "дежурство" in blocked.json()["detail"]

    assert employee.delete(f"/api/me/absences/{conflict_id}").status_code == 200
    assert employee.delete(f"/api/me/absences/{conflict_id}").status_code == 404

    assert employee.post(
        "/api/me/absences",
        json={
            "date_from": (date.today() + timedelta(days=120)).isoformat(),
            "date_to": (date.today() + timedelta(days=121)).isoformat(),
        },
    ).status_code == 400
    assert employee.post(
        "/api/me/absences",
        json={"date_from": finish.isoformat(), "date_to": start.isoformat()},
    ).status_code == 400

    assert client.delete(f"/api/duties/{duty_id}").status_code == 200
    second = employee.post(
        "/api/me/absences",
        json={
            "date_from": start.isoformat(),
            "date_to": finish.isoformat(),
            "kind": "trip",
        },
    )
    assert second.status_code == 200
    second_id = second.json()["request"]["id"]
    assert client.patch(
        f"/api/absence-requests/{second_id}", json={"status": "approved"}
    ).status_code == 200
    assert client.delete(f"/api/absence-requests/{second_id}").status_code == 200
    with db.db() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM absences WHERE person_id = ?", (ivanov,)
        ).fetchone()[0] == 0


def test_auto_plan_respects_requests(client: TestClient):
    ivanov = add_person(client, "Иванов")
    petrov = add_person(client, "Петров")
    add_account(client, ivanov, "ivanov")
    add_account(client, petrov, "petrov")
    ivanov_client = login_as("ivanov")
    petrov_client = login_as("petrov")

    earlier = MONDAY - timedelta(days=3)
    assert client.post(
        "/api/duties", json={"date": earlier.isoformat(), "person_id": ivanov}
    ).status_code == 200

    preferred = petrov_client.post(
        "/api/me/requests",
        json={"dates": [MONDAY.isoformat()], "kind": "preferred"},
    )
    assert client.patch(
        f"/api/requests/{preferred.json()['created'][0]['id']}",
        json={"status": "approved"},
    ).status_code == 200

    wednesday = MONDAY + timedelta(days=2)
    unavailable = ivanov_client.post(
        "/api/me/requests",
        json={"dates": [wednesday.isoformat()], "kind": "unavailable"},
    )
    assert client.patch(
        f"/api/requests/{unavailable.json()['created'][0]['id']}",
        json={"status": "approved"},
    ).status_code == 200
    petrov_pref_wed = petrov_client.post(
        "/api/me/requests",
        json={"dates": [wednesday.isoformat()], "kind": "preferred"},
    )
    assert client.patch(
        f"/api/requests/{petrov_pref_wed.json()['created'][0]['id']}",
        json={"status": "approved"},
    ).status_code == 200

    first = client.post(
        "/api/auto-plan",
        json={
            "date_from": MONDAY.isoformat(),
            "date_to": MONDAY.isoformat(),
            "seed": 3,
        },
    )
    assert first.status_code == 200
    assert first.json()["assigned"][0]["person_id"] == ivanov

    second = client.post(
        "/api/auto-plan",
        json={
            "date_from": wednesday.isoformat(),
            "date_to": wednesday.isoformat(),
            "seed": 3,
        },
    )
    assert second.status_code == 200
    assert second.json()["assigned"][0]["person_id"] == petrov

    friday = MONDAY + timedelta(days=4)
    for employee in (ivanov_client, petrov_client):
        blocked = employee.post(
            "/api/me/requests",
            json={"dates": [friday.isoformat()], "kind": "unavailable"},
        )
        assert client.patch(
            f"/api/requests/{blocked.json()['created'][0]['id']}",
            json={"status": "approved"},
        ).status_code == 200

    empty = client.post(
        "/api/auto-plan",
        json={
            "date_from": friday.isoformat(),
            "date_to": friday.isoformat(),
            "seed": 3,
        },
    )
    assert empty.status_code == 200
    assert empty.json()["count"] == 0
    assert empty.json()["skipped"][0]["reason"] == "нет доступных сотрудников"


def test_rbac_login_roles_and_password_change(client: TestClient):
    anonymous = TestClient(app)
    assert anonymous.get("/api/schedule").status_code == 401
    assert anonymous.get("/api/me").status_code == 401
    assert anonymous.get("/", follow_redirects=False).status_code == 303
    assert anonymous.get("/login").status_code == 200
    assert anonymous.post(
        "/api/auth/login", json={"username": "admin", "password": "wrong"}
    ).status_code == 401

    ivanov = add_person(client, "Иванов")
    add_account(client, ivanov, "ivanov")
    employee = login_as("ivanov")
    assert employee.get("/me").status_code == 200
    assert employee.get("/api/me").status_code == 200
    assert employee.get("/api/coverage").status_code == 403

    lead_person = add_person(client, "Петров")
    add_account(client, lead_person, "lead", role="teamlead")
    lead = login_as("lead")
    assert lead.get("/api/schedule").status_code == 200
    assert lead.get("/api/coverage").status_code == 200
    assert lead.get("/api/users").status_code == 403
    assert lead.get("/api/notifications").status_code == 403

    assert client.get("/api/users").status_code == 200
    assert client.get("/api/notifications").status_code == 200

    wrong = employee.post(
        "/api/auth/password",
        json={"current_password": "wrong", "new_password": "newpass123"},
    )
    assert wrong.status_code == 400
    changed = employee.post(
        "/api/auth/password",
        json={"current_password": "pass1234", "new_password": "newpass123"},
    )
    assert changed.status_code == 200
    assert employee.get("/api/me").status_code == 200

    employee.post("/api/auth/logout")
    assert employee.get("/api/me").status_code == 401


def test_coverage_gap_dismiss_and_override(client: TestClient):
    ivanov = add_person(client, "Иванов")
    add_account(client, ivanov, "ivanov")

    absence = client.post(
        "/api/absences",
        json={
            "person_id": ivanov,
            "date_from": MONDAY.isoformat(),
            "date_to": MONDAY.isoformat(),
            "kind": "vacation",
        },
    )
    assert absence.status_code == 200

    gaps = client.get(
        "/api/coverage",
        params={"date_from": MONDAY.isoformat(), "date_to": MONDAY.isoformat()},
    ).json()
    assert gaps["count"] == 1
    day = gaps["days"][0]
    assert day["date"] == MONDAY.isoformat()
    assert day["weekdayName"] == "Понедельник"
    assert "Иванов" in day["absents"]
    assert day["reasons"]

    dismissed = client.post(
        f"/api/coverage/{MONDAY.isoformat()}/dismiss", json={"note": "закрыли вручную"}
    )
    assert dismissed.status_code == 200
    after = client.get(
        "/api/coverage",
        params={"date_from": MONDAY.isoformat(), "date_to": MONDAY.isoformat()},
    ).json()
    assert after["count"] == 0
    assert after["reviewed"][0]["note"] == "закрыли вручную"

    assert client.delete(f"/api/coverage/{MONDAY.isoformat()}").status_code == 200

    short_reason = client.post(
        f"/api/coverage/{MONDAY.isoformat()}/assign",
        json={"person_id": ivanov, "reason": "ок"},
    )
    assert short_reason.status_code == 400

    assigned = client.post(
        f"/api/coverage/{MONDAY.isoformat()}/assign",
        json={"person_id": ivanov, "reason": "крайняя необходимость"},
    )
    assert assigned.status_code == 200
    assert assigned.json()["duty"]["personId"] == ivanov
    assert assigned.json()["warnings"]

    final = client.get(
        "/api/coverage",
        params={"date_from": MONDAY.isoformat(), "date_to": MONDAY.isoformat()},
    ).json()
    assert final["count"] == 0
    assert final["overrides"][0]["person_name"] == "Иванов"


def test_coverage_rescue_candidates_with_coefficient(client: TestClient):
    ivanov = add_person(client, "Иванов")
    petrov = add_person(client, "Петров")
    assert client.post(
        "/api/duties", json={"date": MONDAY.isoformat(), "person_id": ivanov}
    ).status_code == 200
    tuesday = MONDAY + timedelta(days=1)
    assert client.post(
        "/api/absences",
        json={
            "person_id": petrov,
            "date_from": tuesday.isoformat(),
            "date_to": tuesday.isoformat(),
            "kind": "vacation",
        },
    ).status_code == 200

    gaps = client.get(
        "/api/coverage",
        params={"date_from": tuesday.isoformat(), "date_to": tuesday.isoformat()},
    ).json()
    assert gaps["count"] == 1
    day = gaps["days"][0]
    pool = {item["personId"]: item for item in day["candidates"]}
    assert set(pool) == {ivanov, petrov}
    assert any("отсыпной" in item for item in pool[ivanov]["conflicts"])
    assert any("отпуск" in item for item in pool[petrov]["conflicts"])
    assert all(item["weight"] > 0 for item in pool.values())
    assert sum(item["probability"] for item in pool.values()) == pytest.approx(1.0)
    assert day["candidates"][0]["personId"] == petrov

    assigned = client.post(
        f"/api/coverage/{tuesday.isoformat()}/assign",
        json={"person_id": petrov, "reason": "сотрудник дал согласие"},
    )
    assert assigned.status_code == 200
    assert assigned.json()["duty"]["personId"] == petrov
    assert any("отпуск" in item for item in assigned.json()["warnings"])


def test_stats_weekday_matrix_by_person(client: TestClient):
    ivanov = add_person(client, "Иванов")
    petrov = add_person(client, "Петров")
    assert client.post(
        "/api/duties", json={"date": MONDAY.isoformat(), "person_id": ivanov}
    ).status_code == 200
    assert client.post(
        "/api/duties", json={"date": SATURDAY.isoformat(), "person_id": petrov}
    ).status_code == 200

    stats = client.get("/api/stats").json()
    rows = {item["id"]: item for item in stats["stats"]}
    assert rows[ivanov]["byWeekday"] == [1, 0, 0, 0, 0, 0, 0]
    assert rows[petrov]["byWeekday"] == [0, 0, 0, 0, 0, 1, 0]
    assert stats["weekdays"][0]["total"] == 1
    assert stats["weekdays"][5]["total"] == 1
    assert stats["weekdays"][1]["total"] == 0


def test_export_schedule_xlsx_for_print(client: TestClient):
    ivanov = add_person(client, "Иванов")
    assert client.post(
        "/api/duties", json={"date": MONDAY.isoformat(), "person_id": ivanov}
    ).status_code == 200

    response = client.get(
        "/api/export/schedule.xlsx", params={"month": MONTH}
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "duty_schedule_" in response.headers["content-disposition"]
    assert response.content[:2] == b"PK"

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = set(archive.namelist())
        assert "xl/worksheets/sheet1.xml" in names
        assert "xl/worksheets/sheet2.xml" in names
        assert "xl/styles.xml" in names
        matrix = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
        assert "ТАБЛИЦА ДЕЖУРСТВ: ФИО / ДАТА" in matrix
        assert "Иванов" in matrix
        assert "Пн" in matrix
        assert 's="15"' in matrix
        assert 's="11"' in matrix
        assert 'xSplit="1"' in matrix
        assert 'scale="65"' in matrix
        listing = archive.read("xl/worksheets/sheet2.xml").decode("utf-8")
        assert "ГРАФИК СУТОЧНЫХ ДЕЖУРСТВ" in listing
        assert "Понедельник" in listing
        assert 'orientation="landscape"' in listing
        assert 'fitToWidth="1"' in listing
        workbook = archive.read("xl/workbook.xml").decode("utf-8")
        assert workbook.count("_xlnm.Print_Titles") == 2

    assert client.get(
        "/api/export/schedule.xlsx", params={"month": "2026-13"}
    ).status_code == 400


def test_export_schedule_bw_xlsx_with_legend_and_absences(client: TestClient):
    ivanov = add_person(client, "Иванов")
    petrov = add_person(client, "Петров")
    sidorov = add_person(client, "Сидоров")
    assert client.post(
        "/api/duties", json={"date": MONDAY.isoformat(), "person_id": ivanov}
    ).status_code == 200
    absence_period = {
        "date_from": MONDAY.isoformat(),
        "date_to": (MONDAY + timedelta(days=1)).isoformat(),
    }
    assert client.post(
        "/api/absences",
        json={"person_id": petrov, "kind": "vacation", **absence_period},
    ).status_code == 200
    assert client.post(
        "/api/absences",
        json={"person_id": sidorov, "kind": "trip", **absence_period},
    ).status_code == 200
    assert client.post(
        "/api/holidays",
        json={"date": MONDAY.isoformat(), "name": "Тестовый праздник"},
    ).status_code == 200

    response = client.get(
        "/api/export/schedule-bw.xlsx", params={"month": MONTH}
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "duty_schedule_bw_" in response.headers["content-disposition"]
    assert response.content[:2] == b"PK"

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        styles = archive.read("xl/styles.xml").decode("utf-8")
        assert 'patternType="lightUp"' in styles
        assert "FFE7E7E7" in styles
        assert "FFD9D9D9" in styles
        matrix = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
        assert "ГРАФИК СУТОЧНЫХ ДЕЖУРСТВ — ЧБ ДЛЯ ПЕЧАТИ" in matrix
        assert "Условные обозначения" in matrix
        assert "Д — дежурство" in matrix
        assert "О — отпуск" in matrix
        assert "К — командировка" in matrix
        assert "Б — болезнь" in matrix
        assert "серая заливка" in matrix
        assert "Иванов" in matrix
        assert "Петров" in matrix
        assert "Сидоров" in matrix
        assert ">Д</t>" in matrix
        assert ">О</t>" in matrix
        assert ">К</t>" in matrix
        assert 's="23"' in matrix
        assert 's="25"' in matrix
        assert 's="26"' in matrix
        assert 'xSplit="1"' in matrix
        assert 'scale="62"' in matrix
        listing = archive.read("xl/worksheets/sheet2.xml").decode("utf-8")
        assert "СПИСОК ДЕЖУРСТВ И ОТСУТСТВИЙ — ЧБ ДЛЯ ПЕЧАТИ" in listing
        assert "Тестовый праздник" in listing
        assert "Выходной" in listing
        assert "Петров — отпуск" in listing
        assert "Сидоров — командировка" in listing
        assert 'orientation="landscape"' in listing
        assert 'fitToWidth="1"' in listing
        workbook = archive.read("xl/workbook.xml").decode("utf-8")
        assert "ФИО-Дата ЧБ" in workbook
        assert "Список ЧБ" in workbook
        assert workbook.count("_xlnm.Print_Titles") == 2

    assert client.get(
        "/api/export/schedule-bw.xlsx", params={"month": "2026-13"}
    ).status_code == 400


def test_backup_download_admin_only(client: TestClient, tmp_path):
    ivanov = add_person(client, "Иванов")

    response = client.get("/api/backup")
    assert response.status_code == 200
    assert response.content.startswith(b"SQLite format 3\x00")
    assert response.content[18:20] == b"\x01\x01"
    assert "duty_backup_" in response.headers["content-disposition"]
    assert response.headers["cache-control"] == "no-store"

    backup_path = tmp_path / "duty_backup.db"
    backup_path.write_bytes(response.content)
    copy = sqlite3.connect(backup_path)
    try:
        assert copy.execute("PRAGMA journal_mode").fetchone() == ("delete",)
        assert copy.execute("SELECT name FROM people").fetchall() == [("Иванов",)]
    finally:
        copy.close()

    add_account(client, ivanov, "ivanov")
    employee = login_as("ivanov")
    assert employee.get("/api/backup").status_code == 403

    petrov = add_person(client, "Петров")
    add_account(client, petrov, "petrov", role="teamlead")
    teamlead = login_as("petrov")
    assert teamlead.get("/api/backup").status_code == 403


def test_extended_stats_weekdays_months_and_totals(client: TestClient):
    ivanov = add_person(client, "Иванов")
    assert client.post(
        "/api/duties", json={"date": MONDAY.isoformat(), "person_id": ivanov}
    ).status_code == 200

    stats = client.get("/api/stats").json()
    assert len(stats["weekdays"]) == 7
    assert len(stats["months"]) == 12
    assert stats["weekdays"][0]["name"] == "Понедельник"
    assert stats["weekdays"][0]["total"] == 1
    assert stats["weekdays"][-1]["name"] == "Воскресенье"
    assert stats["totals"]["duties"] == 1
    assert {
        "requestsPending",
        "coverageGaps",
        "compsPending",
    } <= set(stats["totals"])
    assert {"open", "dismissed", "overrides"} <= set(stats["coverage"])
    assert stats["coverage"]["horizonDays"] > 0
    assert stats["coverage"]["unassigned"] >= 0
    assert "draws" in stats and "compsScheduled" in stats["totals"]
    for person in stats["stats"]:
        assert len(person["byMonth"]) == len(stats["months"])
        assert 0.0 <= person["weekendShare"] <= 1.0
    assert set(stats["requests"]) == {
        "pending",
        "approved",
        "declined",
        "unavailable",
        "preferred",
    }


def test_notifications_outbox_flags_and_test_send(client: TestClient):
    ivanov = add_person(client, "Иванов")
    add_account(client, ivanov, "ivanov", email="ivanov@example.by")
    employee = login_as("ivanov")

    employee.post("/api/me/requests", json={"dates": [MONDAY.isoformat()]})
    assert client.get("/api/notifications").json()["notifications"] == []

    enabled = client.put(
        "/api/settings", json={"notifications_enabled": True}
    )
    assert enabled.status_code == 200

    with db.db() as conn:
        conn.execute(
            "UPDATE users SET email = 'lead@example.by' WHERE username = 'admin'"
        )

    employee.post(
        "/api/me/requests",
        json={"dates": [(MONDAY + timedelta(days=2)).isoformat()]},
    )
    journal = client.get("/api/notifications").json()["notifications"]
    assert len(journal) >= 1
    assert journal[0]["event"] == "request_created"
    assert journal[0]["recipient"] == "lead@example.by"
    assert journal[0]["status"] in ("pending", "error")

    test = client.post("/api/notifications/test", json={"channel": "email"})
    assert test.status_code == 200
    assert test.json()["status"] == "error"
    assert "SMTP" in test.json()["error"]

    retried = client.post("/api/notifications/retry")
    assert retried.status_code == 200
    assert "sent" in retried.json()


def test_roulette_month_mode_weights_by_month_duties(client: TestClient):
    ivanov = add_person(client, "Иванов")
    petrov = add_person(client, "Петров")
    sidorov = add_person(client, "Сидоров")
    for offset, person in ((0, ivanov), (7, ivanov), (1, petrov)):
        created = client.post(
            "/api/duties",
            json={
                "date": (MONDAY + timedelta(days=offset)).isoformat(),
                "person_id": person,
            },
        )
        assert created.status_code == 200

    target = MONDAY + timedelta(days=21)
    preview = client.get("/api/roulette", params={"date": target.isoformat()})
    assert preview.status_code == 200
    data = preview.json()
    assert data["month"] == MONTH
    assert data["duty"] is None
    by_name = {item["person_name"]: item for item in data["candidates"]}
    assert by_name["Иванов"]["month_duties"] == 2
    assert by_name["Петров"]["month_duties"] == 1
    assert by_name["Сидоров"]["month_duties"] == 0
    for candidate in data["candidates"]:
        assert candidate["equal_probability"] == pytest.approx(1 / 3, abs=1e-4)
    assert by_name["Иванов"]["month_probability"] == pytest.approx(1 / 14, abs=1e-4)
    assert by_name["Петров"]["month_probability"] == pytest.approx(4 / 14, abs=1e-4)
    assert by_name["Сидоров"]["month_probability"] == pytest.approx(9 / 14, abs=1e-4)

    draw = client.post(
        "/api/draw",
        json={
            "date": target.isoformat(),
            "candidate_ids": [ivanov, petrov, sidorov],
            "mode": "month",
            "seed": 777,
        },
    )
    assert draw.status_code == 200
    result = draw.json()
    assert result["mode"] == "month"
    probs = {item["personId"]: item["probability"] for item in result["candidates"]}
    assert probs[ivanov] == pytest.approx(1 / 14, abs=1e-4)
    assert probs[petrov] == pytest.approx(4 / 14, abs=1e-4)
    assert probs[sidorov] == pytest.approx(9 / 14, abs=1e-4)
    assert sum(probs.values()) == pytest.approx(1.0)

    schedule = client.get("/api/schedule", params={"month": MONTH}).json()
    assert schedule["draws"][0]["seed"] == 777
    duty = next(
        day["duty"] for day in schedule["days"] if day["date"] == target.isoformat()
    )
    assert duty["personName"] == result["winner"]["personName"]
    assert "Рулетка" in duty["note"]


def test_roulette_equal_mode_ignores_duties(client: TestClient):
    ivanov = add_person(client, "Иванов")
    petrov = add_person(client, "Петров")
    sidorov = add_person(client, "Сидоров")
    for offset, person in ((0, ivanov), (1, petrov)):
        created = client.post(
            "/api/duties",
            json={
                "date": (MONDAY + timedelta(days=offset)).isoformat(),
                "person_id": person,
            },
        )
        assert created.status_code == 200

    target = MONDAY + timedelta(days=21)
    data = client.get(
        "/api/roulette", params={"date": target.isoformat()}
    ).json()
    by_name = {item["person_name"]: item for item in data["candidates"]}
    assert by_name["Сидоров"]["month_probability"] > by_name["Иванов"]["month_probability"]
    for candidate in data["candidates"]:
        assert candidate["equal_probability"] == pytest.approx(1 / 3, abs=1e-4)

    draw = client.post(
        "/api/draw",
        json={
            "date": target.isoformat(),
            "candidate_ids": [ivanov, petrov, sidorov],
            "mode": "equal",
            "seed": 99,
        },
    )
    assert draw.status_code == 200
    result = draw.json()
    assert result["mode"] == "equal"
    for candidate in result["candidates"]:
        assert candidate["probability"] == pytest.approx(1 / 3, abs=1e-4)
    schedule = client.get("/api/schedule", params={"month": MONTH}).json()
    duty = next(
        day["duty"] for day in schedule["days"] if day["date"] == target.isoformat()
    )
    assert "равные шансы" in duty["note"]

    invalid = client.post(
        "/api/draw",
        json={
            "date": (target + timedelta(days=40)).isoformat(),
            "mode": "bogus",
            "seed": 1,
        },
    )
    assert invalid.status_code == 400


def test_draw_proof_is_verifiable_and_linked(client: TestClient):
    ivanov = add_person(client, "Иванов")
    petrov = add_person(client, "Петров")

    drawn = client.post(
        "/api/draw",
        json={
            "date": MONDAY.isoformat(),
            "candidate_ids": [ivanov, petrov],
            "seed": 4242,
        },
    )
    assert drawn.status_code == 200
    result = drawn.json()
    draw_id = result["drawId"]
    assert result["seed"] == 4242
    assert 0.0 <= result["roll"] < 1.0
    assert len(result["proofHash"]) == 64
    assert result["proofUrl"] == f"/proof/{draw_id}"

    proof = client.get(f"/api/proof/{draw_id}")
    assert proof.status_code == 200
    record = proof.json()
    assert record["available"] is True
    assert record["verified"] is True
    assert record["proofHash"] == result["proofHash"]
    assert set(record["checks"].values()) == {True}
    assert record["winnerId"] == result["winner"]["personId"]
    assert record["replayedWinnerId"] == result["winner"]["personId"]
    assert record["totalWeight"] > 0
    winner_interval = next(
        item
        for item in record["intervals"]
        if item["personId"] == result["winner"]["personId"]
    )
    assert winner_interval["from"] <= record["threshold"] < winner_interval["to"]

    page = client.get(f"/proof/{draw_id}")
    assert page.status_code == 200
    assert "Пруф жеребьёвки" in page.text
    assert result["proofHash"] in page.text
    assert "/static/i18n.js" in page.text
    assert "data-lang-toggle" in page.text
    assert client.get("/proof/999999").status_code == 404
    assert client.get("/api/proof/999999").status_code == 404


def test_legacy_draw_without_proof_stays_viewable(client: TestClient):
    ivanov = add_person(client, "Иванов")
    with db.db() as conn:
        cursor = conn.execute(
            "INSERT INTO draws(date, seed, winner_id, candidates) VALUES(?, ?, ?, ?)",
            (MONDAY.isoformat(), 7, ivanov, "[]"),
        )
        draw_id = cursor.lastrowid

    record = client.get(f"/api/proof/{draw_id}")
    assert record.status_code == 200
    data = record.json()
    assert data["available"] is False
    assert data.get("verified") is None
    assert "пруф" in data["reason"].lower()
    assert client.get(f"/proof/{draw_id}").status_code == 200


def test_i18n_assets_and_language_toggle(client: TestClient):
    asset = client.get("/static/i18n.js")
    assert asset.status_code == 200
    assert "javascript" in asset.headers["content-type"]
    assert "duty-lang" in asset.text
    assert '"Schedule"' in asset.text
    assert "data-lang-toggle" in asset.text

    for name in ("index.html", "login.html", "my.html"):
        page = (ROOT / "app" / "static" / name).read_text(encoding="utf-8")
        assert "/static/i18n.js" in page
        assert "data-lang-toggle" in page

    for path in ("/", "/login"):
        response = client.get(path)
        assert response.status_code == 200
        assert "/static/i18n.js" in response.text
        assert "data-lang-toggle" in response.text


def test_i18n_translations_with_node():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not installed")
    completed = subprocess.run(
        [node, "--test", "tests/test_i18n.mjs"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_health_and_security_headers(client: TestClient):
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert str(db.DB_PATH) not in health.text

    headers = client.get("/api/schedule").headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert "script-src 'self'" in headers["Content-Security-Policy"]
    assert "Strict-Transport-Security" not in headers


def test_login_rate_limit(client: TestClient):
    anonymous = TestClient(app)
    for _ in range(10):
        response = anonymous.post(
            "/api/auth/login", json={"username": "ghost", "password": "wrong-pass"}
        )
        assert response.status_code == 401
    blocked = anonymous.post(
        "/api/auth/login", json={"username": "ghost", "password": "wrong-pass"}
    )
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) >= 1
    reset_login_failures()
    recovered = anonymous.post(
        "/api/auth/login", json={"username": "ghost", "password": "wrong-pass"}
    )
    assert recovered.status_code == 401


def test_logout_revokes_existing_session(client: TestClient):
    ivanov = add_person(client, "Иванов")
    add_account(client, ivanov, "ivanov")
    employee = login_as("ivanov")
    token = employee.cookies.get("duty_session")
    assert token

    stolen = TestClient(app)
    assert stolen.get(
        "/api/me", headers={"cookie": f"duty_session={token}"}
    ).status_code == 200

    employee.post("/api/auth/logout")
    assert stolen.get(
        "/api/me", headers={"cookie": f"duty_session={token}"}
    ).status_code == 401


def test_password_policy_min_length(client: TestClient):
    ivanov = add_person(client, "Иванов")
    response = client.post(
        "/api/users",
        json={
            "username": "ivanov",
            "password": "short12",
            "role": "employee",
            "person_id": ivanov,
        },
    )
    assert response.status_code == 400

    add_account(client, ivanov, "ivanov")
    employee = login_as("ivanov")
    rejected = employee.post(
        "/api/auth/password",
        json={"current_password": "pass1234", "new_password": "short12"},
    )
    assert rejected.status_code == 400


def test_csv_export_neutralises_formulas(client: TestClient):
    person = add_person(client, "=HYPERLINK(\"http://x\")")
    created = client.post(
        "/api/duties",
        json={"date": MONDAY.isoformat(), "person_id": person, "note": "+SUM(1)"},
    )
    assert created.status_code == 200
    export = client.get("/api/export", params={"month": MONTH})
    assert export.status_code == 200
    assert "'=HYPERLINK" in export.text
    assert "'+SUM(1)" in export.text


def test_relaxed_roulette_blocks_only_vacation_and_rest(client: TestClient):
    absent = add_person(client, "Отпускной")
    resting = add_person(client, "Отсыпной")
    conflicted = add_person(client, "СЗаявкой")
    free = add_person(client, "Свободный")
    target = MONDAY + timedelta(days=21)

    absence = client.post(
        "/api/absences",
        json={
            "person_id": absent,
            "date_from": target.isoformat(),
            "date_to": target.isoformat(),
            "kind": "vacation",
        },
    )
    assert absence.status_code == 200
    rest_duty = client.post(
        "/api/duties",
        json={
            "date": (target - timedelta(days=1)).isoformat(),
            "person_id": resting,
        },
    )
    assert rest_duty.status_code == 200
    with db.db() as conn:
        conn.execute(
            "INSERT INTO availability"
            "(person_id, date_from, date_to, kind, reason, status) "
            "VALUES(?, ?, ?, 'unavailable', 'учебный день', 'approved')",
            (conflicted, target.isoformat(), target.isoformat()),
        )

    strict = client.get(
        "/api/roulette", params={"date": target.isoformat()}
    ).json()
    by_name = {item["person_name"]: item for item in strict["candidates"]}
    assert by_name["Отпускной"]["eligible"] is False
    assert by_name["Отсыпной"]["eligible"] is False
    assert by_name["СЗаявкой"]["eligible"] is False
    assert by_name["Свободный"]["eligible"] is True

    relaxed = client.get(
        "/api/roulette", params={"date": target.isoformat(), "relaxed": 1}
    ).json()
    assert relaxed["relaxed"] is True
    by_name = {item["person_name"]: item for item in relaxed["candidates"]}
    assert by_name["Отпускной"]["eligible"] is False
    assert by_name["Отсыпной"]["eligible"] is False
    assert by_name["СЗаявкой"]["eligible"] is True
    assert any(
        "согласованная заявка" in reason
        for reason in by_name["СЗаявкой"]["conflicts"]
    )

    blocked = client.post(
        "/api/draw",
        json={
            "date": target.isoformat(),
            "candidate_ids": [absent],
            "mode": "equal",
            "relaxed": True,
            "seed": 1,
        },
    )
    assert blocked.status_code == 409

    drawn = client.post(
        "/api/draw",
        json={
            "date": target.isoformat(),
            "candidate_ids": [conflicted, free],
            "mode": "equal",
            "relaxed": True,
            "seed": 5,
        },
    )
    assert drawn.status_code == 200
    result = drawn.json()
    assert result["winner"]["personId"] in (conflicted, free)
    if result["winner"]["personId"] == conflicted:
        assert result["deviations"]
    schedule = client.get("/api/schedule", params={"month": MONTH}).json()
    duty = next(
        day["duty"] for day in schedule["days"] if day["date"] == target.isoformat()
    )
    assert duty["personName"] == result["winner"]["personName"]


def test_roulette_replaces_planned_duty(client: TestClient):
    ivanov = add_person(client, "Иванов")
    petrov = add_person(client, "Петров")
    target = MONDAY + timedelta(days=21)
    original = client.post(
        "/api/duties",
        json={"date": target.isoformat(), "person_id": ivanov},
    )
    assert original.status_code == 200
    old_id = original.json()["duty"]["id"]

    refused = client.post(
        "/api/draw",
        json={"date": target.isoformat(), "candidate_ids": [petrov], "seed": 3},
    )
    assert refused.status_code == 409

    replaced = client.post(
        "/api/draw",
        json={
            "date": target.isoformat(),
            "candidate_ids": [petrov],
            "seed": 3,
            "replace": True,
        },
    )
    assert replaced.status_code == 200
    result = replaced.json()
    assert result["replacedDutyId"] == old_id
    assert result["winner"]["personId"] == petrov

    schedule = client.get("/api/schedule", params={"month": MONTH}).json()
    day = next(item for item in schedule["days"] if item["date"] == target.isoformat())
    assert day["duty"]["personName"] == "Петров"
    with db.db() as conn:
        old = conn.execute(
            "SELECT status FROM duties WHERE id = ?", (old_id,)
        ).fetchone()
    assert old["status"] == "cancelled"


def test_roulette_replace_respects_scheduled_comp(client: TestClient):
    ivanov = add_person(client, "Иванов")
    petrov = add_person(client, "Петров")
    target = SATURDAY + timedelta(days=14)
    duty = client.post(
        "/api/duties",
        json={"date": target.isoformat(), "person_id": ivanov},
    )
    assert duty.status_code == 200
    duty_id = duty.json()["duty"]["id"]
    with db.db() as conn:
        conn.execute(
            "INSERT INTO comp_choices(duty_id, date, status) VALUES(?, ?, 'scheduled')",
            (duty_id, (target + timedelta(days=3)).isoformat()),
        )

    refused = client.post(
        "/api/draw",
        json={
            "date": target.isoformat(),
            "candidate_ids": [petrov],
            "seed": 3,
            "replace": True,
        },
    )
    assert refused.status_code == 409
    assert "отгул" in refused.json()["detail"]

