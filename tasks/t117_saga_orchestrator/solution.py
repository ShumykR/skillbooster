"""Завдання №117: Saga: розподілена транзакція замовлення (склад, оплата, доставка) через оркестратор і компенсації.

Одна ACID-транзакція на кілька сервісів неможлива, тому замовлення це послідовність локальних кроків. Якщо крок k падає, уже виконані
кроки 1..k-1 не відкочуються «магією», а скасовуються компенсувальними діями у зворотному порядку (повернути резерв, повернути гроші).

Step = {"name": str, "action": callable(ctx), "compensate": callable(ctx) | None, "retries": int (типово 0)}
    ctx це словник, спільний для всіх кроків: action може записати в нього результат (payment_id), який потрібен компенсації.
NonRetryable(Exception): виняток, після якого action НЕ повторюється (наприклад, «недостатньо коштів»).

SagaOrchestrator(store, *, compensation_attempts=3)
    store це словник, що імітує надійне сховище (БД): стан кожної саги зберігається в store[saga_id] і пережиє «падіння процесу».
    .run(saga_id, steps, ctx=None) -> dict
        steps порожній або імена не унікальні: ValueError.
        Стан store[saga_id] = {"status", "completed": [імена виконаних кроків], "undone": [імена скасованих], "ctx": копія ctx,
        "error": рядок або None, "log": [...]}; його треба оновлювати ПІСЛЯ кожного завершеного кроку (done/undone), щоб після
        падіння процесу можна було продовжити.
        Статуси: "running" -> "completed"; або "running" -> "compensating" -> "compensated" | "failed".
        Виконання: кроки по черзі. Перед кожним викликом action в log додається "start:<імя>", після успіху "done:<імя>" (імʼя додається
        в completed, ctx зберігається). Невдача (виняток Exception): якщо це не NonRetryable і викликів було менше 1 + retries, виклик
        повторюється; інакше в log "failed:<імя>", error = f"{імя}: {ТипВинятку}: {текст}", статус "compensating". Виняток, що не є
        Exception (BaseException, імітація смерті процесу), НЕ перехоплюється: стан у store лишається як був.
        Компенсація: для виконаних кроків (completed, у зворотному порядку), яких ще немає в undone, і в яких compensate не None:
        перед кожним викликом "undo:<імя>", успіх "undone:<імя>" (імʼя в undone); до compensation_attempts викликів; якщо всі невдалі:
        "undo_failed:<імя>", статус "failed" (потрібне ручне втручання), решта кроків НЕ скасовується. Крок без compensate вважається
        скасованим без викликів і без записів у log (але додається в undone). Невдалий крок (той, що кинув виняток) не компенсується.
        Успішна компенсація всіх: статус "compensated".
        Повторний run з тим самим saga_id: "completed" або "compensated" повертає збережений результат, нічого не виконуючи;
        "running" продовжує з першого кроку, якого немає в completed (крок, що встиг виконатись, але не був записаний, виконується
        знову: at-least-once, тому action має бути ідемпотентним), ctx береться зі store; "compensating" та "failed" продовжують
        компенсацію. Імена в completed, яких немає в steps: ValueError.
        Результат: {"saga_id", "status", "completed", "undone", "error"} (копії списків).
"""


class NonRetryable(Exception):
    pass


class SagaOrchestrator:
    def __init__(self, store: dict, *, compensation_attempts: int = 3) -> None:
        raise NotImplementedError

    def run(self, saga_id: str, steps: list[dict], ctx: dict | None = None) -> dict:
        raise NotImplementedError
