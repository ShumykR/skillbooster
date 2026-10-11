"""Завдання №30: soft delete та журнал змін (audit).

Таблиці створюються тестами:

    CREATE TABLE docs (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        title      TEXT NOT NULL,
        deleted_at REAL            -- NULL означає «не видалено»
    );
    CREATE TABLE audit (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        doc_id    INTEGER NOT NULL,
        action    TEXT NOT NULL,
        actor     TEXT NOT NULL,
        at        REAL NOT NULL,
        old_title TEXT,
        new_title TEXT
    );

`DocRepo(conn, clock=time.time)`. Час береться з `clock()` (у тестах він підмінений).

Методи (`actor` це хто виконав дію):
- `create(title, actor) -> int`   новий документ; запис в audit: action="create",
                                  old_title=None, new_title=title;
- `get(doc_id, include_deleted=False) -> dict|None`
                                  `{"id", "title", "deleted_at"}`; видалені приховані,
                                  якщо не передано `include_deleted=True`;
- `list() -> list[dict]`          невидалені, за зростанням id, у тому ж форматі;
- `rename(doc_id, title, actor) -> bool`
                                  audit: action="rename", old_title=старий, new_title=новий.
                                  Видалений або неіснуючий документ: False, нічого не пишемо;
- `delete(doc_id, actor) -> bool` м'яке видалення: `deleted_at = clock()`, рядок лишається.
                                  audit: action="delete", old_title=поточний, new_title=None.
                                  Уже видалений або неіснуючий: False;
- `restore(doc_id, actor) -> bool` знімає позначку видалення; audit: action="restore",
                                  old_title=None, new_title=поточний. Невидалений або
                                  неіснуючий: False;
- `history(doc_id) -> list[dict]` записи audit цього документа за порядком появи, кожен як
                                  `{"action", "actor", "at", "old_title", "new_title"}`.

АТОМАРНІСТЬ: зміна документа й запис в audit виконуються в ОДНІЙ транзакції. Якщо запис в
audit не вдався (наприклад, `actor=None` порушує NOT NULL), зміна документа теж
відкочується, а виняток `sqlite3.IntegrityError` піднімається до викликача.
"""
import sqlite3
import time
from typing import Callable


class DocRepo:
    def __init__(self, conn: sqlite3.Connection, clock: Callable[[], float] = time.time):
        raise NotImplementedError

    def create(self, title: str, actor: str) -> int:
        raise NotImplementedError

    def get(self, doc_id: int, include_deleted: bool = False) -> dict | None:
        raise NotImplementedError

    def list(self) -> list[dict]:
        raise NotImplementedError

    def rename(self, doc_id: int, title: str, actor: str) -> bool:
        raise NotImplementedError

    def delete(self, doc_id: int, actor: str) -> bool:
        raise NotImplementedError

    def restore(self, doc_id: int, actor: str) -> bool:
        raise NotImplementedError

    def history(self, doc_id: int) -> list[dict]:
        raise NotImplementedError
