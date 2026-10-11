"""Завдання №156: «Parse, don't validate» (value objects).

Замість рядка `email: str`, який хтось колись мав перевірити, робимо тип `Email`, який НЕ МОЖНА створити
невалідним. Усе, що вже є `Email`, безпечно: повторних перевірок немає.

Всі об'єкти незмінні (`frozen=True`), порівнюються й хешуються за значенням.

`Email(value)`
    * не str: TypeError; порушення правил: ValueError;
    * без обрізання пробілів: будь-який пробіл/керівний символ (зокрема `\\n`, `\\x00`) де завгодно це ValueError;
    * рівно один `@`; весь адрес 3..254 символи; лише ASCII;
    * local-частина 1..64 символи з `A-Za-z0-9._%+-`, без крапки на початку/в кінці і без `..`;
    * домен: щонайменше 2 мітки через `.`, кожна 1..63 символи з `A-Za-z0-9-`, не починається й не закінчується `-`;
      остання мітка (TLD) лише літери, 2+;
    * нормалізація: домен приводиться до нижнього регістру, local-частина лишається як є.
`Quantity(value)`: ціле 1..1000. Не int (включно з bool і float, навіть 5.0): TypeError; поза діапазоном: ValueError.
    Має `int(q)`.
`Sku(value)`: рядок, 3..20 символів `A-Z0-9-`, перший символ не `-`. Не str: TypeError; інакше ValueError.
    Увага: `re` з `$` приймає завершальний `\\n`.

`Line(sku: Sku, quantity: Quantity, unit_price_cents: int)`: незмінний; `unit_price_cents` це int 1..10**9
    (не bool); властивість `total_cents = quantity * unit_price_cents`.
`Order(email: Email, lines: tuple[Line, ...])`: незмінний; `total_cents` сума по рядках.

`parse_order(payload) -> Order`: перетворює «брудні» дані (JSON з запиту) у Order або піднімає
`ValidationError` з `errors: dict[str, str]`, де ключ це шлях до поля, а значення непорожнє повідомлення.
    Формат payload: {"email": str, "lines": [{"sku": str, "qty": int, "price_cents": int}, ...]}
    * збираються ВСІ помилки, а не лише перша;
    * payload не dict: {"": ...}; бракує поля: "required" на шляху поля; зайве поле (ні `email`, ні `lines`, або
      ні `sku`/`qty`/`price_cents` у рядку): помилка на шляху цього поля (mass assignment: так лишається тільки
      те, що ми чекаємо);
    * шляхи: "email", "lines", "lines[1].qty", "lines[0].sku", "lines[2].price_cents", "lines[3]" (рядок не dict);
    * "lines" має бути list довжини 1..50, інакше помилка на "lines";
    * однакові sku в різних рядках: помилка "lines[i].sku" на другому й подальших входженнях;
    * якщо всі рядки правильні, але сума замовлення > 10**12 копійок: помилка на "lines".
"""
from dataclasses import dataclass


class ValidationError(ValueError):
    def __init__(self, errors: dict[str, str]):
        super().__init__(errors)
        self.errors = errors


@dataclass(frozen=True)
class Email:
    value: str

    def __post_init__(self):
        raise NotImplementedError


@dataclass(frozen=True)
class Quantity:
    value: int

    def __post_init__(self):
        raise NotImplementedError

    def __int__(self) -> int:
        return self.value


@dataclass(frozen=True)
class Sku:
    value: str

    def __post_init__(self):
        raise NotImplementedError


@dataclass(frozen=True)
class Line:
    sku: Sku
    quantity: Quantity
    unit_price_cents: int

    @property
    def total_cents(self) -> int:
        raise NotImplementedError


@dataclass(frozen=True)
class Order:
    email: Email
    lines: tuple

    @property
    def total_cents(self) -> int:
        raise NotImplementedError


def parse_order(payload) -> Order:
    raise NotImplementedError
