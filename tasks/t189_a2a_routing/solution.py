"""Завдання №189: маршрутизація між агентами в стилі A2A (Agent2Agent).

Протокол A2A (Google, 2025; зараз у Linux Foundation) дає агентам спільну мову: кожен
публікує «картку» (`/.well-known/agent-card.json`) з імʼям, адресою, версією, навичками (skills)
і способом автентифікації; клієнт обирає агента за навичками й веде задачу через життєвий цикл
станів. Реалізувати весь протокол не треба: лише валідацію картки, вибір агента, автентифікацію
виклику й автомат станів задачі. Недовірена картка це недовірений вхід: помилки тут це
підміна агента (impersonation) і виклики без автентифікації (CWE-306).

Картка (dict):
    {"name": str, "url": str, "version": "N.N.N", "skills": [{"id": str, "name": str?, "tags": [str]?}],
     "auth": {"schemes": ["bearer" | "apikey", ...]}}

`validate_card(card) -> list[str]`
    Коди проблем у такому порядку (порожній список: картка валідна):
      * не dict: `["not-an-object"]`;
      * `"missing:name"`: `name` відсутнє, не `str` чи порожнє;
      * `"bad-url"`: `url` не `str`; схема не `https` (`http` дозволено ЛИШЕ для хостів `localhost`
        і `127.0.0.1`); немає хоста; в адресі є облікові дані (`user:pass@`);
      * `"bad-version"`: не відповідає `^\\d+\\.\\d+\\.\\d+$` (рядок);
      * `"no-skills"`: `skills` не непорожній список;
      * для кожної навички за індексом `i`: `"skill[i]:not-an-object"`; `"skill[i]:missing-id"`
        (`id` відсутнє, не `str` чи порожнє); `"skill[i]:bad-tags"` (`tags` є, але це не список
        непорожніх рядків). Для не-dict навички інших перевірок немає;
      * `"skill:duplicate-id:<id>"` для кожного повторюваного `id` (по одному разу), за алфавітом;
      * `"auth-missing"`: `auth` не dict або `schemes` не непорожній список;
      * інакше для кожної схеми, що не з `("bearer", "apikey")`, у порядку списку:
        `"auth-scheme:<схема>"` (схеми `"none"` не існує: публічних агентів тут немає).

`select_agent(cards, tags) -> dict`
    `cards` це список карток, `tags` це непорожній список непорожніх рядків (інакше `ValueError`).
    Картка-кандидат: валідна, її `name` унікальне серед ВСІХ переданих карток (дві картки з
    однаковим `name` обидві відхиляються з проблемою `"duplicate-name"`, бо це підміна), і має
    хоч одну навичку, чий набір `tags` містить УСІ потрібні (регістр має значення; один збіг
    лише в межах однієї навички).
    Ранжування кандидатів: більше навичок, що підходять (`matches`), далі вища версія (порівняння
    за числами, `1.10.0` > `1.9.0`), далі `name` за алфавітом.
    Результат: `{"agent": name найкращого | None, "skill": id першої підхожої навички найкращого |
    None, "ranking": [{"agent", "skill", "version", "matches"}, ...] (усі кандидати за ранжуванням),
    "rejected": [{"agent": name | None, "problems": [...]}, ...]}` де `rejected` це картки з
    проблемами в порядку входу (валідні, але без підхожих навичок, у `rejected` НЕ потрапляють).
    Перевірки `validate_card` застосовуються до кожної картки; `"duplicate-name"` додається в кінець
    списку проблем.

`authenticate(card, headers, credentials) -> bool`
    `credentials` це `{"bearer": [токени], "apikey": [ключі]}` (відсутній ключ це порожній список).
    Картка має бути валідною (інакше `False`). Дозволено, якщо виконується ХОЧА Б ОДНА зі схем
    картки: `"bearer"`: заголовок `Authorization` дорівнює `"Bearer <токен>"` (слово `Bearer` без
    урахування регістру, рівно один пробіл), токен є серед `credentials["bearer"]`; `"apikey"`:
    заголовок `X-API-Key` дорівнює одному з `credentials["apikey"]`. Імена заголовків без
    урахування регістру; значення порівнюються за постійний час (`hmac.compare_digest`) з УСІМА
    дійсними значеннями. Без потрібного заголовка, з порожнім значенням, не-рядком чи схемою, якої
    немає в картці: `False` (fail closed). `headers` не dict: `False`.

`Task(task_id, agent, owner)`
    `task_id`, `agent`, `owner` це непорожні різні `str` (`agent != owner`), інакше `ValueError`.
    Стан починається з `"submitted"`. `.state`, `.history` (список `(з, в, actor)`).
    `.transition(new_state, actor)`:
      Дозволені переходи (хто може):
          submitted      -> working (agent), failed (agent), canceled (owner)
          working        -> input-required (agent), completed (agent), failed (agent), canceled (owner)
          input-required -> working (owner), failed (agent), canceled (owner)
      * перехід, якого немає в таблиці (зокрема зі стану `completed`, `failed`, `canceled`, у той
        самий стан чи в невідомий стан): `TransitionError` (підклас `ValueError`);
      * перехід є, але `actor` не має права (`actor` це `agent`, `owner` або чужий): `PermissionError`;
      * у обох випадках стан і історія НЕ змінюються. Успіх додає `(з, в, actor)` в історію.
    `.is_terminal`: `True` у `completed`, `failed`, `canceled`.
"""
import hmac  # noqa: F401  (знадобиться)
import re  # noqa: F401
from urllib.parse import urlsplit  # noqa: F401

SCHEMES = ("bearer", "apikey")


class TransitionError(ValueError):
    pass


def validate_card(card) -> list:
    raise NotImplementedError


def select_agent(cards: list, tags: list) -> dict:
    raise NotImplementedError


def authenticate(card, headers, credentials) -> bool:
    raise NotImplementedError


class Task:
    def __init__(self, task_id: str, agent: str, owner: str):
        raise NotImplementedError

    @property
    def state(self) -> str:
        raise NotImplementedError

    @property
    def history(self) -> list:
        raise NotImplementedError

    @property
    def is_terminal(self) -> bool:
        raise NotImplementedError

    def transition(self, new_state: str, actor: str) -> None:
        raise NotImplementedError
