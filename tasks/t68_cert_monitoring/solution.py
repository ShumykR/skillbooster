"""Завдання №68: HTTPS і сертифікати: моніторинг терміну й автооновлення.

Інцидент «certificate expired» майже завжди означає, що автооновлення мовчки зламалось тижні тому, а ніхто не дивився.
Реалізуй три речі, з яких складається нормальний моніторинг (мережі немає: сертифікат уже розібрано в `CertInfo`,
час передається параметром `now`, секунди від епохи).

hostname_matches(pattern, host) -> bool    (правила RFC 6125 так, як їх застосовують браузери)
    * порівняння без урахування регістру, кінцева крапка в імені ігнорується;
    * `*` дозволено ЛИШЕ як повну крайню ліву мітку (`*.example.com`) і він збігається рівно з ОДНІЄЮ непорожньою
      міткою: `www.example.com` так, `example.com` ні, `a.b.example.com` ні;
    * часткові підстановки (`f*.example.com`, `*oo.example.com`) і `*` не в крайній лівій мітці не збігаються ніколи;
    * після `*.` має лишатись щонайменше дві мітки (`*.com` не збігається ні з чим);
    * шаблон без `*` порівнюється точно.
days_left(not_after, now) -> int: ціле число повних діб до закінчення, `floor((not_after - now) / 86400)`;
    від'ємне, якщо вже прострочено.
check_certificate(cert, host, now, *, warn_days=21, crit_days=7) -> dict
    {"status": ..., "days_left": int, "problems": [відсортовані коди]}. Коди проблем:
    * "expired": now > not_after;  "not_yet_valid": now < not_before;
    * "hostname_mismatch": жоден запис `sans` не збігається з `host` за `hostname_matches` (CN не враховується,
      сучасні клієнти дивляться лише на SAN, навіть якщо `sans` порожній);
    * "chain_incomplete": `chain_ok` це False (сервер не віддав проміжний сертифікат);
    * "self_signed": `issuer == subject`;
    * "validity_too_long": (not_after - not_before) більше за 398 діб (інформаційна, на status не впливає).
    status: "expired", якщо є "expired"; інакше "invalid", якщо є хоч один із "not_yet_valid", "hostname_mismatch",
    "chain_incomplete", "self_signed"; інакше за терміном: days_left <= crit_days це "critical",
    days_left <= warn_days це "warning", решта "ok".
should_renew(not_after, now, *, renew_before_days=30, last_attempt=None, failures=0, issued_this_week=0) -> dict
    {"renew": bool, "reason": str}. Порядок рішень:
    1. days_left > renew_before_days -> False, "not_due";
    2. issued_this_week >= 5 -> False, "rate_limited" (ліміт Let's Encrypt на дублікати);
    3. days_left < 0 -> True, "expired" (затримок немає);
    4. failures == 0 -> True, "due";
    5. пауза після невдач: `min(86400, 3600 * 2**(failures-1))` секунд від `last_attempt`; якщо ще не минула ->
       False, "backoff", інакше True, "retry".
monitor(certs, now, **thresholds) -> dict
    `certs`: список пар (host, CertInfo). Повертає {"exit_code": 0|1|2, "items": [...]}, де кожен елемент
    {"host", "status", "days_left", "problems"}; items впорядковані за серйозністю (expired, invalid, critical,
    warning, ok), далі за days_left за зростанням, далі за host. exit_code як у Nagios: 0 якщо всі ok,
    1 якщо найгірший warning, 2 для critical/invalid/expired. Порожній список це exit_code 0.
"""
import math  # noqa: F401
from dataclasses import dataclass, field

DAY = 86400


@dataclass
class CertInfo:
    subject: str
    issuer: str
    not_before: float
    not_after: float
    sans: list[str] = field(default_factory=list)
    chain_ok: bool = True


def hostname_matches(pattern: str, host: str) -> bool:
    raise NotImplementedError


def days_left(not_after: float, now: float) -> int:
    raise NotImplementedError


def check_certificate(cert: CertInfo, host: str, now: float, *, warn_days: int = 21, crit_days: int = 7) -> dict:
    raise NotImplementedError


def should_renew(
    not_after: float,
    now: float,
    *,
    renew_before_days: int = 30,
    last_attempt: float | None = None,
    failures: int = 0,
    issued_this_week: int = 0,
) -> dict:
    raise NotImplementedError


def monitor(certs: list[tuple[str, CertInfo]], now: float, **thresholds) -> dict:
    raise NotImplementedError
