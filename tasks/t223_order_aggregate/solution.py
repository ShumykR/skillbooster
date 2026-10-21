"""Завдання №223: агрегат «Замовлення» з інваріантами.

Aggregate (DDD) це межа узгодженості: усі зміни проходять через корінь (`Order`), корінь
сам стежить за інваріантами, зовні видно лише незмінні значення, а репозиторій зберігає й
повертає агрегат ЦІЛКОМ. Замість побічних ефектів (листи, шина подій) корінь накопичує
доменні події, які хтось інший забере й опублікує.

Дані (готові, не змінюй):
    OrderLine(sku, qty, unit_price_cents)   frozen dataclass
    Події (frozen dataclass): OrderPlaced(order_id, customer_id, total_cents),
        OrderPaid(order_id, total_cents), OrderShipped(order_id),
        OrderCancelled(order_id, reason, previous_status)
    Винятки: DomainError (порушення інваріанта чи недопустимий перехід),
        ConcurrencyError (конфлікт версій).

`Order(order_id, customer_id, max_total_cents=100_000)`
    `order_id` і `customer_id`: непорожні `str`, `max_total_cents`: `int` > 0 (не `bool`),
    інакше `ValueError`. Початковий статус `"draft"`, версія `0`, рядків немає.
    Тільки читання (присвоєння дає `AttributeError`): `id`, `customer_id`, `status`,
    `version`, `max_total_cents`, `lines` (КОРТЕЖ `OrderLine` у порядку додавання),
    `total_cents` (сума `qty * unit_price_cents`).

Методи зміни (поки статус `draft`, інакше `DomainError`; помилка не змінює жодних даних і не
створює подій):
    `add_line(sku, qty, unit_price_cents)`: `sku` непорожній `str`, `qty` це `int` >= 1,
        `unit_price_cents` це `int` >= 1 (не `bool`), інакше `ValueError`. Той самий `sku`
        з тією самою ціною збільшує кількість наявного рядка (позиція в `lines` лишається);
        той самий `sku` з іншою ціною це `DomainError`. Якщо новий `total_cents` перевищив би
        `max_total_cents`, це `DomainError`.
    `remove_line(sku)`: прибирає рядок; невідомий `sku` це `DomainError`.

Переходи статусу (інакше `DomainError`):
    `place()`: draft -> placed, потрібен хоча б один рядок; подія `OrderPlaced`.
    `pay()`: placed -> paid; подія `OrderPaid`.
    `ship()`: paid -> shipped; подія `OrderShipped`.
    `cancel(reason)`: draft/placed/paid -> cancelled; `reason` непорожній `str` (інакше
        `ValueError`); подія `OrderCancelled(previous_status=...)`. З shipped і cancelled не можна.
`pull_events() -> list`: повертає накопичені події в порядку виникнення й очищує їх.

`OrderRepository()` (сховище в памʼяті, усередині будь-який словник)
    `save(order)`: оптимістичне блокування. Нове замовлення (версія 0) зберігається, лише якщо
        такого `id` ще немає. Завантажене замовлення зберігається, лише якщо збережена версія
        збігається з `order.version`; інакше `ConcurrencyError` і збережений стан НЕ змінюється.
        Успіх збільшує версію на 1 (і в сховищі, і в `order.version`). Зберігається повний
        знімок (клієнт, ліміт, статус, рядки). Подій `save` не чіпає.
    `get(order_id) -> Order`: новий обʼєкт зі збереженим станом і версією, БЕЗ накопичених подій.
        Невідомий id це `KeyError`. Зміни повернутого обʼєкта чи обʼєкта, який ти зберіг, не
        повинні просочуватися в сховище без `save`.
"""
from dataclasses import dataclass


class DomainError(Exception):
    pass


class ConcurrencyError(Exception):
    pass


@dataclass(frozen=True)
class OrderLine:
    sku: str
    qty: int
    unit_price_cents: int


@dataclass(frozen=True)
class OrderPlaced:
    order_id: str
    customer_id: str
    total_cents: int


@dataclass(frozen=True)
class OrderPaid:
    order_id: str
    total_cents: int


@dataclass(frozen=True)
class OrderShipped:
    order_id: str


@dataclass(frozen=True)
class OrderCancelled:
    order_id: str
    reason: str
    previous_status: str


class Order:
    def __init__(self, order_id: str, customer_id: str, max_total_cents: int = 100_000):
        raise NotImplementedError

    @property
    def id(self) -> str:
        raise NotImplementedError

    @property
    def customer_id(self) -> str:
        raise NotImplementedError

    @property
    def status(self) -> str:
        raise NotImplementedError

    @property
    def version(self) -> int:
        raise NotImplementedError

    @property
    def max_total_cents(self) -> int:
        raise NotImplementedError

    @property
    def lines(self) -> tuple:
        raise NotImplementedError

    @property
    def total_cents(self) -> int:
        raise NotImplementedError

    def add_line(self, sku: str, qty: int, unit_price_cents: int) -> None:
        raise NotImplementedError

    def remove_line(self, sku: str) -> None:
        raise NotImplementedError

    def place(self) -> None:
        raise NotImplementedError

    def pay(self) -> None:
        raise NotImplementedError

    def ship(self) -> None:
        raise NotImplementedError

    def cancel(self, reason: str) -> None:
        raise NotImplementedError

    def pull_events(self) -> list:
        raise NotImplementedError


class OrderRepository:
    def __init__(self):
        raise NotImplementedError

    def save(self, order: Order) -> None:
        raise NotImplementedError

    def get(self, order_id: str) -> Order:
        raise NotImplementedError
