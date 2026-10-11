"""Завдання №6: cursor-пагінація замість OFFSET.

Таблиця (створюється тестами):

    CREATE TABLE items (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at INTEGER NOT NULL,
        title      TEXT NOT NULL
    );

`fetch_page(conn, limit, cursor=None)` повертає `(rows, next_cursor)`:
- `conn` це `sqlite3.Connection`; рядки повертай як словники
  `{"id": ..., "created_at": ..., "title": ...}`;
- порядок: найновіші першими, тобто `created_at DESC, id DESC` (id розв'язує однакові
  `created_at`, інакше записи губляться або дублюються на межі сторінок);
- `cursor` це непрозорий рядок, який ти сам видав у попередній відповіді (наприклад,
  base64 від позиції останнього рядка). `None` означає першу сторінку;
- `next_cursor` це `None`, якщо це остання сторінка. Сторінка рівно з `limit` рядків, після
  якої даних немає, теж остання: не віддавай курсор на порожню сторінку;
- `limit` має бути цілим від 1 до 100, інакше `ValueError`; зіпсований курсор (сміття,
  не рядок, не те що ти видавав) теж `ValueError`;
- заборонено `OFFSET` (тест перехоплює SQL): запит має використовувати позицію з курсора.
  Підказка: SQLite підтримує порівняння кортежів `(a, b) < (?, ?)`.
"""
import sqlite3


def fetch_page(conn: sqlite3.Connection, limit: int, cursor: str | None = None) -> tuple[list[dict], str | None]:
    raise NotImplementedError
