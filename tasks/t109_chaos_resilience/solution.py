"""Завдання №109: chaos-тест «убили Redis»: кеш, який не валить запит (timeout, fallback, circuit breaker).

Кеш прискорює запити, але не повинен їх ламати. Коли Redis недоступний, застосунок має віддавати дані з джерела істини (БД), а не
500; коли Redis «висить», кожен запит не повинен чекати його таймаут; а коли Redis одужав, кеш має повернутись без ручного втручання.

ResilientCache(backend, loader, *, clock, ttl=60, timeout=0.1, failure_threshold=3, reset_timeout=30)
    backend.get(key, timeout=...) -> значення або None (промах); backend.set(key, value, ttl=..., timeout=...). Обидва можуть
    кинути ConnectionError або TimeoutError (інші винятки це баги й летять нагору без обробки). Кожен виклик backend ОБОВʼЯЗКОВО
    отримує `timeout` (без нього завислий Redis зависить увесь запит).
    loader(key) -> значення з джерела істини (БД); його винятки не перехоплюються. Якщо loader повертає None, значення не кешується.
    clock() -> секунди (float), у тестах керований.

    .get(key) -> значення:
      * стан "closed" або "half-open": backend.get; є значення (не None) -> віддати (hit); None -> loader(key), потім спроба
        backend.set(key, value, ttl=ttl, timeout=timeout) (miss); помилка set рахується як помилка backend, але значення віддається;
      * помилка backend.get (ConnectionError/TimeoutError): loader(key) і віддати його значення (fallback);
      * стан "open": backend не викликається взагалі, одразу loader(key) (short_circuited).
    Circuit breaker: кожна помилка backend збільшує лічильник поспіль; будь-яка успішна операція backend скидає його до 0.
    Коли лічильник досягає failure_threshold, breaker відкривається: opened_at = clock(). Стан:
      "closed"     opened_at немає;
      "open"       opened_at є, і clock() - opened_at < reset_timeout;
      "half-open"  opened_at є, і clock() - opened_at >= reset_timeout (пробний запит): успіх закриває breaker, помилка
                   відкриває його знову (opened_at = clock()) на новий reset_timeout.
    .state -> "closed" | "open" | "half-open"
    .metrics -> dict з лічильниками "hits", "misses", "errors" (кожна оброблена помилка backend, get чи set),
                "fallbacks" (запити get, що пішли в loader через помилку backend.get), "short_circuited".
"""


class ResilientCache:
    def __init__(self, backend, loader, *, clock, ttl: float = 60, timeout: float = 0.1, failure_threshold: int = 3,
                 reset_timeout: float = 30) -> None:
        raise NotImplementedError

    @property
    def state(self) -> str:
        raise NotImplementedError

    @property
    def metrics(self) -> dict:
        raise NotImplementedError

    def get(self, key):
        raise NotImplementedError
