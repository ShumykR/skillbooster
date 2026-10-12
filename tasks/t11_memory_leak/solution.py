"""Завдання №11: Memory leak.

Сервіс мініатюр працює добу, і його пам'ять росте до OOM-kill. Знайди витоки
(tracemalloc показує, які рядки утримують найбільше) і виправ ТАК, щоб поведінка
не змінилась:
- кеш мініатюр спільний для запитів: ключ це (user_id, size), а не запит;
  повторний запит того самого користувача й розміру не перерахувавшись віддає кеш;
- кеш обмежений `cache_size` записами (витісняється найдавніше використаний);
- після обробки запиту на шині не лишається підписок.
"""
from typing import Any, Callable


class EventBus:
    def __init__(self) -> None:
        self._listeners: list[Callable[[Any], None]] = []

    def subscribe(self, fn: Callable[[Any], None]) -> None:
        self._listeners.append(fn)

    def unsubscribe(self, fn: Callable[[Any], None]) -> None:
        self._listeners.remove(fn)

    def emit(self, event: Any) -> None:
        for fn in list(self._listeners):
            fn(event)

    def listener_count(self) -> int:
        return len(self._listeners)


class ThumbnailService:
    def __init__(self, bus: EventBus, cache_size: int = 128) -> None:
        self.bus = bus
        self.cache_size = cache_size
        self.compute_count = 0
        self._cache: dict[tuple, bytes] = {}

    def cache_len(self) -> int:
        return len(self._cache)

    def handle(self, request_id: int, user_id: int, size: int, payload: bytes) -> bytes:
        key = (request_id, user_id, size)
        if key in self._cache:
            return self._cache[key]

        seen: list[tuple] = []

        def on_event(event: Any) -> None:
            seen.append((event, payload))

        self.bus.subscribe(on_event)
        thumbnail = bytes(payload[:size])  # «рендер»
        self.compute_count += 1
        self.bus.emit(("rendered", request_id))
        self._cache[key] = thumbnail
        return thumbnail
