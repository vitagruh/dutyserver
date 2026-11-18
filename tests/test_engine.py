from datetime import date, timedelta
import random

import pytest

from app import engine


def weekday_on_or_after(start: date, weekday: int) -> date:
    current = start
    while current.weekday() != weekday:
        current += timedelta(days=1)
    return current


MONDAY = weekday_on_or_after(date(2026, 12, 1), 0)
SATURDAY = weekday_on_or_after(date(2026, 12, 1), 5)

PEOPLE = [
    {"id": 1, "name": "Иванов", "active": 1},
    {"id": 2, "name": "Петров", "active": 1},
    {"id": 3, "name": "Сидоров", "active": 1},
]


def duty(duty_id: int, person_id: int, day: date, status: str = "planned") -> dict:
    return {
        "id": duty_id,
        "person_id": person_id,
        "date": day.isoformat(),
        "status": status,
        "source": "manual",
        "note": "",
    }


def candidate(person_id: int, name: str, weighted: float) -> dict:
    return {
        "person_id": person_id,
        "person_name": name,
        "eligible": True,
        "reasons": [],
        "load": {"total": 0, "weekday": 0, "weekend": 0, "weighted": weighted, "last_duty": None},
    }


def test_weekend_duty_has_higher_weight():
    rules = engine.Rules()
    duties = [
        duty(1, 1, MONDAY),
        duty(2, 1, SATURDAY),
    ]
    loads = engine.loads_by_person(PEOPLE, duties, set(), rules)
    assert loads[1]["total"] == 2
    assert loads[1]["weekday"] == 1
    assert loads[1]["weekend"] == 1
    assert loads[1]["weighted"] == pytest.approx(2.5)


def test_rest_day_blocks_next_day_but_not_day_after():
    rules = engine.Rules()
    duties = [duty(1, 1, MONDAY)]
    tuesday = MONDAY + timedelta(days=1)
    wednesday = MONDAY + timedelta(days=2)

    tuesday_result = engine.evaluate_candidates(
        tuesday, PEOPLE, duties, [], [], set(), rules
    )
    ivanov = next(item for item in tuesday_result if item["person_id"] == 1)
    assert not ivanov["eligible"]
    assert "отсыпной" in " ".join(ivanov["reasons"])

    wednesday_result = engine.evaluate_candidates(
        wednesday, PEOPLE, duties, [], [], set(), rules
    )
    ivanov = next(item for item in wednesday_result if item["person_id"] == 1)
    assert ivanov["eligible"]


def test_rest_is_protected_in_forward_direction():
    rules = engine.Rules()
    wednesday = MONDAY + timedelta(days=2)
    tuesday = MONDAY + timedelta(days=1)
    duties = [duty(1, 1, wednesday)]
    result = engine.evaluate_candidates(tuesday, PEOPLE, duties, [], [], set(), rules)
    ivanov = next(item for item in result if item["person_id"] == 1)
    assert not ivanov["eligible"]
    assert "на следующий день" in " ".join(ivanov["reasons"])


def test_min_gap_blocks_short_interval():
    rules = engine.Rules(min_gap_days=3)
    wednesday = MONDAY + timedelta(days=2)
    duties = [duty(1, 1, MONDAY)]
    result = engine.evaluate_candidates(wednesday, PEOPLE, duties, [], [], set(), rules)
    ivanov = next(item for item in result if item["person_id"] == 1)
    assert not ivanov["eligible"]
    assert "интервал" in " ".join(ivanov["reasons"])


def test_absence_and_comp_day_block_candidate():
    rules = engine.Rules()
    target = MONDAY + timedelta(days=1)
    absences = [
        {"person_id": 1, "date_from": target.isoformat(), "date_to": target.isoformat(), "kind": "vacation"}
    ]
    comps = [
        {"person_id": 2, "date": target.isoformat(), "status": "scheduled"}
    ]
    result = engine.evaluate_candidates(target, PEOPLE, [], absences, comps, set(), rules)
    by_id = {item["person_id"]: item for item in result}
    assert not by_id[1]["eligible"]
    assert "отсутствие" in " ".join(by_id[1]["reasons"])
    assert not by_id[2]["eligible"]
    assert "отгул" in " ".join(by_id[2]["reasons"])
    assert by_id[3]["eligible"]


def test_probability_favors_less_loaded_and_sums_to_one():
    candidates = [
        candidate(1, "Ноль", 0.0),
        candidate(2, "Один", 1.0),
        candidate(3, "Два с половиной", 2.5),
    ]
    result = engine.apply_probabilities(candidates, power=2)
    by_id = {item["person_id"]: item for item in result}
    assert by_id[1]["probability"] > by_id[2]["probability"] > by_id[3]["probability"]
    assert sum(item["probability"] for item in result) == pytest.approx(1.0)
    assert by_id[1]["weight"] == pytest.approx(12.25)
    assert by_id[3]["weight"] == pytest.approx(1.0)


def test_probability_respects_selected_claimants_only():
    candidates = [
        candidate(1, "А", 0.0),
        candidate(2, "Б", 1.0),
        candidate(3, "В", 2.5),
    ]
    result = engine.apply_probabilities(candidates, power=2, selected_ids=[2, 3])
    by_id = {item["person_id"]: item for item in result}
    assert by_id[1]["probability"] == 0
    assert by_id[1]["selected"] is False
    assert by_id[2]["probability"] + by_id[3]["probability"] == pytest.approx(1.0)
    assert by_id[2]["probability"] == pytest.approx(6.25 / 7.25)


def test_weighted_pick_is_reproducible_by_seed():
    def run(seed: int) -> int:
        candidates = [
            candidate(1, "А", 0.0),
            candidate(2, "Б", 1.0),
            candidate(3, "В", 2.5),
        ]
        engine.apply_probabilities(candidates, power=2)
        winner = engine.pick_weighted(candidates, random.Random(seed))
        return winner["person_id"]

    assert run(12345) == run(12345)


def test_auto_plan_respects_rest_and_fills_month():
    rules = engine.Rules()
    start = MONDAY
    finish = MONDAY + timedelta(days=11)
    plan = engine.build_auto_plan(
        PEOPLE, [], [], [], set(), rules, start, finish, seed=7
    )
    assert len(plan["assigned"]) == 12
    assert plan["skipped"] == []

    by_person: dict[int, list[date]] = {}
    for item in plan["assigned"]:
        by_person.setdefault(item["person_id"], []).append(date.fromisoformat(item["date"]))
    for dates in by_person.values():
        dates.sort()
        for earlier, later in zip(dates, dates[1:]):
            assert (later - earlier).days >= rules.min_gap_days
    assert len(by_person) == 3


def test_auto_plan_skips_occupied_days():
    rules = engine.Rules()
    existing = [duty(1, 1, MONDAY)]
    plan = engine.build_auto_plan(
        PEOPLE, existing, [], [], set(), rules,
        MONDAY, MONDAY + timedelta(days=2), seed=1,
    )
    assert all(item["date"] != MONDAY.isoformat() for item in plan["assigned"])
    assert any(
        item["date"] == MONDAY.isoformat() and item["reason"] == "день уже занят"
        for item in plan["skipped"]
    )


def test_weekend_entitlements_only_for_days_off():
    rules = engine.Rules()
    duties = [
        duty(1, 1, MONDAY),
        duty(2, 1, SATURDAY),
    ]
    entitlements = engine.weekend_entitlements(duties, [], set(), rules, today=SATURDAY)
    assert len(entitlements) == 1
    item = entitlements[0]
    assert item["duty_id"] == 2
    assert item["status"] == "pending"
    assert item["valid_until"] == (SATURDAY + timedelta(days=60)).isoformat()


def test_holiday_counts_as_day_off():
    rules = engine.Rules()
    tuesday = MONDAY + timedelta(days=1)
    holidays = {tuesday.isoformat()}
    duties = [duty(1, 1, tuesday)]
    loads = engine.loads_by_person(PEOPLE, duties, holidays, rules)
    assert loads[1]["weekend"] == 1
    assert loads[1]["weighted"] == pytest.approx(1.5)
    entitlements = engine.weekend_entitlements(
        duties, [], holidays, rules, today=tuesday
    )
    assert len(entitlements) == 1


def test_comp_date_validation():
    rules = engine.Rules()
    saturday_duty = SATURDAY
    monday = SATURDAY + timedelta(days=2)
    duties = [duty(1, 1, saturday_duty)]

    assert engine.validate_comp_date(
        monday, saturday_duty, 1, duties, [], [], set(), rules
    ) is None

    sunday = SATURDAY + timedelta(days=1)
    assert "рабочий день" in engine.validate_comp_date(
        sunday, saturday_duty, 1, duties, [], [], set(), rules
    )
    assert "позже" in engine.validate_comp_date(
        SATURDAY - timedelta(days=1), saturday_duty, 1, duties, [], [], set(), rules
    )
    assert "срок" in engine.validate_comp_date(
        saturday_duty + timedelta(days=61), saturday_duty, 1, duties, [], [], set(), rules
    )

    conflicting_duty = [duty(2, 1, monday)]
    assert "дежурство" in engine.validate_comp_date(
        monday, saturday_duty, 1, conflicting_duty, [], [], set(), rules
    )

    sunday_duty = [duty(2, 1, sunday)]
    assert "отсыпной" in engine.validate_comp_date(
        monday, saturday_duty, 1, sunday_duty, [], [], set(), rules
    )

    other_comp = [
        {"duty_id": 9, "person_id": 1, "date": monday.isoformat(), "status": "scheduled"}
    ]
    assert "другой отгул" in engine.validate_comp_date(
        monday, saturday_duty, 1, duties, [], other_comp, set(), rules
    )
    assert engine.validate_comp_date(
        monday, saturday_duty, 1, duties, [], other_comp, set(), rules,
        ignore_duty_id=9,
    ) is None


def test_history_window_limits_load():
    rules = engine.Rules(history_days=30)
    old_duty = duty(1, 1, date(2026, 1, 1))
    ref = date(2026, 12, 1)
    loads = engine.loads_by_person(PEOPLE, [old_duty], set(), rules, ref_date=ref)
    assert loads[1]["total"] == 0
    loads_all = engine.loads_by_person(PEOPLE, [old_duty], set(), engine.Rules())
    assert loads_all[1]["total"] == 1
