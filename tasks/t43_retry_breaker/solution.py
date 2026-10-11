"""Завдання №43: Retry з backoff і circuit breaker."""
import random
import time
from typing import Callable, TypeVar

T = TypeVar("T")


def retry(
    fn: Callable[[], T],
    *,
    attempts: int = 4,
    base_delay: float = 0.1,
    max_delay: float = 2.0,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    sleep: Callable[[float], None] = time.sleep,
    jitter: Callable[[], float] = random.random,
) -> T:
    """Викликає fn до `attempts` разів.

    Перед спробою №(i+2) чекає min(max_delay, base_delay * 2**i) * jitter() секунд.
    Виняток, якого немає в retry_on, піднімається одразу. Після останньої
    невдалої спроби піднімається останній виняток.
    """
    raise NotImplementedError


class CircuitOpenError(Exception):
    pass


class CircuitBreaker:
    """closed → open після `failure_threshold` невдач ПІДРЯД.

    У стані open виклики одразу кидають CircuitOpenError, fn не викликається.
    Через `reset_timeout` секунд стан half_open: пропускається один пробний виклик;
    успіх закриває розмикач, невдача знову відкриває (таймер стартує заново).
    Будь-який успіх обнуляє лічильник невдач.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        reset_timeout: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self._clock = clock

    @property
    def state(self) -> str:
        """"closed" | "open" | "half_open" """
        raise NotImplementedError

    def call(self, fn: Callable[[], T]) -> T:
        raise NotImplementedError
