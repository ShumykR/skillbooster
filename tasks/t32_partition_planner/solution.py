"""Завдання №32: помісячне партиціонування таблиці подій (PostgreSQL declarative partitioning).

Таблиця `events` росте на мільйони рядків щодня. Її ділять на партиції по місяцях (`events_2026_03`). Так запит за
один день читає одну партицію (partition pruning), а видалення старих даних це миттєвий `DROP TABLE events_2024_01`,
а не годинний `DELETE`. Партиції треба створювати НАПЕРЕД (інакше вставка падає) і прибирати за політикою зберігання.
Нижче логіка планування; SQL виконує окрема утиліта.

Ім'я таблиці вставляється в SQL, тому воно має відповідати `[a-z_][a-z0-9_]{0,40}`, інакше ValueError (захист від ін'єкції).

`partition_name(table, d) -> str`      "events_2026_03" для дати `d` (date або datetime) у березні 2026.
`partition_bounds(table, name) -> (date, date)`
    Межі партиції `[початок, кінець)`: ("events_2026_03") -> (date(2026,3,1), date(2026,4,1)); грудень закінчується 1 січня наступного
    року. `name` має мати вигляд `<table>_YYYY_MM`, місяць 01..12, рік 1900..2999; інакше ValueError.
`ddl_create(table, d) -> str`
    Рівно такий текст (без зайвих пробілів і переносів):
    CREATE TABLE events_2026_03 PARTITION OF events FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');
`ddl_drop(table, name) -> str`
    DROP TABLE events_2024_01;  (ValueError, якщо `name` не є партицією саме цієї таблиці)
`plan_partitions(table, existing, today, retention_months, ahead_months) -> dict`
    * потрібні партиції: з місяця (поточний мінус retention_months-1) по (поточний плюс ahead_months) включно, де поточний це
      місяць `today`. retention_months >= 1, ahead_months >= 0 (int, не bool), інакше ValueError;
    * `existing`: імена таблиць у схемі (будь-які). Партиціями ЦІЄЇ таблиці вважаються лише імена вигляду `<table>_YYYY_MM`;
      все інше (`events_default`, `events_archive`, `eventsx_2026_03`, `other_2026_03`, `events_2026_13`) ігнорується й НІКОЛИ не видаляється;
    * повертає {"create": [...], "drop": [...]}: create це потрібні, яких ще нема; drop це наявні партиції цієї таблиці,
      що старіші за вікно (партиції з майбутнього поза вікном `ahead` НЕ видаляються: їх хтось створив уже);
    * обидва списки відсортовані за ім'ям, без дублікатів (навіть якщо `existing` має повтори).
`partitions_for_range(table, existing, start, end) -> list[str]`
    Партиції цієї таблиці (з `existing`), що перетинаються з піввідкритим інтервалом дат `[start, end)` (date або datetime;
    datetime: `start` усікається до дати, а `end` з ненульовим часом округлюється ВГОРУ до наступної дати, бо
    момент 00:30 цього дня теж входить в інтервал). Якщо start >= end (після такого приведення), порожньо. Відсортовано. Так планувальник запитів вибирає, які партиції сканувати.
"""
import datetime as dt


def partition_name(table: str, d) -> str:
    raise NotImplementedError


def partition_bounds(table: str, name: str) -> tuple[dt.date, dt.date]:
    raise NotImplementedError


def ddl_create(table: str, d) -> str:
    raise NotImplementedError


def ddl_drop(table: str, name: str) -> str:
    raise NotImplementedError


def plan_partitions(table: str, existing, today, retention_months: int, ahead_months: int) -> dict:
    raise NotImplementedError


def partitions_for_range(table: str, existing, start, end) -> list[str]:
    raise NotImplementedError
