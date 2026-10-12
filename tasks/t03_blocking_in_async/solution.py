"""Завдання №3: Блокуючий код в async.

`build_reports` збирає PDF для списку користувачів. `load_user` це async-виклик
(мережа/БД), а `render_pdf` звичайна синхронна функція: CPU або блокуючий I/O.
Поки `render_pdf` виконується прямо в async-функції, event loop стоїть і вся
решта запитів сервісу чекає.

Виправ так, щоб:
- event loop не блокувався рендером;
- одночасно рендерилось не більше `max_parallel` PDF;
- порядок результатів збігався з порядком `user_ids`;
- збій рендеру одного користувача не ламав решту: `{"user_id": id, "error": "<текст>"}`.
"""
from typing import Any, Awaitable, Callable


async def build_reports(
    user_ids: list[int],
    load_user: Callable[[int], Awaitable[Any]],
    render_pdf: Callable[[Any], bytes],
    *,
    max_parallel: int = 4,
) -> list[dict[str, Any]]:
    """Повертає [{"user_id": id, "pdf": bytes} | {"user_id": id, "error": str}, ...]."""
    results = []
    for user_id in user_ids:
        user = await load_user(user_id)
        results.append({"user_id": user_id, "pdf": render_pdf(user)})  # блокує event loop
    return results
