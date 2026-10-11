"""Завдання №150: декоратор, що не ламає функцію.

`observed` вимірює виклик і передає результат у `sink`. Його можна вживати двома способами:
    @observed                                  # без дужок
    @observed(clock=..., sink=..., name="x")   # з параметрами

Параметри (усі іменовані): clock=time.perf_counter, sink=None (нічого не робити), name=None (за замовчуванням
`func.__qualname__`).

Після кожного виклику (успішного чи ні) викликається `sink({"name": str, "seconds": float, "ok": bool,
"error": str | None})`, де `seconds = clock() після - clock() до`, `error` це ім'я класу винятку
(`"ValueError"`) або None. Рівно ОДИН виклик `clock` до і ОДИН після, ніяких інших.

Вимоги до обгортки:
    * результат повертається як є, виняток піднімається ТОЙ САМИЙ об'єкт (не замінений і не загорнутий);
    * зберігає `__name__`, `__qualname__`, `__doc__`, `__module__`, `__wrapped__` і `inspect.signature`;
    * звичайні функції, `async def` і методи класів: для async вимірюється час до ЗАВЕРШЕННЯ корутини
      (а не до її створення), `inspect.iscoroutinefunction(обгортка)` це True, для sync False;
    * помилка в самому `sink` не маскує результат чи виняток функції (її можна проковтнути);
    * CancelledError у async-функції теж фіксується (`ok=False`, `error="CancelledError"`) і піднімається далі.
"""
import time


def observed(func=None, *, clock=time.perf_counter, sink=None, name=None):
    raise NotImplementedError
