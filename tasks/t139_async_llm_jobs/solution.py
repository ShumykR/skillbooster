"""Завдання №139: Асинхронні LLM-завдання: довга генерація через чергу, прогрес через SSE, скасування та відновлення потоку.

Генерація звіту займає хвилини, тож HTTP-запит так не тримають. Клієнт створює завдання (202 + job_id), воркер оновлює прогрес, а клієнт
дивиться події через SSE і після обриву з'єднання продовжує з Last-Event-ID. Реалізуй сховище завдань і форматування SSE.

JobManager(clock, *, max_active_per_owner=5, max_events=1000)
    .submit(owner, kind, payload, *, key=None) -> str
        id "j1", "j2", ... (лічильник на менеджер, зростає лише для НОВИХ завдань). key це ключ ідемпотентності: повторний submit того самого
        (owner, key) повертає id наявного завдання. Якщо у власника вже max_active_per_owner активних (queued або running) завдань, то
        TooManyJobs (для повтору за key перевірка не робиться). Створення записує подію 1 {"event": "status", "data": {"status": "queued"}}.
    .start(job_id) -> bool          queued -> running, подія status "running". Завершене завдання (succeeded/failed/cancelled): False. Не queued і не
                                    завершене (вже running): ValueError. Невідомий id: KeyError.
    .progress(job_id, percent=None, message="") -> bool
        Лише для running (завершене: False; queued: ValueError). percent це ціле 0..100 або None (інакше ValueError). Подія
        {"event": "progress", "data": {"percent": percent, "message": message}}. Якщо percent не None і вже було
        прийняте значення percent, а новий НЕ більший за останнє прийняте, подія не створюється: False. Інакше True; прийняте значення
        запамʼятовується (для None нічого не змінюється, подія створюється завжди). Перше значення будь-яке (навіть 0).
    .complete(job_id, result) -> bool    running -> succeeded, прогрес 100; події {"event": "result", "data": {"result": result}}, потім status
                                    "succeeded". Завершене: False. queued: ValueError.
    .fail(job_id, error) -> bool         running або queued -> failed; події {"event": "error", "data": {"error": str(error)}}, потім status "failed".
                                    Завершене: False.
    .cancel(job_id, owner) -> bool       власник скасовує queued чи running: status "cancelled" (одна подія), True. Завершене: False.
                                    Чужий власник або невідомий id: KeyError.
    .get(job_id, owner) -> dict          {"id", "kind", "status", "progress", "result", "error", "created", "finished"}  (progress: останнє прийняте значення, 0 якщо не було, 100 після complete) (created/finished це clock() у момент
                                    створення та завершення, finished None до завершення; result/error None, поки немає). Чужий або невідомий: KeyError.
    .events(job_id, owner, last_event_id=0) -> list[dict]
        Події {"id": 1.., "event", "data"} з id > last_event_id. Чужий або невідомий job_id: KeyError (однаково, щоб не розкривати чужі id).
        Зберігаються лише останні max_events подій; id не перенумеровуються.
    .purge(max_age) -> int               видаляє завершені завдання, що завершились понад max_age секунд тому (clock() - finished > max_age);
                                    повертає кількість. Активні не чіпає.
    Подія завершення: після неї статус остаточний. TooManyJobs це Exception.

format_sse(event) -> str             f"id: {id}\\nevent: {event}\\ndata: {json}\\n\\n", де json = json.dumps(data, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).
KEEPALIVE = ": ping\\n\\n"

stream_chunks(manager, job_id, owner, last_event_id=0) -> tuple[list[str], bool]
    SSE-рядки для подій з id > last_event_id і прапорець finished: True, якщо завдання завершене (клієнту можна закривати потік). Якщо нових
    подій немає й завдання не завершене, список містить один KEEPALIVE.
"""

import json  # noqa: F401

KEEPALIVE = ": ping\n\n"


class TooManyJobs(Exception):
    pass


class JobManager:
    def __init__(self, clock, *, max_active_per_owner: int = 5, max_events: int = 1000) -> None:
        raise NotImplementedError

    def submit(self, owner: str, kind: str, payload, *, key: str | None = None) -> str:
        raise NotImplementedError

    def start(self, job_id: str) -> bool:
        raise NotImplementedError

    def progress(self, job_id: str, percent: int | None = None, message: str = "") -> bool:
        raise NotImplementedError

    def complete(self, job_id: str, result) -> bool:
        raise NotImplementedError

    def fail(self, job_id: str, error) -> bool:
        raise NotImplementedError

    def cancel(self, job_id: str, owner: str) -> bool:
        raise NotImplementedError

    def get(self, job_id: str, owner: str) -> dict:
        raise NotImplementedError

    def events(self, job_id: str, owner: str, last_event_id: int = 0) -> list[dict]:
        raise NotImplementedError

    def purge(self, max_age: float) -> int:
        raise NotImplementedError


def format_sse(event: dict) -> str:
    raise NotImplementedError


def stream_chunks(manager: JobManager, job_id: str, owner: str, last_event_id: int = 0) -> tuple[list[str], bool]:
    raise NotImplementedError
