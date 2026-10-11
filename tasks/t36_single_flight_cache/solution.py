"""Завдання №36: Cache stampede.

Кеш із TTL, який при 1000 одночасних запитах на протухлий ключ
викликає loader лише ОДИН раз (single-flight).
"""
import time
from typing import Any, Awaitable, Callable


class SingleFlightCache:
    def __init__(
        self,
        loader: Callable[[str], Awaitable[Any]],
        ttl: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._loader = loader
        self._ttl = ttl
        self._clock = clock

    async def get(self, key: str) -> Any:
        raise NotImplementedError
