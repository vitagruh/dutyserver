"""Проверяемый жребий: канонический пакет, SHA-256 и воспроизведение выбора."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Sequence

ALGORITHM = "weighted-pick/v1"
VERSION = 1


def canonical_json(payload: Any) -> str:
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def digest(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def build_payload(
    *,
    date: str,
    mode: str,
    seed: int,
    roll: float,
    power: int,
    weekend_weight: float,
    month: str | None,
    candidates: Sequence[dict[str, Any]],
    winner_id: int,
    winner_name: str,
) -> dict[str, Any]:
    return {
        "algorithm": ALGORITHM,
        "version": VERSION,
        "date": date,
        "mode": mode,
        "seed": int(seed),
        "roll": float(roll),
        "power": int(power),
        "weekendWeight": float(weekend_weight),
        "month": month,
        "winnerId": int(winner_id),
        "winnerName": winner_name,
        "candidates": [
            {
                "personId": int(candidate["person_id"]),
                "name": candidate["person_name"],
                "weight": float(candidate["weight"]),
                "probability": float(candidate["probability"]),
                "weightedLoad": float(candidate["load"]["weighted"]),
                "monthDuties": int(candidate.get("month_duties", 0)),
            }
            for candidate in candidates
        ],
    }


def _weights_consistent(
    payload: dict[str, Any],
    candidates: Sequence[dict[str, Any]],
    power: int,
) -> bool:
    """Сверяет веса участников с правилом выбранного режима.

    load  — (maxWeightedLoad − weightedLoad + 1)^power,
    month — (maxMonthDuties − monthDuties + 1)^power,
    equal — у всех участников вес 1.
    """
    if not candidates:
        return False
    eps = 1e-6
    mode = str(payload.get("mode") or "load")
    if mode == "equal":
        return all(
            abs(float(candidate.get("weight", 0.0)) - 1.0) <= eps
            for candidate in candidates
        )
    if mode == "month":
        top = max(int(candidate.get("monthDuties", 0)) for candidate in candidates)
        return all(
            abs(
                float(candidate["weight"])
                - float((top - int(candidate.get("monthDuties", 0)) + 1) ** power)
            )
            <= eps
            for candidate in candidates
        )
    top = max(float(candidate.get("weightedLoad", 0.0)) for candidate in candidates)
    return all(
        abs(
            float(candidate["weight"])
            - float((top - float(candidate.get("weightedLoad", 0.0)) + 1.0) ** power)
        )
        <= eps
        for candidate in candidates
    )


def verify(payload: dict[str, Any], expected_hash: str) -> dict[str, Any]:
    canonical = canonical_json(payload)
    computed = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    candidates = [
        candidate
        for candidate in payload.get("candidates") or []
        if float(candidate.get("weight", 0)) > 0
    ]
    total = sum(float(candidate["weight"]) for candidate in candidates)
    power = int(payload.get("power") or 1)
    roll = float(payload.get("roll", 0.0))
    threshold = roll * total
    acc = 0.0
    replayed: dict[str, Any] | None = None
    bounds: list[dict[str, Any]] = []
    for candidate in candidates:
        start = acc
        acc += float(candidate["weight"])
        bounds.append(
            {
                "personId": int(candidate["personId"]),
                "name": candidate.get("name", ""),
                "from": start,
                "to": acc,
                "weight": float(candidate["weight"]),
                "probability": float(candidate.get("probability", 0.0)),
            }
        )
        if replayed is None and threshold < acc:
            replayed = candidate
    if replayed is None and candidates:
        replayed = candidates[-1]

    probabilities = sum(
        float(candidate.get("probability", 0.0)) for candidate in candidates
    )
    winner_id = int(payload.get("winnerId", 0))
    checks = {
        "hashMatches": computed == expected_hash,
        "weightsPositive": bool(candidates) and total > 0,
        "weightsConsistent": _weights_consistent(payload, candidates, power),
        "probabilitiesSum": abs(probabilities - 1.0) <= 1e-6 if candidates else False,
        "winnerMatches": bool(replayed)
        and int(replayed["personId"]) == winner_id,
    }
    return {
        "canonical": canonical,
        "hash": computed,
        "checks": checks,
        "verified": all(checks.values()),
        "totalWeight": total,
        "roll": roll,
        "threshold": threshold,
        "intervals": bounds,
        "replayedWinnerId": int(replayed["personId"]) if replayed else None,
        "replayedWinnerName": replayed.get("name") if replayed else None,
    }
