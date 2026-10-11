"""Завдання №160: керування сесіями (CWE-384 session fixation, CWE-613 insufficient expiration).

`SessionStore(clock, idle_ttl, absolute_ttl, max_per_user=5, token_fn=None)`
    * `clock()` повертає поточний час у секундах (float/int); `idle_ttl` та `absolute_ttl` це секунди, `0 < idle_ttl <= absolute_ttl`,
      інакше ValueError; `max_per_user` це int >= 1;
    * `token_fn()` повертає новий ідентифікатор сесії (рядок); за замовчуванням `secrets.token_urlsafe(32)`.
      Якщо `token_fn` повернув id, що вже використовується (колізія), повтори до 3 разів, далі RuntimeError;
      жодної перезаписаної чужої сесії.

`create(user_id, data=None) -> str`
    Створює сесію, повертає її id. `data` це dict (копіюється; за замовчуванням порожній). Якщо в користувача вже
    `max_per_user` активних сесій, найстаріша за часом створення (`created_at`) видаляється. Прострочені сесії
    вважаються неіснуючими й не враховуються в ліміті.
`get(sid) -> dict | None`
    Для чинної сесії повертає КОПІЮ `{"user_id", "created_at", "last_seen", "data"}` і оновлює `last_seen` на «зараз».
    Для невідомого/не-рядкового id, відкликаної чи простроченої повертає None (прострочену видаляє).
    Прострочена, якщо `now - last_seen >= idle_ttl` (неактивність) або `now - created_at >= absolute_ttl` (абсолютний ліміт:
    активністю його НЕ подовжити).
`rotate(sid) -> str | None`
    Видає НОВИЙ id для тієї самої сесії (виклик після входу чи підвищення привілеїв: захист від fixation).
    Старий id стає недійсним миттєво. `created_at` (отже й абсолютний ліміт) і `data` зберігаються, `last_seen` оновлюється.
    Для недійсного sid повертає None і нічого не створює.
`revoke(sid) -> bool`           True, якщо чинну сесію видалено.
`revoke_user(user_id) -> int`   Видаляє всі сесії користувача («вийти скрізь», зміна пароля); повертає кількість видалених
                                (прострочені, які ще лежать у сховищі, теж видаляються, але в кількість не входять).
`active_count(user_id) -> int`  Кількість чинних сесій користувача (не змінює `last_seen`).
Сесії різних користувачів не впливають одна на одну.
"""
import secrets
from typing import Callable


class SessionStore:
    def __init__(self, clock: Callable[[], float], idle_ttl: float, absolute_ttl: float, max_per_user: int = 5,
                 token_fn: Callable[[], str] | None = None):
        raise NotImplementedError

    def create(self, user_id, data: dict | None = None) -> str:
        raise NotImplementedError

    def get(self, sid) -> dict | None:
        raise NotImplementedError

    def rotate(self, sid) -> str | None:
        raise NotImplementedError

    def revoke(self, sid) -> bool:
        raise NotImplementedError

    def revoke_user(self, user_id) -> int:
        raise NotImplementedError

    def active_count(self, user_id) -> int:
        raise NotImplementedError
