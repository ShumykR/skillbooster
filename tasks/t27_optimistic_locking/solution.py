"""Завдання №27: Optimistic locking.

Два редактори відкрили один документ і зберігають по черзі: останній мовчки
затирає зміни першого (lost update). Захисти від цього версією рядка.
"""
import sqlite3


class StaleDataError(Exception):
    """Документ змінили після того, як клієнт його прочитав."""


def update_title(conn: sqlite3.Connection, doc_id: int, new_title: str, expected_version: int) -> int:
    """Змінює заголовок і повертає НОВУ версію.

    LookupError, якщо документа немає; StaleDataError, якщо версія не збігається.
    """
    conn.execute("UPDATE docs SET title = ? WHERE id = ?", (new_title, doc_id))
    conn.commit()
    return expected_version + 1
