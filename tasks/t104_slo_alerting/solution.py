"""Завдання №104: алерти за SLO (burn rate), а не за CPU.

SLO 99.9% за 30 днів означає error budget 0.1%: стільки запитів можна провалити. Алерт «CPU > 80%» нічого не каже про користувачів.
Алерт за швидкістю спалювання бюджету (burn rate) каже: «при такій частці помилок бюджет скінчиться за N годин».
burn rate = частка помилок / (1 - SLO); 1.0 означає, що бюджет закінчиться рівно наприкінці вікна.

Усі функції перевіряють аргументи: slo не в (0, 1), частка помилок не в [0, 1], від'ємні кількості: ValueError.

error_budget(slo, window_days=30) -> dict      {"budget_ratio": 1 - slo (округлено до 10 знаків),
                                                "allowed_downtime_min": window_days * 1440 * (1 - slo), округлено до 2 знаків}
burn_rate(error_ratio, slo) -> float           error_ratio / (1 - slo), без округлення
budget_consumed(burn, window_hours, window_days=30) -> float
    частка місячного бюджету, спожита за window_hours при сталому burn: burn * window_hours / (window_days * 24), 6 знаків.
hours_to_exhaustion(burn, remaining=1.0, window_days=30) -> float | None
    за скільки годин закінчиться залишок бюджету (частка від повного) при сталому burn: remaining * window_days * 24 / burn,
    2 знаки; burn <= 0: None (ніколи).

error_ratio(good, total) -> float              1 - good / total; total == 0 -> 0.0 (немає запитів, немає помилок). good > total: ValueError.
latency_sli(durations, threshold) -> float     частка тривалостей <= threshold; порожній список -> 1.0.
budget_status(good, total, slo) -> dict
    {"sli": good / total (total == 0 -> 1.0), "meets_slo": sli >= slo, "consumed": bad / (total * (1 - slo)) округлено до 4 знаків
     (total == 0 -> 0.0; може бути > 1), "remaining": round(1 - consumed, 4)}, де bad = total - good.
release_policy(consumed) -> str                "normal" (consumed < 0.5), "caution" (0.5 <= consumed < 1), "freeze" (consumed >= 1):
                                                що команда робить із релізами, коли бюджет закінчується.

DEFAULT_POLICY: правила Google SRE Workbook (multi-window, multi-burn-rate). Кожне правило
    {"severity": "page"|"ticket", "long": "1h", "short": "5m", "factor": 14.4}:
    ("page", 1h, 5m, 14.4), ("page", 6h, 30m, 6), ("ticket", 1d, 2h, 3), ("ticket", 3d, 6h, 1).
evaluate_alerts(slo, ratios, policy=DEFAULT_POLICY) -> list[dict]
    `ratios`: {мітка вікна: частка помилок у цьому вікні}. Правило спрацьовує, коли burn rate СТРОГО більший за factor в ОБОХ
    вікнах (довге ловить реальну проблему, коротке гарантує, що вона триває зараз, а не вже минула). Правило, для якого немає
    даних хоча б по одному вікну, пропускається. Повертає спрацьовані правила (словники правил як є) у порядку політики.
highest_severity(alerts) -> str | None          "page", якщо є хоч один page, інакше "ticket", інакше None.
alert_expr(slo, long, short, factor, metric="job:slo_errors_per_request:ratio_rate") -> str
    вираз PromQL: f"{metric}{long} > ({factor} * {budget}) and {metric}{short} > ({factor} * {budget})", де factor і budget
    форматуються як f"{x:g}", а budget = round(1 - slo, 10). Приклад: slo 0.999, "1h", "5m", 14.4 ->
    "job:slo_errors_per_request:ratio_rate1h > (14.4 * 0.001) and job:slo_errors_per_request:ratio_rate5m > (14.4 * 0.001)".
"""

DEFAULT_POLICY = (
    {"severity": "page", "long": "1h", "short": "5m", "factor": 14.4},
    {"severity": "page", "long": "6h", "short": "30m", "factor": 6},
    {"severity": "ticket", "long": "1d", "short": "2h", "factor": 3},
    {"severity": "ticket", "long": "3d", "short": "6h", "factor": 1},
)


def error_budget(slo: float, window_days: int = 30) -> dict:
    raise NotImplementedError


def burn_rate(error_ratio: float, slo: float) -> float:
    raise NotImplementedError


def budget_consumed(burn: float, window_hours: float, window_days: int = 30) -> float:
    raise NotImplementedError


def hours_to_exhaustion(burn: float, remaining: float = 1.0, window_days: int = 30) -> float | None:
    raise NotImplementedError


def error_ratio(good: int, total: int) -> float:
    raise NotImplementedError


def latency_sli(durations: list[float], threshold: float) -> float:
    raise NotImplementedError


def budget_status(good: int, total: int, slo: float) -> dict:
    raise NotImplementedError


def release_policy(consumed: float) -> str:
    raise NotImplementedError


def evaluate_alerts(slo: float, ratios: dict[str, float], policy=DEFAULT_POLICY) -> list[dict]:
    raise NotImplementedError


def highest_severity(alerts: list[dict]) -> str | None:
    raise NotImplementedError


def alert_expr(slo: float, long: str, short: str, factor: float, metric: str = "job:slo_errors_per_request:ratio_rate") -> str:
    raise NotImplementedError
