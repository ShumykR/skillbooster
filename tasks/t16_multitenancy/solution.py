"""Завдання №16: мультитенантність (ізоляція даних між клієнтами).

Спільна таблиця (створюється тестами):

    CREATE TABLE notes (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id TEXT NOT NULL,
        title     TEXT NOT NULL
    );

`NoteRepo(conn, tenant_id)` це єдина точка доступу до таблиці для одного клієнта. Кожен
запит ОБОВʼЯЗКОВО обмежений `tenant_id`; забути один `WHERE` означає витік даних.

Методи:
- `add(title) -> int`        створює нотатку цього tenant, повертає її id;
- `get(note_id) -> dict|None` `{"id", "title"}` або `None`, якщо такої нотатки немає В ЦЬОМУ
                              tenant. Чужу нотатку не відрізняй від неіснуючої (не підказуй
                              атакувальнику, що id існує);
- `list() -> list[dict]`     нотатки цього tenant, за зростанням id;
- `update(note_id, title) -> bool` True, якщо змінено; чужа або неіснуюча нотатка дає False
                              і нічого не змінює;
- `delete(note_id) -> bool`  так само;
- `count() -> int`           кількість нотаток цього tenant.

`tenant_id` має бути непорожнім рядком, інакше `ValueError` у конструкторі. Усі значення
передавай параметрами SQL (`?`), а не склеюванням рядків: tenant_id або title можуть містити
лапки й фрагменти SQL.
"""
import sqlite3


class NoteRepo:
    def __init__(self, conn: sqlite3.Connection, tenant_id: str):
        raise NotImplementedError

    def add(self, title: str) -> int:
        raise NotImplementedError

    def get(self, note_id: int) -> dict | None:
        raise NotImplementedError

    def list(self) -> list[dict]:
        raise NotImplementedError

    def update(self, note_id: int, title: str) -> bool:
        raise NotImplementedError

    def delete(self, note_id: int) -> bool:
        raise NotImplementedError

    def count(self) -> int:
        raise NotImplementedError
