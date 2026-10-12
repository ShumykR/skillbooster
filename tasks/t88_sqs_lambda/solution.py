"""Завдання №88: Lambda + SQS: подієва обробка, DLQ, ідемпотентність.

SQS гарантує доставку «щонайменше раз»: те саме повідомлення може прийти двічі, а пачка з 10 повідомлень, у якій одне
«отруйне» (poison), без обробки помилок повторюється ЦІЛКОМ і вдруге платить за 9 уже виконаних. Реалізуй обробник пачки,
який (1) не виконує одну дію двічі, (2) повертає SQS лише ті повідомлення, що справді не вдались (partial batch response),
(3) не ламає порядок у FIFO-черзі. Саму чергу, повторні доставки й переміщення в DLQ (redrive policy з maxReceiveCount) робить SQS.

IdempotencyStore (вже реалізований, використовуй його; в реальності це DynamoDB з умовним записом `attribute_not_exists`)
    begin(key, now) -> "acquired" | "done" | "busy": "done" якщо ключ уже успішно оброблено; "busy" якщо його обробляє інший
    виклик і блокування (lock_ttl секунд) ще не минуло; інакше блокування береться ("acquired").
    complete(key, now): ключ оброблено назавжди. release(key): зняти блокування (обробка не вдалась, повтор дозволено).

process_batch(event, handler, store, *, now, fifo=False) -> dict
    `event`: {"Records": [{"messageId": str, "body": str (JSON), ...}, ...]}. `handler(payload: dict)` виконує дію й кидає виняток
    при невдачі. Повертає {"batchItemFailures": [{"itemIdentifier": messageId}, ...]} у порядку записів; успішні й дублікати
    не повертаються (SQS видалить їх).
    Для кожного запису по порядку:
    * ключ ідемпотентності: поле `event_id` з JSON (рядок або число, перетворене на рядок; порожнє/відсутнє: ігнорується),
      інакше `messageId`. Один ключ може прийти з різними messageId, наприклад дубль від продюсера;
    * body не JSON-обʼєкт (не парситься або не словник): запис вважається невдалим, handler не викликається, store не чіпаємо;
    * store.begin: "done" -> дубль, успіх без виклику handler; "busy" -> невдача (SQS спробує пізніше), handler не викликається;
      "acquired" -> викликати handler: успіх -> store.complete і запис не повертається; будь-який виняток ->
      store.release і запис повертається як невдалий;
    * обробка однієї пачки не зупиняється на невдачі (інші записи виконуються), КРІМ fifo=True: після першої невдачі
      всі наступні записи пачки повертаються як невдалі БЕЗ виклику handler і без звернення до store (порядок у FIFO-черзі
      не можна переставляти).
"""
import json  # noqa: F401
from typing import Callable


class IdempotencyStore:
    def __init__(self, lock_ttl: float = 300) -> None:
        self.lock_ttl = lock_ttl
        self._items: dict[str, tuple[str, float]] = {}

    def begin(self, key: str, now: float) -> str:
        state = self._items.get(key)
        if state is not None:
            status, stamp = state
            if status == "done":
                return "done"
            if now - stamp < self.lock_ttl:
                return "busy"
        self._items[key] = ("in_progress", now)
        return "acquired"

    def complete(self, key: str, now: float) -> None:
        self._items[key] = ("done", now)

    def release(self, key: str) -> None:
        if self._items.get(key, ("",))[0] == "in_progress":
            del self._items[key]


def process_batch(
    event: dict,
    handler: Callable[[dict], None],
    store: IdempotencyStore,
    *,
    now: float,
    fifo: bool = False,
) -> dict:
    raise NotImplementedError
