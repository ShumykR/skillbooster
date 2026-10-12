"""Завдання №90: Керування витратами: бюджети, теги і розбір «чому рахунок виріс».

Дані вигрузки Cost Explorer / CUR це список рядків-витрат:
  {"service": "AmazonEC2", "account": "prod", "usage_type": "BoxUsage:m5.large", "tags": {"team": "search"}, "cost": 12.5}
(`tags` може бути відсутнім або без потрібного ключа).

cost_diff(prev, cur, *, by="service", top=None) -> list[dict]
    Порівняння двох періодів. `by`: "service", "account", "usage_type" або "tag:<ключ>" (рядок без тега чи з порожнім
    значенням потрапляє в групу "(untagged)"). Результат: [{"key", "prev", "cur", "delta", "pct"}], де суми по групі
    округлені до 2 знаків, delta = cur - prev (після округлення сум), pct = round(delta / prev * 100, 1) або None, якщо
    prev == 0 (нова стаття витрат). Групи, що є хоч в одному періоді. Порядок: delta за спаданням, при рівності key за зростанням.
    `top`: залишити перші N записів. Невідомий `by`: ValueError.
budget_alerts(spend, budget, day, days_in_month, thresholds=(50, 80, 100)) -> list[str]
    `spend` витрачено за `day`-й день місяця включно (1-based). budget <= 0 або day поза 1..days_in_month: ValueError.
    Повертає, у такому порядку: "actual_<N>" для кожного N з thresholds (за зростанням), якщо spend >= budget * N / 100;
    потім "forecast_100", якщо day >= 3 і прогноз `spend / day * days_in_month` СТРОГО більший за budget
    (до третього дня прогноз надто шумний). Прогноз не дублюється, коли це вже "actual_100"-випадок: тоді ("actual_100" є)
    "forecast_100" все одно не додається.
daily_anomalies(costs, *, window=7, factor=2.0, min_increase=10.0) -> list[int]
    Індекси днів i >= window, де costs[i] > factor * mean(costs[i-window:i]) І costs[i] - mean >= min_increase
    (крихітні суми не спрацьовують). Порожній результат, якщо даних менше за window + 1.
untagged_report(items, tag) -> dict
    {"untagged": сума витрат без тега `tag` (немає ключа або порожнє значення), "total": загальна сума, "share": untagged/total
    округлене до 4 знаків (0.0, якщо total == 0), "top_services": до 3 сервісів із найбільшою untagged-сумою як
    [(service, sum), ...] за спаданням суми, при рівності за назвою}. Суми округлені до 2 знаків.
"""


def cost_diff(prev: list[dict], cur: list[dict], *, by: str = "service", top: int | None = None) -> list[dict]:
    raise NotImplementedError


def budget_alerts(spend: float, budget: float, day: int, days_in_month: int, thresholds: tuple[int, ...] = (50, 80, 100)) -> list[str]:
    raise NotImplementedError


def daily_anomalies(costs: list[float], *, window: int = 7, factor: float = 2.0, min_increase: float = 10.0) -> list[int]:
    raise NotImplementedError


def untagged_report(items: list[dict], tag: str) -> dict:
    raise NotImplementedError
