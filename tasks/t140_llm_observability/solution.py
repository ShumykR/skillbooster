"""Завдання №140: Observability для LLM: трасування викликів, вартість, затримка, помилки (як Langfuse/OpenTelemetry у мініатюрі).

Без трасування не відповісти на питання «чому відповідь була повільною/дорогою/неправильною». Реалізуй трасувальник: trace це один запит
користувача, span це крок усередині (пошук, виклик інструмента), generation це виклик моделі з токенами й вартістю.

LlmTracer(clock, prices, *, max_traces=1000, capture_content=False)
    prices: {"model": {"in": USD за 1M вхідних токенів, "out": USD за 1M вихідних}}.
    .trace(name, *, user=None, tags=()) -> контекстний менеджер, що віддає Trace. На виході (також при винятку, який потім летить далі)
        trace завершується й додається в .traces (зберігаються лише останні max_traces). Trace це словник:
        {"id": "t1", "t2", ... (лічильник на трасувальник), "name", "user", "tags": list(tags), "start", "end", "duration", "status": "ok" | "error",
         "error": None | "<ТипВинятку>: <текст>", "spans": [...], "cost": сума cost generation (None не рахуються), round(.., 6), "tokens": сума
         prompt_tokens + completion_tokens усіх generation}.
        status "error" і error заповнюються, лише якщо виняток вийшов за межі блоку trace (виняток, який
        спіймали всередині блоку, trace не ламає, хоча span, через який він пройшов, отримує status "error").
    .traces -> list[dict]       завершені trace за порядком завершення (копія списку).
    .report() -> dict           підсумок по завершених trace (див. нижче).

Trace (об'єкт всередині with):
    .span(name, **attrs) -> контекстний менеджер, що віддає словник span. Span:
        {"id": "s1", "s2", ... у межах trace, "parent": id відкритого на цей момент span або None, "kind": "span", "name", "start", "end", "duration",
         "status": "ok" | "error", "error": None | "<Тип>: <текст>", "attrs": attrs}. Вкладення дозволені. Виняток span записується й летить далі.
    .generation(name, model, prompt) -> контекстний менеджер, що віддає Generation (g). Span з додатковими полями:
        "kind": "generation", "model", "prompt_chars": len(prompt), "prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0, "ttft": None,
        "output_chars": 0; а також "input" (= prompt) та "output" (None до finish) лише якщо capture_content=True (за замовчуванням тексти НЕ зберігаються: приватність).
        g.first_token(): уперше викликана записує ttft = clock() - start generation (повторні виклики ігноруються).
        g.finish(output, usage): usage {"prompt_tokens", "completion_tokens"} (відсутні = 0); ставить поля токенів, output_chars = len(output),
        cost = round((prompt*in + completion*out) / 1e6, 6) за prices; невідома модель: cost None. finish викликається не більше разу
        (повторний: RuntimeError). Без finish поля лишаються початковими.
    Після завершення trace виклики span/generation: RuntimeError.

report() -> dict
    {"traces": n, "errors": кількість trace зі status "error", "error_rate": round(errors / n, 4) (0.0 без trace),
     "latency": {"p50", "p95"} за duration trace (nearest-rank: відсортувати, елемент з індексом ceil(p * n / 100) - 1, цілочисельно; None без trace),
     "cost": round(сума cost trace, 6), "tokens": сума tokens,
     "by_model": {model: {"calls": кількість generation, "cost": сума (None не рахується, round 6), "prompt_tokens", "completion_tokens"}},
     "by_user": {user: {"traces": n, "cost": round(.., 6)}} лише для trace з user,
     "slowest": id трьох найповільніших trace (за duration спаданням, при рівності за id як рядком за зростанням)}.
"""

from contextlib import contextmanager  # noqa: F401


class LlmTracer:
    def __init__(self, clock, prices: dict, *, max_traces: int = 1000, capture_content: bool = False) -> None:
        raise NotImplementedError

    def trace(self, name: str, *, user: str | None = None, tags=()):
        raise NotImplementedError

    @property
    def traces(self) -> list[dict]:
        raise NotImplementedError

    def report(self) -> dict:
        raise NotImplementedError
