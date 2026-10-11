"""Завдання №31: пул з'єднань.

`Pool(factory, max_size=5, max_age=300.0, clock=time.monotonic)`.
`factory()` створює нове з'єднання (обʼєкт із методом `close()`).

- `acquire() -> conn`
    1. Бере вільне з'єднання з пулу. Найновіше повернуте йде першим (LIFO: «гарячі»
       з'єднання використовуються, решта старіє й закривається).
       З'єднання, чий вік (`clock() - момент створення`) >= `max_age`, закривається
       (`conn.close()`), пропускається, і береться наступне.
    2. Якщо вільних немає, а зайнятих менше за `max_size`, створює нове через `factory()`.
    3. Інакше піднімає `PoolExhausted` (без очікування: у production тут був би таймаут).
    Після `close()` пулу `acquire()` піднімає `RuntimeError`.
- `release(conn, broken=False)`
    Повертає з'єднання в пул. `broken=True`: з'єднання закривається й викидається, а
    місце в пулі звільняється. Чуже або вже повернене з'єднання це `ValueError`.
    Якщо пул уже закрито, з'єднання закривається замість повернення.
- `connection()`: контекстний менеджер. `with pool.connection() as conn:` бере з'єднання й
    гарантовано повертає його, навіть якщо в блоці виняток. Виняток `ConnectionError`
    вважається ознакою зламаного з'єднання: його викидають (як `broken=True`) і
    пробрасують далі. Інші винятки з'єднання не ламають.
- `stats() -> dict`: `{"in_use": ..., "idle": ..., "created": ...}`, де `created` це скільки
    з'єднань створено за весь час.
- `close()`: закриває всі вільні з'єднання; зайняті закриються при поверненні.

Вік рахується від створення, а не від останнього використання.
"""
import time
from contextlib import contextmanager
from typing import Callable


class PoolExhausted(Exception):
    pass


class Pool:
    def __init__(self, factory: Callable[[], object], max_size: int = 5, max_age: float = 300.0,
                 clock: Callable[[], float] = time.monotonic):
        raise NotImplementedError

    def acquire(self):
        raise NotImplementedError

    def release(self, conn, broken: bool = False) -> None:
        raise NotImplementedError

    @contextmanager
    def connection(self):
        raise NotImplementedError
        yield  # noqa: B901  (щоб це лишалось генератором)

    def stats(self) -> dict:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError
