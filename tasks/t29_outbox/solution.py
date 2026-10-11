"""Завдання №29: Outbox pattern.

Після створення замовлення треба опублікувати подію (у брокер). Зараз між
записом у БД і публікацією є розрив: якщо процес впав посередині, замовлення є,
а події немає (або навпаки). Реалізуй надійну доставку через таблицю outbox.
"""
import json
import sqlite3
from typing import Callable

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, total REAL NOT NULL);
CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    payload TEXT NOT NULL,
    sent_at TEXT
);
"""


def place_order(
    conn: sqlite3.Connection,
    order_id: int,
    total: float,
    _crash: Callable[[], None] | None = None,
) -> None:
    """Зберігає замовлення і подію `order.created` (JSON з order_id і total).

    `_crash` викликається між двома записами, щоб тести могли симулювати падіння.
    """
    conn.execute("INSERT INTO orders(id, total) VALUES (?, ?)", (order_id, total))
    conn.commit()
    if _crash:
        _crash()
    payload = json.dumps({"order_id": order_id, "total": total})
    conn.execute("INSERT INTO outbox(topic, payload) VALUES ('order.created', ?)", (payload,))
    conn.commit()


def relay(conn: sqlite3.Connection, publish: Callable[[str, str, int], None]) -> int:
    """Публікує непослані події в порядку id: publish(topic, payload, event_id).

    Після успішної публікації ставить sent_at. Якщо publish кинув виняток,
    зупиняється (решта лишається неспосланою) і піднімає його далі.
    Повертає кількість надісланих подій.
    """
    raise NotImplementedError
