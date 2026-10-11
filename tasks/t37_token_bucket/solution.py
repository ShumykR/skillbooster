"""Завдання №37: Rate limiter (token bucket).

Окреме відро на кожен ключ (наприклад, користувача або IP).
"""
import time
from typing import Callable


class TokenBucket:
    def __init__(
        self,
        capacity: int,
        refill_per_sec: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.capacity = capacity
        self.refill_per_sec = refill_per_sec
        self._clock = clock

    def allow(self, key: str, cost: int = 1) -> bool:
        """True, якщо запит дозволено (токени списано)."""
        raise NotImplementedError

    def retry_after(self, key: str, cost: int = 1) -> float:
        """Через скільки секунд запит буде дозволено (0.0, якщо вже можна).

        Якщо cost > capacity, запит ніколи не пройде: поверни float('inf').
        """
        raise NotImplementedError
