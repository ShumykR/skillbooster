"""Завдання №225: Event Sourcing і CQRS.

Банківський рахунок без таблиці «поточний стан»: єдине джерело правди це журнал подій.
Стан рахунку обчислюється згортанням подій, а для читання є окрема проєкція (read model).
Годинників і мережі немає: усе в памʼяті, детерміновано.

Події (`dict`): `{"type": str, "data": dict}`:
    Opened    {"owner": str}
    Deposited {"amount": int}
    Withdrawn {"amount": int}
    Closed    {}
Стан агрегата: `{"owner": str, "balance": int, "status": "open" | "closed"}`.
Команди (`dict`): `{"type": "open", "owner": str}`, `{"type": "deposit", "amount": int}`,
`{"type": "withdraw", "amount": int}`, `{"type": "close"}`.

Дано (не змінюй): `ConcurrencyError`, `DomainError`, `StoredEvent`.

`EventStore` (журнал у памʼяті)
    * `append(stream_id, events, expected_version) -> list[StoredEvent]`
      Дописує події в потік АТОМАРНО. `expected_version` це кількість подій у потоці,
      яку бачив автор (для нового потоку 0, тип `int` >= 0, не `bool`, інакше `ValueError`).
      Якщо реальна кількість інша: `ConcurrencyError` і НІЧОГО не дописано. Кожна подія
      має бути `dict` з рядком `type` і `dict` `data`, інакше `ValueError` до будь-якого запису
      (жодної часткової вставки). Порожній список це no-op: повертає `[]` (версію теж
      перевіряє). `version` події це її номер у потоці (1, 2, ...), `position` це
      наскрізний номер у всьому журналі (1, 2, ... по всіх потоках). Дані копіюються
      (глибоко): зміна словника викликачем потім не змінює журнал.
    * `read_stream(stream_id, from_version=1) -> list[StoredEvent]` події потоку з версією
      >= `from_version` за зростанням (невідомий потік: `[]`).
    * `read_all(after_position=0, limit=None) -> list[StoredEvent]` події всіх потоків з
      `position > after_position` за зростанням позиції, не більше `limit` штук.

`apply(state, event) -> dict`
    ЧИСТА функція згортання: повертає НОВИЙ стан, вхідний `state` не змінює. `Opened`
    приймає `state=None`. Невідомий тип події це `ValueError`.

`decide(state, command) -> list[dict]`
    Бізнес-правила, повертає події (не змінює стан): `open` лише коли `state is None`;
    решта команд лише для існуючого відкритого рахунку; `amount` це `int` > 0 (не `bool`);
    `withdraw` не більше за баланс; `close` лише з нульовим балансом. Порушення це
    `DomainError`. Невідомий тип команди це `ValueError`.

`AccountRepository(store, snapshot_every=0)`
    * `load(stream_id) -> tuple[dict | None, int]` стан і версія (кількість подій). Якщо в
      `self.snapshots[stream_id]` є знімок `{"version": v, "state": ...}`, події читаються
      лише з `from_version=v + 1` (виклик `store.read_stream`).
    * `handle(stream_id, command) -> list[StoredEvent]` load, decide, append з
      `expected_version` = версії, яку прочитано. `ConcurrencyError` не ковтається.
    * знімки: якщо `snapshot_every > 0` і `нова_версія // snapshot_every > стара_версія //
      snapshot_every`, зберегти `self.snapshots[stream_id] = {"version": нова_версія,
      "state": <стан після нових подій>}` (копія, а не посилання на живий стан).

`BalanceProjection(store, fault=None)` проєкція для читання
    * атрибут `checkpoint` (позиція останньої застосованої події, спершу 0);
    * `handle_event(stored_event) -> bool`: ідемпотентно. Подія з `position <= checkpoint`
      це повторна доставка: `False`, нічого не змінюється. `position > checkpoint + 1`
      це пропуск: `ValueError`. Інакше змінює модель і `checkpoint` РАЗОМ, `True`.
      Перед фіксацією (після обчислення змін) викликається `fault(stored_event)`, якщо
      він заданий: якщо хук кидає виняток, модель і `checkpoint` лишаються такими, як були
      до цієї події (імітація падіння між обробкою й commit);
    * `catch_up(limit=None) -> int`: читає `store.read_all(after_position=checkpoint)` і
      передає КОЖНУ подію в `self.handle_event` (так перевизначення в підкласі працює);
      повертає кількість застосованих. Виняток із події зупиняє обробку, попередні
      лишаються застосованими, наступний `catch_up` продовжує з checkpoint;
    * `get(account_id) -> dict | None` копія `{"owner", "balance", "status"}` або `None`;
    * `total_open_balance() -> int` сума балансів відкритих рахунків.

`ReadModel(store, factory=BalanceProjection)` перебудова проєкції без простою
    * `current` це активна проєкція; `get(account_id)` і `catch_up()` делегують їй;
    * `begin_rebuild(factory=None)` створює ТІНЬОВУ проєкцію (з `factory` або тієї самої),
      порожню, `current` не чіпає (повторний виклик відкидає попередню тінь);
    * `rebuild_step(n) -> int` застосовує до тіні не більше `n` подій, повертає кількість
      застосованих (`RuntimeError`, якщо перебудову не розпочато). Поки триває перебудова,
      `get` читає зі СТАРОЇ `current`, а `catch_up()` її й оновлює;
    * `finish_rebuild()` дожене тінь до голови журналу й АТОМАРНО зробить її `current`
      (`RuntimeError`, якщо не розпочато). Після цього тіні немає.
"""
from dataclasses import dataclass


class ConcurrencyError(Exception):
    """Версія потоку змінилась між читанням і записом."""


class DomainError(Exception):
    """Порушення бізнес-правила."""


@dataclass(frozen=True)
class StoredEvent:
    stream_id: str
    version: int
    position: int
    type: str
    data: dict


class EventStore:
    def append(self, stream_id: str, events: list[dict], expected_version: int) -> list[StoredEvent]:
        raise NotImplementedError

    def read_stream(self, stream_id: str, from_version: int = 1) -> list[StoredEvent]:
        raise NotImplementedError

    def read_all(self, after_position: int = 0, limit: int | None = None) -> list[StoredEvent]:
        raise NotImplementedError


def apply(state: dict | None, event: StoredEvent | dict) -> dict:
    raise NotImplementedError


def decide(state: dict | None, command: dict) -> list[dict]:
    raise NotImplementedError


class AccountRepository:
    def __init__(self, store: EventStore, snapshot_every: int = 0):
        raise NotImplementedError

    def load(self, stream_id: str) -> tuple[dict | None, int]:
        raise NotImplementedError

    def handle(self, stream_id: str, command: dict) -> list[StoredEvent]:
        raise NotImplementedError


class BalanceProjection:
    def __init__(self, store: EventStore, fault=None):
        raise NotImplementedError

    def handle_event(self, event: StoredEvent) -> bool:
        raise NotImplementedError

    def catch_up(self, limit: int | None = None) -> int:
        raise NotImplementedError

    def get(self, account_id: str) -> dict | None:
        raise NotImplementedError

    def total_open_balance(self) -> int:
        raise NotImplementedError


class ReadModel:
    def __init__(self, store: EventStore, factory=BalanceProjection):
        raise NotImplementedError

    def get(self, account_id: str) -> dict | None:
        raise NotImplementedError

    def catch_up(self, limit: int | None = None) -> int:
        raise NotImplementedError

    def begin_rebuild(self, factory=None) -> None:
        raise NotImplementedError

    def rebuild_step(self, n: int) -> int:
        raise NotImplementedError

    def finish_rebuild(self) -> None:
        raise NotImplementedError
