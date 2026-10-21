"""Завдання №260: пріоритизація вразливостей (не «лише за CVSS»).

Сканер знайшов 400 CVE. CVSS каже «наскільки погано в найгіршому випадку», а не «наскільки
ймовірно, що це вдарить по нас». Тут ти пишеш два шари: `classify` (пріоритет і SLA для однієї
знахідки) і `triage` (терміни, винятки, ескалація для списку). Дані приходять готовими:
базовий бал CVSS, EPSS, ознака CISA KEV (відома експлуатація), reachability, актив.

Знахідка (`dict`):
    {"id": "CVE-2025-0001", "cvss": 9.8, "epss": 0.02, "in_kev": False,
     "reachable": True | False | None,          # None = невідомо, вважаємо досяжною
     "asset": {"internet_facing": bool, "criticality": "low"|"medium"|"high"|"critical"},
     "first_seen": "2026-10-01"}                # ISO-дата, потрібна лише для triage
Валідація (`ValueError`): `cvss` число 0..10, `epss` число 0..1, `in_kev` строго `bool`,
`reachable` `True`/`False`/`None`, `asset` обʼєкт з `internet_facing` (bool) і `criticality` з
переліку; `bool` не вважається числом.

`classify(finding) -> {"priority": "P0".."P4", "sla_days": int, "reasons": [str]}`
    SLA: P0=3, P1=14, P2=30, P3=90, P4=180 днів. Правила по порядку, перше підходяще вирішує:
    1. `in_kev` і `reachable is not False`: P0, reasons `["kev"]`.
    2. `in_kev` і `reachable is False`: P1, reasons `["kev-unreachable"]`.
    3. `epss >= 0.5` і `internet_facing` і `reachable is not False`: P0, `["epss-exposed"]`.
    4. Інакше рівень від CVSS (число 0..4 для P0..P4): `>= 9.0` P1 (`cvss-critical`),
       `>= 7.0` P2 (`cvss-high`), `>= 4.0` P3 (`cvss-medium`), інакше P4 (`cvss-low`).
       Далі модифікатори в такому порядку (кожен додає свій код у `reasons`, навіть якщо
       межа клемпу «з'їсть» зміну):
       * `epss >= 0.1`: на рівень терміновіше (`epss-elevated`);
       * `internet_facing` і `cvss >= 7.0`: на рівень терміновіше (`internet-facing`);
       * `criticality == "critical"`: на рівень терміновіше (`asset-critical`);
         `criticality == "low"`: на рівень менш термінове (`asset-low`);
       після цього рівень клемпиться в P1..P4 (P0 лише за правилами 1 і 3);
       нарешті `reachable is False`: рівень не терміновіший за P3 (`unreachable-cap`).
    `reasons`: у порядку застосування (код CVSS першим).

`triage(findings, exceptions, today) -> list[dict]`
    `today` це `datetime.date`. Для кожної знахідки результат
    `{"id", "priority", "sla_days", "reasons", "due", "status", "escalate_to"}`:
    * `due` = `first_seen` + `sla_days` (рядок ISO);
    * `status`: `"overdue"` якщо `today > due`; `"due-soon"` якщо `0 <= due - today <= 3` днів;
      `"ok"` інакше; `"excepted"` якщо діє валідний виняток (замість ok/due-soon/overdue);
    * `escalate_to` лише для `overdue`: прострочено на 1..7 днів `"team-lead"`, на 8..30
      `"security-lead"`, більше за 30 `"ciso"`; для P0 мінімум `"security-lead"`; інакше `None`.
    Виняток: `{"id", "owner", "reason", "expires"}` (одна знахідка, не більше одного винятку:
    дубль id це `ValueError`). Валідний, якщо: `owner` і `reason` непорожні після `strip()`,
    `expires` коректна ISO-дата, `expires >= today` (останній день діє), `expires - today <= 90`
    днів, пріоритет знахідки не P0. Невалідний виняток ігнорується, а в `reasons` знахідки
    додається `"exception-invalid:<чому>"` (у кінець): `no-owner`, `no-reason`, `bad-date`,
    `expired`, `too-long`, `p0` (перевіряй у цьому порядку, перше підходяще). Виняток для
    невідомого id це `ValueError`. Дубль id серед знахідок це `ValueError`.
    Порядок результату: за `(priority, due, id)`.
"""
from datetime import date

SLA_DAYS = {"P0": 3, "P1": 14, "P2": 30, "P3": 90, "P4": 180}


def classify(finding: dict) -> dict:
    raise NotImplementedError


def triage(findings: list[dict], exceptions: list[dict], today: date) -> list[dict]:
    raise NotImplementedError
