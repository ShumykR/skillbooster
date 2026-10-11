"""Завдання №70: розбір звіту сканера образів (Trivy) для CI-гейта.

Вхід `report` це розібраний JSON від `trivy image --format json`:
`{"Results": [{"Target": "app (debian 12)", "Vulnerabilities": [ {...}, ... ]}, ...]}`.
Уразливість: `VulnerabilityID`, `PkgName`, `InstalledVersion`, `FixedVersion` (може бути відсутнє
або порожнє = виправлення ще немає), `Severity`. У результата `Vulnerabilities` може бути
відсутнім або `None`.

Рівні: UNKNOWN < LOW < MEDIUM < HIGH < CRITICAL. Регістр у вхідних даних ігноруй, невідоме
або відсутнє значення `Severity` це "UNKNOWN".

`parse_findings(report) -> list[dict]`: плаский список знахідок із ключами
`id`, `pkg`, `installed`, `fixed` (рядок або None), `severity` (UPPER), `target`.
Дублікати (однакові id, pkg, installed, target) лишай один раз. Порядок: спершу серйозніші,
далі за `id`, далі за `pkg`.

`triage(report, policy, today) -> dict`. `policy`:
    {"fail_on": "HIGH",            # блокують знахідки цього рівня й вище (за замовчуванням "HIGH")
     "only_fixable": True,         # блокують лише ті, що мають FixedVersion (за замовчуванням True)
     "ignore": [{"id": "CVE-2024-1", "until": "2026-12-31", "reason": "...", "pkg": "zlib"}]}
`today` це `datetime.date`. Запис ignore:
- `until` (ISO-дата) обовʼязковий, ігнорування без терміну заборонене: `ValueError`;
  некоректна дата теж `ValueError`; `reason` обовʼязковий і непорожній: `ValueError`;
- діє, поки `today <= until` (останній день включно); `pkg` необовʼязковий і звужує запис
  до одного пакета;
- прострочений запис нічого не ігнорує, а його `id` потрапляє в `expired_ignores`.
Невідомий `fail_on` це `ValueError`.

Результат: {"blocking": [...знахідки...],              # у порядку parse_findings
            "ignored": [{"finding": {...}, "reason": "..."}],
            "expired_ignores": ["CVE-..."],            # відсортовані унікальні id
            "fixes": {"pkg": "версія"},
            "passed": bool}                            # True, якщо blocking порожній

Знахідка нижче порога не потрапляє ні в blocking, ні в ignored. Знахідка без виправлення при
`only_fixable=True` теж ні. Якщо діючий запис ignore покриває знахідку, що інакше блокувала б,
вона йде в `ignored`.

`fixes`: для кожного пакета з blocking-знахідками мінімальна версія, що закриває ВСІ його
знахідки. `FixedVersion` може містити кілька гілок через кому ("1.2.9, 1.3.4"): бери
найменшу, що не нижча за встановлену. Версія для порівняння це кортеж усіх чисел у рядку
(`re.findall(r"\\d+", v)`). Для пакета бери максимум за його знахідками. Якщо жодної придатної
гілки немає, пакет у `fixes` не входить.
"""


def parse_findings(report: dict) -> list[dict]:
    raise NotImplementedError


def triage(report: dict, policy: dict, today) -> dict:
    raise NotImplementedError
