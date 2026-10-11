"""Завдання №34: read replica та «прочитав свій запис» (read-your-writes).

Реплікація асинхронна: запис на primary з'являється на replica з затримкою (replication
lag). Користувач натискає «Зберегти», сторінка перезавантажується, читання йде на replica,
а зміни там ще немає: «система загубила мої дані». `ReadRouter` вирішує, куди спрямувати
запит.

`ReadRouter(primary, replica, stick_seconds=5.0, clock=time.monotonic, replica_ok=lambda: True)`
де `primary` і `replica` це довільні обʼєкти (роутер їх лише повертає), `replica_ok()`
повідомляє, чи здорова replica.

- `for_write(user_id)`: запам'ятовує момент запису цього користувача й повертає `primary`;
- `for_read(user_id=None, force_primary=False)` повертає:
    * `primary`, якщо `force_primary=True` (наприклад, читання всередині транзакції запису);
    * `primary`, якщо `replica_ok()` повертає False (failover);
    * `primary`, якщо цей користувач писав менше ніж `stick_seconds` секунд тому
      (рівно `stick_seconds` уже вважається давно);
    * інакше `replica`. Анонімне читання (`user_id=None`) і користувачі, які ніколи не
      писали, йдуть на replica;
- `tracked_users() -> int`: скільки користувачів зараз «прив'язані» до primary (писали менше
  `stick_seconds` тому). Прострочені записи не повинні накопичуватись у памʼяті вічно.

Запис одного користувача не впливає на читання інших.
"""
import time
from typing import Callable


class ReadRouter:
    def __init__(
        self,
        primary: object,
        replica: object,
        stick_seconds: float = 5.0,
        clock: Callable[[], float] = time.monotonic,
        replica_ok: Callable[[], bool] = lambda: True,
    ):
        raise NotImplementedError

    def for_write(self, user_id: str) -> object:
        raise NotImplementedError

    def for_read(self, user_id: str | None = None, force_primary: bool = False) -> object:
        raise NotImplementedError

    def tracked_users(self) -> int:
        raise NotImplementedError
