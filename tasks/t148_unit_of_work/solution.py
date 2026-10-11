"""Завдання №148: Unit of Work + Repository.

Таблиці (створює тест):
    accounts(id TEXT PRIMARY KEY, owner TEXT NOT NULL, balance INTEGER NOT NULL)
    audit(id INTEGER PRIMARY KEY AUTOINCREMENT, message TEXT NOT NULL)

`UnitOfWork(connect)` де `connect()` повертає НОВЕ `sqlite3.Connection` (кожен виклик це нова транзакційна межа).
    * `with UnitOfWork(connect) as uow:` відкриває з'єднання (один `connect()` на вхід) і дає репозиторії
      `uow.accounts` та `uow.audit`, які працюють в ОДНІЙ транзакції на цьому з'єднанні;
    * `uow.commit()` фіксує зміни, `uow.rollback()` відкочує;
    * вихід із `with` без `commit()` ВІДКОЧУЄ все (це «безпечне за замовчуванням»); так само при винятку;
      виняток при цьому не придушується;
    * після виходу з'єднання закрите;
    * `uow.accounts` / `uow.audit` поза `with` (до входу чи після виходу): RuntimeError;
    * кожен вхід у `with` це нова одиниця роботи (об'єкт можна використати двічі підряд).

`AccountRepo`:   add(id, owner, balance), get(id) -> {"id","owner","balance"} | None, set_balance(id, balance)
    (set_balance для неіснуючого рахунку: LookupError)
`AuditRepo`:     add(message), all() -> list[str] за порядком додавання

`transfer(connect, src, dst, amount)`: у ОДНІЙ одиниці роботи списує з `src`, зараховує на `dst`, пише рядок
    в аудит і фіксує. amount це int > 0 (інакше ValueError). Немає рахунку: LookupError. Не вистачає коштів:
    InsufficientFunds. У разі будь-якої помилки НЕ має лишитись жодного сліду: ні змін балансу, ні аудиту.
"""
import sqlite3
from typing import Callable


class InsufficientFunds(Exception):
    pass


class AccountRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add(self, id: str, owner: str, balance: int) -> None:
        raise NotImplementedError

    def get(self, id: str) -> dict | None:
        raise NotImplementedError

    def set_balance(self, id: str, balance: int) -> None:
        raise NotImplementedError


class AuditRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add(self, message: str) -> None:
        raise NotImplementedError

    def all(self) -> list[str]:
        raise NotImplementedError


class UnitOfWork:
    def __init__(self, connect: Callable[[], sqlite3.Connection]):
        self._connect = connect

    def __enter__(self):
        raise NotImplementedError

    def __exit__(self, exc_type, exc, tb):
        raise NotImplementedError

    def commit(self) -> None:
        raise NotImplementedError

    def rollback(self) -> None:
        raise NotImplementedError


def transfer(connect: Callable[[], sqlite3.Connection], src: str, dst: str, amount: int) -> None:
    raise NotImplementedError
