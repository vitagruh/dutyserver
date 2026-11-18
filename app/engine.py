from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Iterable, Sequence

ACTIVE_DUTY_STATUSES = ("planned", "done", "missed")
COMP_BLOCKING_STATUSES = ("scheduled", "used")


def as_date(value: str | date) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def iso(value: str | date) -> str:
    return value.isoformat() if isinstance(value, date) else str(value)


def short_date(value: str | date) -> str:
    d = as_date(value)
    return f"{d.day:02d}.{d.month:02d}"


@dataclass(frozen=True)
class Rules:
    rest_days: int = 1
    min_gap_days: int = 2
    weekend_weight: float = 1.5
    fairness_power: int = 2
    comp_enabled: bool = True
    comp_valid_days: int = 60
    history_days: int = 0

    @classmethod
    def from_settings(cls, values: dict[str, Any]) -> "Rules":
        def as_int(key: str, default: int) -> int:
            try:
                return int(values.get(key, default))
            except (TypeError, ValueError):
                return default

        def as_float(key: str, default: float) -> float:
            try:
                return float(values.get(key, default))
            except (TypeError, ValueError):
                return default

        rest = min(7, max(0, as_int("rest_days", 1)))
        gap = min(30, max(1, as_int("min_gap_days", 2)))
        return cls(
            rest_days=rest,
            min_gap_days=max(gap, rest + 1),
            weekend_weight=min(3.0, max(1.0, as_float("weekend_weight", 1.5))),
            fairness_power=min(4, max(1, as_int("fairness_power", 2))),
            comp_enabled=as_int("comp_enabled", 1) == 1,
            comp_valid_days=min(365, max(1, as_int("comp_valid_days", 60))),
            history_days=min(3650, max(0, as_int("history_days", 0))),
        )


def is_active_duty(duty: dict[str, Any]) -> bool:
    return duty.get("status", "planned") in ACTIVE_DUTY_STATUSES


def is_day_off(day: date, holidays: set[str]) -> bool:
    """Выходной или нерабочий праздничный день."""
    return day.weekday() >= 5 or day.isoformat() in holidays


def empty_load() -> dict[str, Any]:
    return {
        "total": 0,
        "weekday": 0,
        "weekend": 0,
        "weighted": 0.0,
        "last_duty": None,
    }


def loads_by_person(
    people: Sequence[dict[str, Any]],
    duties: Sequence[dict[str, Any]],
    holidays: set[str],
    rules: Rules,
    ref_date: date | None = None,
) -> dict[int, dict[str, Any]]:
    """Взвешенная нагрузка: будни = 1, выходные/праздники = weekend_weight."""
    result = {int(p["id"]): empty_load() for p in people}
    for duty in duties:
        if not is_active_duty(duty):
            continue
        person_id = int(duty["person_id"])
        if person_id not in result:
            continue
        duty_date = as_date(duty["date"])
        if ref_date and rules.history_days > 0:
            if duty_date < ref_date - timedelta(days=rules.history_days):
                continue
        item = result[person_id]
        item["total"] += 1
        if is_day_off(duty_date, holidays):
            item["weekend"] += 1
            item["weighted"] += rules.weekend_weight
        else:
            item["weekday"] += 1
            item["weighted"] += 1.0
        last = item["last_duty"]
        if last is None or duty_date > as_date(last):
            item["last_duty"] = duty_date.isoformat()
    for item in result.values():
        item["weighted"] = round(item["weighted"], 2)
    return result


def evaluate_candidates(
    day: date | str,
    people: Sequence[dict[str, Any]],
    duties: Sequence[dict[str, Any]],
    absences: Sequence[dict[str, Any]],
    comps: Sequence[dict[str, Any]],
    holidays: set[str],
    rules: Rules,
    requests: Sequence[dict[str, Any]] = (),
    relax: bool = False,
) -> list[dict[str, Any]]:
    """Все активные сотрудники с отметкой доступности и причинами отказа.

    relax=True переносит отпуска, отсыпные/интервалы и согласованные заявки
    из блокирующих причин в конфликты: это пул для решения тимлида, а не
    штатное распределение.
    """
    target = as_date(day)
    target_iso = target.isoformat()
    active_people = [p for p in people if p.get("active", 1)]
    loads = loads_by_person(active_people, duties, holidays, rules, ref_date=target)

    duty_dates: dict[int, list[date]] = {}
    on_duty_today: set[int] = set()
    for duty in duties:
        if not is_active_duty(duty):
            continue
        person_id = int(duty["person_id"])
        duty_date = as_date(duty["date"])
        duty_dates.setdefault(person_id, []).append(duty_date)
        if duty_date == target:
            on_duty_today.add(person_id)

    absent: set[int] = set()
    for absence in absences:
        if as_date(absence["date_from"]) <= target <= as_date(absence["date_to"]):
            absent.add(int(absence["person_id"]))

    comp_today: set[int] = set()
    for comp in comps:
        if comp.get("status") in COMP_BLOCKING_STATUSES and comp.get("date") == target_iso:
            comp_today.add(int(comp["person_id"]))

    unavailable: set[int] = set()
    notes: dict[int, list[str]] = {}
    for request in requests:
        if request.get("status") == "declined":
            continue
        if not (as_date(request["date_from"]) <= target <= as_date(request["date_to"])):
            continue
        person_id = int(request["person_id"])
        if request.get("kind") == "unavailable":
            if request.get("status") == "approved":
                unavailable.add(person_id)
            else:
                notes.setdefault(person_id, []).append("заявка «не могу» ждёт согласования")
        elif request.get("status") == "approved":
            notes.setdefault(person_id, []).append("просил не назначать (согласовано)")
        else:
            notes.setdefault(person_id, []).append("просил не назначать")

    result: list[dict[str, Any]] = []
    for person in active_people:
        person_id = int(person["id"])
        reasons: list[str] = []
        conflicts: list[str] = []
        soft = conflicts if relax else reasons
        if person_id in on_duty_today:
            reasons.append("в этот день уже назначено дежурство")
        if person_id in absent:
            soft.append("отсутствие: отпуск / болезнь / командировка")
        if person_id in comp_today:
            reasons.append("в этот день оформлен отгул")
        if person_id in unavailable:
            soft.append("не может дежурить — согласованная заявка")

        for duty_date in duty_dates.get(person_id, []):
            diff = (duty_date - target).days
            distance = abs(diff)
            if distance == 0:
                continue
            if distance < rules.min_gap_days:
                if diff < 0 and distance <= rules.rest_days:
                    soft.append(f"отсыпной после дежурства {short_date(duty_date)}")
                elif diff > 0 and distance <= rules.rest_days:
                    soft.append(f"на следующий день дежурство {short_date(duty_date)}")
                else:
                    soft.append(f"малый интервал с дежурством {short_date(duty_date)}")

        reasons = list(dict.fromkeys(reasons))
        result.append(
            {
                "person_id": person_id,
                "person_name": person["name"],
                "eligible": not reasons,
                "reasons": reasons,
                "conflicts": list(dict.fromkeys(conflicts)),
                "warnings": list(dict.fromkeys(notes.get(person_id, []))),
                "load": dict(loads[person_id]),
            }
        )
    return result


def apply_probabilities(
    candidates: list[dict[str, Any]],
    power: int,
    selected_ids: Iterable[int] | None = None,
) -> list[dict[str, Any]]:
    """Вес = (Lmax - L + 1)^power; вероятность = вес / сумма весов.

    В нагрузке L выходное дежурство уже учтено с коэффициентом weekend_weight.
    Если selected_ids не заданы, в розыгрыше участвуют все доступные.
    """
    chosen = (
        {int(pid) for pid in selected_ids}
        if selected_ids is not None
        else {int(c["person_id"]) for c in candidates if c["eligible"]}
    )
    pool = [c for c in candidates if c["eligible"] and int(c["person_id"]) in chosen]
    for candidate in candidates:
        candidate["selected"] = int(candidate["person_id"]) in chosen
        candidate["weight"] = 0.0
        candidate["probability"] = 0.0
    if not pool:
        return candidates

    max_load = max(float(c["load"]["weighted"]) for c in pool)
    for candidate in pool:
        weight = (max_load - float(candidate["load"]["weighted"]) + 1.0) ** power
        candidate["weight"] = weight
    total = sum(float(c["weight"]) for c in pool)
    for candidate in pool:
        candidate["probability"] = float(candidate["weight"]) / total if total else 0.0
    return candidates


ROULETTE_MODES = ("equal", "month")


def apply_roulette_weights(
    candidates: list[dict[str, Any]],
    mode: str,
    month_counts: dict[int, int],
    power: int,
    selected_ids: Iterable[int] | None = None,
) -> list[dict[str, Any]]:
    """Веса для визуальной рулетки.

    equal — дежурства не учитываются, у всех участников вес 1.
    month — вес = (Mmax − M + 1)^power, где M — число дежурств
    в целевом месяце: кто меньше дежурил, получает больший шанс.
    """
    if mode not in ROULETTE_MODES:
        raise ValueError(f"Неизвестный режим рулетки: {mode}")
    chosen = (
        {int(pid) for pid in selected_ids}
        if selected_ids is not None
        else {int(c["person_id"]) for c in candidates if c["eligible"]}
    )
    pool = [c for c in candidates if c["eligible"] and int(c["person_id"]) in chosen]
    for candidate in candidates:
        person_id = int(candidate["person_id"])
        candidate["selected"] = person_id in chosen
        candidate["month_duties"] = int(month_counts.get(person_id, 0))
        candidate["weight"] = 0.0
        candidate["probability"] = 0.0
    if not pool:
        return candidates

    if mode == "equal":
        for candidate in pool:
            candidate["weight"] = 1.0
    else:
        top = max(int(candidate["month_duties"]) for candidate in pool)
        for candidate in pool:
            candidate["weight"] = float(
                (top - int(candidate["month_duties"]) + 1) ** power
            )
    total = sum(float(candidate["weight"]) for candidate in pool)
    for candidate in pool:
        candidate["probability"] = (
            float(candidate["weight"]) / total if total else 0.0
        )
    return candidates


def pick_by_roll(
    candidates: Sequence[dict[str, Any]], roll: float
) -> dict[str, Any] | None:
    """Выбор по одному случайному числу из [0, 1) — основа проверяемого пруфа."""
    pool = [c for c in candidates if float(c.get("weight", 0)) > 0]
    if not pool:
        return None
    total = sum(float(c["weight"]) for c in pool)
    threshold = float(roll) * total
    acc = 0.0
    for candidate in pool:
        acc += float(candidate["weight"])
        if threshold < acc:
            return candidate
    return pool[-1]


def pick_weighted(
    candidates: Sequence[dict[str, Any]], rng: random.Random
) -> dict[str, Any] | None:
    return pick_by_roll(candidates, rng.random())


def build_auto_plan(
    people: Sequence[dict[str, Any]],
    duties: Sequence[dict[str, Any]],
    absences: Sequence[dict[str, Any]],
    comps: Sequence[dict[str, Any]],
    holidays: set[str],
    rules: Rules,
    date_from: date,
    date_to: date,
    seed: int = 0,
    requests: Sequence[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Равномерное заполнение пустых дней: минимальная нагрузка, жребий среди равных."""
    rng = random.Random(seed)
    simulated = [dict(d) for d in duties]
    assigned: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    occupied = {
        duty["date"] for duty in simulated if is_active_duty(duty)
    }

    current = date_from
    while current <= date_to:
        day_iso = current.isoformat()
        if day_iso in occupied:
            skipped.append({"date": day_iso, "reason": "день уже занят"})
            current += timedelta(days=1)
            continue

        candidates = evaluate_candidates(
            current, people, simulated, absences, comps, holidays, rules,
            requests=requests,
        )
        eligible = [c for c in candidates if c["eligible"]]
        if not eligible:
            skipped.append({"date": day_iso, "reason": "нет доступных сотрудников"})
        else:
            preferred = [c for c in eligible if not c.get("warnings")]
            pool_source = preferred or eligible
            min_load = min(float(c["load"]["weighted"]) for c in pool_source)
            pool = [
                c for c in pool_source
                if abs(float(c["load"]["weighted"]) - min_load) < 1e-9
            ]
            chosen = rng.choice(pool)
            simulated.append(
                {
                    "id": None,
                    "date": day_iso,
                    "person_id": chosen["person_id"],
                    "status": "planned",
                    "source": "auto",
                    "note": "",
                }
            )
            occupied.add(day_iso)
            assigned.append(
                {
                    "date": day_iso,
                    "person_id": chosen["person_id"],
                    "person_name": chosen["person_name"],
                    "weekend": is_day_off(current, holidays),
                    "load_before": round(min_load, 2),
                }
            )
        current += timedelta(days=1)

    return {"assigned": assigned, "skipped": skipped, "seed": seed}


def weekend_entitlements(
    duties: Sequence[dict[str, Any]],
    choices: Sequence[dict[str, Any]],
    holidays: set[str],
    rules: Rules,
    today: date | None = None,
) -> list[dict[str, Any]]:
    """Право на отгул за каждое выходное/праздничное дежурство."""
    if not rules.comp_enabled:
        return []
    choice_by_duty = {int(c["duty_id"]): c for c in choices}
    result: list[dict[str, Any]] = []
    for duty in duties:
        if not is_active_duty(duty):
            continue
        duty_date = as_date(duty["date"])
        if not is_day_off(duty_date, holidays):
            continue
        duty_id = int(duty["id"])
        choice = choice_by_duty.get(duty_id, {})
        status = choice.get("status") or "pending"
        chosen_date = choice.get("date")
        valid_until = duty_date + timedelta(days=rules.comp_valid_days)
        expired = bool(
            status == "pending" and today is not None and today > valid_until
        )
        result.append(
            {
                "duty_id": duty_id,
                "person_id": int(duty["person_id"]),
                "duty_date": duty_date.isoformat(),
                "status": status,
                "choice_date": chosen_date,
                "valid_until": valid_until.isoformat(),
                "expired": expired,
            }
        )
    result.sort(key=lambda item: item["duty_date"], reverse=True)
    return result


def validate_comp_date(
    day: date,
    duty_date: date,
    person_id: int,
    duties: Sequence[dict[str, Any]],
    absences: Sequence[dict[str, Any]],
    comps: Sequence[dict[str, Any]],
    holidays: set[str],
    rules: Rules,
    ignore_duty_id: int | None = None,
) -> str | None:
    """Возвращает текст ошибки или None, если дата отгула допустима."""
    if day <= duty_date:
        return "дата отгула должна быть позже дежурства"
    last_allowed = duty_date + timedelta(days=rules.comp_valid_days)
    if day > last_allowed:
        return f"срок оформления отгула истёк {short_date(last_allowed)}"
    if is_day_off(day, holidays):
        return "отгул оформляется на рабочий день (будни, не праздник)"

    for duty in duties:
        if not is_active_duty(duty) or int(duty["person_id"]) != person_id:
            continue
        other = as_date(duty["date"])
        if other == day:
            return "в этот день у сотрудника дежурство"
        if 0 < (day - other).days <= rules.rest_days:
            return f"в этот день отсыпной после дежурства {short_date(other)}"

    for absence in absences:
        if int(absence["person_id"]) != person_id:
            continue
        if as_date(absence["date_from"]) <= day <= as_date(absence["date_to"]):
            return "в этот день сотрудник уже отсутствует"

    day_iso = day.isoformat()
    for comp in comps:
        if comp.get("status") not in COMP_BLOCKING_STATUSES:
            continue
        if comp.get("date") != day_iso:
            continue
        if int(comp["person_id"]) != person_id:
            continue
        if ignore_duty_id is not None and int(comp.get("duty_id", -1)) == ignore_duty_id:
            continue
        return "на этот день уже оформлен другой отгул"

    return None
