"""Демонстрационная база: 12 сотрудников, три месяца дежурств, отпуска и отгулы.

Запуск (из корня проекта):
    .venv/Scripts/python.exe seed_demo.py --force
    DUTY_DB=demo.db .venv/Scripts/python.exe run.py
"""

from __future__ import annotations

import argparse
import os
import random
from datetime import date, timedelta
from pathlib import Path

PEOPLE = [
    ("Александр Ковалёв", "1 смена", "kovalev"),
    ("Дмитрий Сидоров", "1 смена", "sidorov"),
    ("Сергей Лебедев", "2 смена", "lebedev"),
    ("Андрей Морозов", "2 смена", "morozov"),
    ("Павел Новиков", "3 смена", "novikov"),
    ("Игорь Волков", "3 смена", "volkov"),
    ("Максим Орлов", "резерв", "orlov"),
    ("Роман Зайцев", "1 смена", "zaytsev"),
    ("Евгений Соколов", "2 смена", "sokolov"),
    ("Виктор Павлов", "3 смена", "pavlov"),
    ("Олег Смирнов", "резерв", "smirnov"),
    ("Николай Фёдоров", "1 смена", "fedorov"),
]

EMPLOYEE_PASSWORD = "duty123"
TEAMLEAD_PASSWORD = "lead123"


def add_months(first_day: date, months: int) -> date:
    index = first_day.year * 12 + (first_day.month - 1) + months
    return date(index // 12, index % 12 + 1, 1)


def main() -> int:
    parser = argparse.ArgumentParser(description="Создать демонстрационную БД")
    parser.add_argument("--db", default="demo.db", help="путь к файлу БД")
    parser.add_argument("--force", action="store_true", help="пересоздать существующую БД")
    args = parser.parse_args()

    os.environ["DUTY_DB"] = args.db
    os.environ.setdefault("DUTY_ADMIN_PASSWORD", "admin123")

    from app import db, engine, security
    from app.holidays import belarus_holidays

    path = db.DB_PATH
    if path.exists():
        if not args.force:
            print(f"Файл {path} уже существует. Добавьте --force, чтобы пересоздать.")
            return 1
        for suffix in ("", "-wal", "-shm"):
            try:
                Path(str(path) + suffix).unlink()
            except FileNotFoundError:
                pass

    db.init_db()
    today = date.today()
    month_first = today.replace(day=1)
    plan_start = add_months(month_first, -1)
    next_first = add_months(month_first, 1)
    plan_finish = add_months(next_first, 1) - timedelta(days=1)

    with db.db() as conn:
        for name, note, login in PEOPLE:
            conn.execute(
                "INSERT INTO people(name, note, active, email, rocketchat) "
                "VALUES(?, ?, 1, ?, ?)",
                (name, note, f"{login}@example.by", f"@{login}"),
            )
        people = [dict(row) for row in conn.execute(
            "SELECT id, name, note, active, email, rocketchat "
            "FROM people ORDER BY id"
        )]
        ids = [int(person["id"]) for person in people]

        for index, person in enumerate(people):
            is_lead = index == 0
            conn.execute(
                "INSERT INTO users(username, password_hash, role, person_id, email, rocketchat) "
                "VALUES(?, ?, ?, ?, ?, ?)",
                (
                    PEOPLE[index][2],
                    security.hash_password(
                        TEAMLEAD_PASSWORD if is_lead else EMPLOYEE_PASSWORD
                    ),
                    "teamlead" if is_lead else "employee",
                    int(person["id"]),
                    person["email"],
                    person["rocketchat"],
                ),
            )

        for year in range(plan_start.year, plan_finish.year + 1):
            for day, name in belarus_holidays(year):
                conn.execute(
                    "INSERT OR IGNORE INTO holidays(date, name) VALUES(?, ?)",
                    (day.isoformat(), name),
                )

        absences_data = [
            (ids[2], next_first + timedelta(days=8), next_first + timedelta(days=12), "vacation", "Плановый отпуск"),
            (ids[5], today - timedelta(days=2), today + timedelta(days=1), "sick", "Больничный"),
            (ids[8], next_first + timedelta(days=1), next_first + timedelta(days=4), "trip", "Командировка"),
            (ids[10], today + timedelta(days=5), today + timedelta(days=7), "vacation", "Отпуск"),
        ]
        for person_id, start, finish, kind, note in absences_data:
            conn.execute(
                "INSERT INTO absences(person_id, date_from, date_to, kind, note) "
                "VALUES(?, ?, ?, ?, ?)",
                (person_id, start.isoformat(), finish.isoformat(), kind, note),
            )
        absences = [dict(row) for row in conn.execute("SELECT * FROM absences")]
        holiday_rows = [dict(row) for row in conn.execute("SELECT date, name FROM holidays")]
        holiday_set = {row["date"] for row in holiday_rows}
        rules = engine.Rules.from_settings(db.load_settings(conn))

        plan = engine.build_auto_plan(
            people,
            [],
            absences,
            [],
            holiday_set,
            rules,
            plan_start,
            plan_finish,
            seed=20261118,
        )
        for item in plan["assigned"]:
            conn.execute(
                "INSERT INTO duties(date, person_id, status, source, note) "
                "VALUES(?, ?, 'planned', 'auto', ?)",
                (item["date"], item["person_id"], "Демонстрационный график"),
            )

        conn.execute(
            "UPDATE duties SET status = 'done' "
            "WHERE date < ? AND status = 'planned'",
            (today.isoformat(),),
        )

        duties = [dict(row) for row in conn.execute("SELECT * FROM duties")]
        comps: list[dict] = []
        rng = random.Random(424242)
        weekend_duties = sorted(
            (
                duty for duty in duties
                if engine.is_active_duty(duty)
                and engine.is_day_off(engine.as_date(duty["date"]), holiday_set)
                and engine.as_date(duty["date"]) < today
            ),
            key=lambda duty: duty["date"],
        )
        scheduled = used = declined = 0
        for duty in weekend_duties:
            duty_date = engine.as_date(duty["date"])
            person_id = int(duty["person_id"])
            roll = rng.random()
            if roll >= 0.58:
                if roll >= 0.58 and roll < 0.70:
                    conn.execute(
                        "INSERT INTO comp_choices(duty_id, date, status) "
                        "VALUES(?, NULL, 'declined')",
                        (duty["id"],),
                    )
                    declined += 1
                continue

            window_start = duty_date + timedelta(days=2)
            window_end = min(duty_date + timedelta(days=24), today)
            if window_start > window_end:
                continue
            options = []
            cursor = window_start
            while cursor <= window_end:
                if cursor.weekday() < 5:
                    options.append(cursor)
                cursor += timedelta(days=1)
            rng.shuffle(options)
            for option in options:
                error = engine.validate_comp_date(
                    option,
                    duty_date,
                    person_id,
                    duties,
                    absences,
                    comps,
                    holiday_set,
                    rules,
                    ignore_duty_id=int(duty["id"]),
                )
                if error:
                    continue
                status = "used" if option <= today else "scheduled"
                conn.execute(
                    "INSERT INTO comp_choices(duty_id, date, status) VALUES(?, ?, ?)",
                    (duty["id"], option.isoformat(), status),
                )
                comps.append(
                    {
                        "duty_id": duty["id"],
                        "person_id": person_id,
                        "date": option.isoformat(),
                        "status": status,
                    }
                )
                if status == "used":
                    used += 1
                else:
                    scheduled += 1
                break

        free_days: list[date] = []
        for day_number in (8, 16, 23):
            free_day = date(next_first.year, next_first.month, day_number)
            while free_day.weekday() >= 5:
                free_day += timedelta(days=1)
            conn.execute("DELETE FROM duties WHERE date = ?", (free_day.isoformat(),))
            free_days.append(free_day)

        gap_day = free_days[1]
        for person in people:
            conn.execute(
                "INSERT INTO availability"
                "(person_id, date_from, date_to, kind, reason, status) "
                "VALUES(?, ?, ?, 'unavailable', ?, 'approved')",
                (
                    int(person["id"]),
                    gap_day.isoformat(),
                    gap_day.isoformat(),
                    "Учебный день (демо-заявка)",
                ),
            )

        duty_count = conn.execute("SELECT COUNT(*) FROM duties").fetchone()[0]
        weekend_count = sum(
            1 for duty in duties
            if engine.is_day_off(engine.as_date(duty["date"]), holiday_set)
        )

    print(f"Демо-БД: {path}")
    print(f"Сотрудников: {len(people)}")
    print(f"Дежурств: {duty_count} (выходных/праздничных: {weekend_count})")
    print(f"Отгулы: оформлено {scheduled}, использовано {used}, отказ {declined}")
    print("Свободные дни для проверки жеребьёвки/назначения: "
          + ", ".join(day.strftime("%d.%m.%Y") for day in free_days))
    print(f"День без покрытия (демо): {gap_day:%d.%m.%Y} — все сотрудники недоступны")
    print()
    print("Учётные записи:")
    print(f"  admin / {os.environ.get('DUTY_ADMIN_PASSWORD', 'admin123')} — администратор")
    print(f"  {PEOPLE[0][2]} / {TEAMLEAD_PASSWORD} — тимлид ({PEOPLE[0][0]})")
    print(f"  остальные сотрудники — пароль {EMPLOYEE_PASSWORD}:")
    print("   " + ", ".join(item[2] for item in PEOPLE[1:]))
    print()
    print("Запуск:")
    print("  Git Bash:  DUTY_DB=demo.db .venv/Scripts/python.exe run.py")
    print("  PowerShell: $env:DUTY_DB=\"demo.db\"; .venv\\Scripts\\python.exe run.py")
    print("  Открыть:   http://127.0.0.1:8000")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
