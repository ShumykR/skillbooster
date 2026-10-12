"""Завдання №74: Матриця версій, кеш залежностей, паралельні джоби: швидкий CI.

Два інструменти для аналізу workflow GitHub Actions (YAML вже розбирається `yaml.safe_load`; зверни увагу, що ключ
`on` YAML читає як `True`: тут він не потрібен).

audit_ci(text) -> list[str]    відсортований список унікальних кодів проблем. Job = елемент `jobs`.
    * CI001  job має крок `actions/setup-python`, `actions/setup-node`, `actions/setup-java` або `actions/setup-go` (будь-яка
             версія після `@`) БЕЗ ключа `with.cache`, і в тому самому job немає кроку `actions/cache`: залежності
             завантажуються з нуля щоразу;
    * CI002  job запускає тести (в `run` кроку є `pytest` або `npm test`), але не має `strategy.matrix` з ключем,
             що закінчується на `-version` (`python-version`, `node-version`) і має щонайменше 2 значення;
    * CI003  job має `strategy.matrix`, а `strategy.fail-fast` не дорівнює `false` явно (за замовчуванням `true`: перша
             помилка скасовує решту комбінацій і ховає, які саме версії зламались);
    * CI004  на верхньому рівні немає `concurrency` з `cancel-in-progress: true` (старі запуски того ж PR не скасовуються);
    * CI005  «перевірочний» job (id містить `lint`, `test`, `typecheck`, `mypy` або `ruff`, без урахування регістру) має
             `needs` на ІНШИЙ перевірочний job (штучна серіалізація): ці перевірки незалежні й мають іти паралельно;
             `needs` на job збірки/інші не рахується;
    * CI006  у job немає `timeout-minutes` (типово 360 хвилин: завислий job палить гроші шість годин);
    * CI007  у перевірочному job (за тими самими id) крок `actions/checkout` має `with.fetch-depth: 0`
             (повна історія git потрібна рідко: це секунди чи хвилини на кожен запуск).

critical_path(text, minutes) -> tuple[float, list[str]]
    Час пайплайна визначає найдовший ланцюжок `needs`: джоби без залежностей між собою йдуть паралельно, а матриця job-а
    теж паралельна (вона не множить час). `minutes`: {id job: хвилини}; відсутній id це 1.0. Повертає (сумарний час
    найдовшого ланцюжка, список id від початку до кінця). Якщо найдовших ланцюжків кілька, вибирається той, чий
    список id лексикографічно менший. `needs` це рядок або список. Невідомий id в `needs` або цикл -> ValueError.
    Порожній `jobs` -> (0.0, []).
"""
import yaml  # noqa: F401


def audit_ci(text: str) -> list[str]:
    raise NotImplementedError


def critical_path(text: str, minutes: dict[str, float]) -> tuple[float, list[str]]:
    raise NotImplementedError
