"""Завдання №23: Індекси.

Три запити в production повільні (повне сканування таблиць). Створи
МІНІМАЛЬНИЙ набір індексів (не більше 3), щоб кожен із них використовував індекс,
а запит №1 ще й обходився без окремого сортування.

Запити (див. test_solution.py):
  1. SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC LIMIT 20
  2. SELECT COUNT(*) FROM orders WHERE status = 'pending' AND created_at > ?
  3. SELECT id FROM users WHERE lower(email) = ?
"""
import sqlite3


def create_indexes(conn: sqlite3.Connection) -> None:
    raise NotImplementedError
