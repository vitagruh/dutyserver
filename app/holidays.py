from __future__ import annotations

from datetime import date, timedelta

FIXED_HOLIDAYS: tuple[tuple[int, int, str], ...] = (
    (1, 1, "Новый год"),
    (1, 2, "Новый год (2-й день)"),
    (1, 7, "Рождество Христово (православное)"),
    (3, 8, "День женщин"),
    (5, 1, "Праздник труда"),
    (5, 9, "День Победы"),
    (7, 3, "День Независимости Республики Беларусь"),
    (11, 7, "День Октябрьской революции"),
    (12, 25, "Рождество Христово (католическое)"),
)


def orthodox_easter(year: int) -> date:
    """Пасха по юлианской пасхалии в григорианском календаре."""
    a = year % 4
    b = year % 7
    c = year % 19
    d = (19 * c + 15) % 30
    e = (2 * a + 4 * b - d + 34) % 7
    month = (d + e + 114) // 31
    day = ((d + e + 114) % 31) + 1
    return date(year, month, day) + timedelta(days=13)


def belarus_holidays(year: int) -> list[tuple[date, str]]:
    result = [(date(year, month, day), name) for month, day, name in FIXED_HOLIDAYS]
    radunitsa = orthodox_easter(year) + timedelta(days=9)
    result.append((radunitsa, "Радуница"))
    result.sort(key=lambda item: item[0])
    return result
