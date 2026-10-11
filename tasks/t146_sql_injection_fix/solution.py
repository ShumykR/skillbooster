"""Завдання №146: SQL-ін'єкція. Виправ вразливий код.

Нижче код, який хтось написав «на швидку руку». Він працює на звичайних даних і дозволяє
зловмиснику читати чужі дані, обходити фільтри й ламати БД (CWE-89, **№2 у MITRE CWE Top 25**).
Твоє завдання: ПЕРЕПИСАТИ функції так, щоб дані від користувача НІКОЛИ не потрапляли в текст
SQL, але поведінка для чесних запитів лишилась.

Таблиця (створюється тестами):
    users(id INTEGER PRIMARY KEY, name TEXT, email TEXT, role TEXT, password_hash TEXT)

`find_users(conn, name_prefix, sort_by="name", order="asc", limit=20) -> list[dict]`
    Користувачі, чиє ім'я ПОЧИНАЄТЬСЯ з `name_prefix` (без урахування регістру для ASCII, як
    `LIKE` у SQLite). Символи `%`, `_` та `\\` у `name_prefix` це ЗВИЧАЙНІ символи, а не шаблон
    (пошук `100%` знаходить лише імена, що починаються з рівно `100%`).
    * кожен елемент це `{"id", "name", "email"}` і БІЛЬШЕ НІЧОГО (`password_hash` та `role` не віддавати);
    * `sort_by` має бути одним із `id`, `name`, `email`, інакше `ValueError`. Імена колонок не
      можна передати параметром `?`, тому тут потрібен allowlist;
    * `order` це `asc` або `desc` (будь-який регістр), інакше `ValueError`;
    * `limit` це `int` від 1 до 100 (не `bool`, не рядок, не `float`), інакше `ValueError`;
    * порядок: за `sort_by` і `order`, а при рівності за `id` за зростанням.
`get_user_by_email(conn, email) -> dict | None`
    Точний збіг email. Результат `{"id", "name", "email", "role"}` або `None`.
    `password_hash` не віддавати.
"""
import sqlite3


def find_users(conn: sqlite3.Connection, name_prefix: str, sort_by: str = "name", order: str = "asc",
               limit: int = 20) -> list[dict]:
    # НАЇВНА ВРАЗЛИВА РЕАЛІЗАЦІЯ: перепиши.
    sql = (
        f"SELECT id, name, email, password_hash FROM users WHERE name LIKE '{name_prefix}%' "
        f"ORDER BY {sort_by} {order} LIMIT {limit}"
    )
    rows = conn.execute(sql).fetchall()
    return [{"id": r[0], "name": r[1], "email": r[2], "password_hash": r[3]} for r in rows]


def get_user_by_email(conn: sqlite3.Connection, email: str) -> dict | None:
    # НАЇВНА ВРАЗЛИВА РЕАЛІЗАЦІЯ: перепиши.
    row = conn.execute(f"SELECT * FROM users WHERE email = '{email}'").fetchone()
    if not row:
        return None
    return {"id": row[0], "name": row[1], "email": row[2], "role": row[3], "password_hash": row[4]}
