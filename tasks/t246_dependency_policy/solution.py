"""Завдання №246: політика залежностей (lockfile проти знімка індексів).

Перед збіркою CI перевіряє lockfile: чи не підсунули чужий пакет замість внутрішнього
(dependency confusion), чи є хеші, чи це wheels, чи не yanked версія, чи не надто свіжа
(cooldown: більшість шкідливих релізів знаходять і знімають за дні). Мережі немає: індекси
приходять знімком, «зараз» параметром.

Формати даних
    lock:     list[dict], елемент
              {"name": "requests", "version": "2.32.3", "index": "pypi",
               "filename": "requests-2.32.3-py3-none-any.whl",
               "hashes": ["sha256:<64 малих hex>", ...]}
    snapshot: {index_name: {package_name: {version: {"yanked": bool,
               "uploaded": "2026-01-02T00:00:00+00:00",   # ISO 8601 ЗІ зсувом пояса
               "files": {filename: "sha256:<64 hex>"}}}}}
              Імена пакетів у знімку вже нормалізовані (PEP 503).
    policy:   dict, усі ключі необовʼязкові; дефолти СУВОРІ (fail closed):
              "internal_names": [] , "internal_prefixes": [],
              "require_hashes": True, "wheels_only": True,
              "cooldown_days": 7 (0 вимикає), "cooldown_exempt": [] (імена пакетів)
    now:      `datetime` із часовим поясом.

`normalize_name(name) -> str`: нормалізація PEP 503 (уже реалізована).

`check_lock(lock, snapshot, policy, now) -> list[dict]`
    Повертає порушення `{"package", "version", "rule", "reason"}`, де `package` це
    нормалізоване імʼя, відсортовані за `(package, version, rule)`. Порожній список означає
    «можна збирати». `reason` це рядок, що містить імʼя пакета й версію (людині треба
    зрозуміти відмову). Вхідні структури не змінювати. Правила:

    | rule            | коли |
    |-----------------|------|
    | `confusion`     | нормалізоване імʼя є в `internal_names` (теж нормалізованих) або починається з одного з `internal_prefixes` (нормалізованих), а `index` елемента НЕ `"internal"` |
    | `missing-hash`  | `require_hashes` і список `hashes` порожній чи відсутній |
    | `bad-hash`      | будь-який елемент `hashes` не відповідає `sha256:` + рівно 64 малих hex |
    | `hash-mismatch` | `hashes` непорожній, `filename` є у знімку, але хеш файла зі знімка НЕ входить до `hashes` (зайві додаткові хеші дозволені: той самий реліз має кілька wheels) |
    | `sdist`         | `wheels_only` і `filename` (без урахування регістру) не закінчується на `.whl` |
    | `yanked`        | у знімку версія має `yanked: true` |
    | `cooldown`      | `cooldown_days > 0`, пакета немає в `cooldown_exempt` і `now - uploaded < cooldown_days` днів (рівно N днів уже ОК; `uploaded` у майбутньому це порушення) |
    | `not-in-index`  | індексу, пакета, версії чи файла `filename` немає у знімку (тоді правила `hash-mismatch`, `yanked`, `cooldown` для цього елемента не застосовуються) |

    Один елемент може мати кілька порушень. Помилки входу: `now` без часового поясу,
    елемент lock без `name`/`version`/`filename`, `uploaded` без зсуву пояса це `ValueError`.
"""
import re
from datetime import datetime, timedelta  # noqa: F401  (знадобляться)


def normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def check_lock(lock: list[dict], snapshot: dict, policy: dict, now: datetime) -> list[dict]:
    raise NotImplementedError
