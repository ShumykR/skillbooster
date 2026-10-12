"""Завдання №110: навантажувальне тестування: розбір результатів k6/Locust і пошук точки насичення.

Запустити k6 просто. Складніше зрозуміти результат: де система перестала масштабуватись і скільки інстансів потрібно під цільове
навантаження. Реалізуй аналіз.

percentile(values, p) -> float       метод nearest-rank: відсортувати, rank = ceil(p / 100 * n), результат values[rank - 1]. Обчислюй
                                     rank точно (через fractions.Fraction(str(p))), не через float. 0 < p <= 100, порожній список
                                     або p поза діапазоном: ValueError.
summarize(samples) -> dict           `samples`: [{"latency": секунди, "ok": bool}, ...] (помилкові запити теж мають затримку).
                                     {"count", "errors", "error_rate" (errors / count, 4 знаки), "p50", "p95", "p99", "max"}
                                     за затримками всіх запитів. Порожній список: ValueError.
check_thresholds(summary, limits) -> dict
                                     як thresholds у k6: limits {"p95": 0.3, "error_rate": 0.01, ...}; ключ проходить, якщо
                                     summary[key] <= limits[key]. Невідомий ключ у summary: ValueError.
                                     Результат {"passed": bool, "failed": відсортований список ключів, що не пройшли}.
find_saturation(steps, *, p95_limit, error_limit=0.01, gain_min=0.05) -> dict
                                     `steps`: [{"vus": n, "rps": пропускна здатність, "p95": секунди, "error_rate": частка}, ...]
                                     за зростанням vus (порожній список або vus не строго зростає: ValueError).
                                     Крок «поганий» за першою з умов: error_rate > error_limit -> "errors"; p95 > p95_limit ->
                                     "latency"; (не перший крок і попередній rps > 0) (rps - prev_rps) / prev_rps < gain_min
                                     -> "plateau" (навантаження зросло, а пропускна здатність майже ні, або впала).
                                     Береться ПЕРШИЙ поганий крок. Результат:
                                       "saturated_at": vus першого поганого кроку або None;
                                       "reason": "errors" | "latency" | "plateau" | None;
                                       "max_sustainable": vus останнього доброго кроку перед ним (None, якщо добрих немає;
                                                          якщо поганих немає, vus останнього кроку);
                                       "peak_rps": максимальний rps серед добрих кроків (0.0, якщо добрих немає).
little_law(rps, latency) -> float    закон Літтла: середня кількість запитів у системі = rps * latency.
required_instances(target_rps, rps_per_instance, headroom=0.3) -> int
                                     скільки інстансів потрібно, щоб кожен працював не вище (1 - headroom) від виміряної межі:
                                     ceil(target_rps / (rps_per_instance * (1 - headroom))), точно (Fraction(str(...))).
                                     target_rps < 0, rps_per_instance <= 0 або headroom не в [0, 1): ValueError.
"""


def percentile(values: list[float], p: float) -> float:
    raise NotImplementedError


def summarize(samples: list[dict]) -> dict:
    raise NotImplementedError


def check_thresholds(summary: dict, limits: dict) -> dict:
    raise NotImplementedError


def find_saturation(steps: list[dict], *, p95_limit: float, error_limit: float = 0.01, gain_min: float = 0.05) -> dict:
    raise NotImplementedError


def little_law(rps: float, latency: float) -> float:
    raise NotImplementedError


def required_instances(target_rps: float, rps_per_instance: float, headroom: float = 0.3) -> int:
    raise NotImplementedError
