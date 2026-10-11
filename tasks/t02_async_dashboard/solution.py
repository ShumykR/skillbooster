"""Завдання №2: Async під навантаженням.

Реалізуй fetch_dashboard: викликає всі сервіси ПАРАЛЕЛЬНО, але не більше
`max_concurrency` одночасно, і кожному дає `timeout` секунд.
Збій або таймаут одного сервісу не має ламати відповідь.
"""
from typing import Any, Awaitable, Callable

Service = Callable[[int], Awaitable[Any]]


async def fetch_dashboard(
    user_id: int,
    services: dict[str, Service],
    *,
    timeout: float = 0.5,
    max_concurrency: int = 2,
) -> dict[str, dict[str, Any]]:
    """Повертає {"data": {імʼя: результат}, "errors": {імʼя: "timeout" | "error"}}."""
    raise NotImplementedError
