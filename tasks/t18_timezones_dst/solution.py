"""Завдання №18: часові пояси та перехід на літній/зимовий час (DST).

Правило: ЗБЕРІГАЙ у UTC, перетворюй у локальний час лише на межі (вхід користувача, вивід).
Використовуй `zoneinfo.ZoneInfo` (на Windows потрібен пакет `tzdata`, він у requirements.txt).
`tz` усюди це рядок на кшталт "Europe/Kyiv". Усі результати це aware-datetime в UTC.

Функції:
- `to_utc(local, tz, ambiguous="raise") -> datetime`
    `local` це НАЇВНИЙ datetime (з tzinfo це `ValueError`) у часовому поясі `tz`.
    * Звичайний час: просто переводиться в UTC.
    * НЕІСНУЮЧИЙ час (пропуск навесні, 03:30 у Києві 2026-03-29): `NonexistentTimeError`.
    * НЕОДНОЗНАЧНИЙ час (осінній дубль, 03:30 у Києві 2026-10-25 трапляється двічі):
      залежить від `ambiguous`: "raise" піднімає `AmbiguousTimeError`, "earlier" бере перше
      входження (літній час), "later" друге (зимовий). Інше значення `ambiguous` це `ValueError`.
    Підказка: PEP 495, атрибут `fold` у datetime.
- `add_calendar_days(utc_dt, days, tz) -> datetime`
    «Той самий настінний час через N календарних днів у поясі tz» (нагадування «щодня о 09:00»).
    Через перехід на літній час це на 23 години, через зимовий на 25. Якщо отриманий локальний
    час не існує (пропуск), зсунь його вперед на величину пропуску (03:30 стає 04:30);
    якщо він подвійний, бери перше входження. `utc_dt` має бути aware і в UTC, інакше `ValueError`.
- `add_elapsed(utc_dt, hours) -> datetime`
    Реально минулі години (таймер, TTL): рівно `hours` годин різниці в UTC, незалежно від DST.
- `local_day_bounds(day, tz) -> (start_utc, end_utc)`
    Межі локальної доби `day` (тип `date`) як півінтервал [start, end): початок цієї доби й
    початок наступної, обидва в UTC. Ті самі правила для неіснуючого/подвійного часу, що й вище
    (північ у деяких поясах «пропадає», тоді беруть перший існуючий момент після пропуску).
- `day_length_hours(day, tz) -> float`   тривалість доби в годинах: 23, 24 або 25.
- `format_local(utc_dt, tz) -> str`      ISO-рядок локального часу з зсувом, до хвилин:
    `"2026-03-29T04:30+03:00"`.
"""
from datetime import date, datetime


class NonexistentTimeError(ValueError):
    """Локального часу не існує (пропуск при переході на літній час)."""


class AmbiguousTimeError(ValueError):
    """Локальний час трапляється двічі (дубль при переході на зимовий час)."""


def to_utc(local: datetime, tz: str, ambiguous: str = "raise") -> datetime:
    raise NotImplementedError


def add_calendar_days(utc_dt: datetime, days: int, tz: str) -> datetime:
    raise NotImplementedError


def add_elapsed(utc_dt: datetime, hours: float) -> datetime:
    raise NotImplementedError


def local_day_bounds(day: date, tz: str) -> tuple[datetime, datetime]:
    raise NotImplementedError


def day_length_hours(day: date, tz: str) -> float:
    raise NotImplementedError


def format_local(utc_dt: datetime, tz: str) -> str:
    raise NotImplementedError
