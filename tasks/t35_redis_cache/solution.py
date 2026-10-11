"""Завдання №35: Redis-кеш за схемою cache-aside.

`UserService(db, cache, ttl=60, negative_ttl=5)`.

`db` має методи `load(user_id) -> dict | None` (None, якщо користувача немає) і
`save(user_id, data)`. `cache` схожий на Redis-клієнт, що зберігає ТІЛЬКИ РЯДКИ:
`get(key) -> str | None`, `set(key, value: str, ttl: int)`, `delete(key)`. Будь-який з методів
кешу може підняти `CacheError` (Redis недоступний).

- `get_user(user_id)`:
    1. ключ кешу `f"user:{user_id}"`; значення зберігай як JSON (`json.dumps`);
    2. кеш-хіт: повернути дані з кешу, НЕ чіпаючи БД;
    3. кеш-міс: `db.load`, записати результат у кеш з `ttl` секунд і повернути;
    4. якщо користувача немає (`None`), теж кешуй (JSON `null`) але на `negative_ttl`
       секунд: так повторні запити за неіснуючим id не б'ють у БД («negative caching»);
    5. `CacheError` при читанні або записі в кеш не ламає запит: працюємо напряму з БД.
- `update_user(user_id, data)`:
    1. спершу `db.save`, потім `cache.delete(ключ)`: інвалідація ПІСЛЯ запису. Інший порядок
       залишає вікно, у якому читач поверне в кеш старі дані з БД;
    2. кеш НЕ оновлюється через `set` (інакше при гонці двох оновлень там може лишитись
       старе значення): видаляємо, а наступне читання підтягне свіже;
    3. `CacheError` при видаленні не скасовує вже виконаний запис; застарілий запис
       тимчасово живе до кінця TTL.
"""
from typing import Any


class CacheError(Exception):
    """Кеш недоступний."""


class UserService:
    def __init__(self, db: Any, cache: Any, ttl: int = 60, negative_ttl: int = 5):
        raise NotImplementedError

    def get_user(self, user_id: str) -> dict | None:
        raise NotImplementedError

    def update_user(self, user_id: str, data: dict) -> None:
        raise NotImplementedError
