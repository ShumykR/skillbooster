"""Завдання №168: ціна й обмеження рахує сервер, а не форма.

Наївний чекаут бере з запиту `price_cents`, `discount_pct` і `total_cents`, бо «фронтенд же
перевірив». Достатньо відкрити DevTools, виставити ціну в 1 копійку, і замовлення оформлено.
Правило: усе, що впливає на гроші й права, береться на сервері; значення з клієнта лише
порівнюються з серверними, щоб показати користувачу «ціна змінилась».

`price_order(catalog, promos, payload, today) -> dict`
    - `catalog`: {sku: {"price_cents": int, "max_qty": int, "active": bool}};
    - `promos`: {код: {"percent": int, "min_total_cents": int, "valid_until": "YYYY-MM-DD"}};
    - `payload`: {"items": [{"sku": ..., "qty": ..., <будь-які інші поля клієнта>}],
                  "promo_code": необовʼязковий рядок, "claimed_total_cents": необовʼязкове int};
    - `today`: `datetime.date`.

Усі інші поля клієнта (`price_cents`, `discount_pct`, `total_cents`, `is_admin`, ...) ІГНОРУЮТЬСЯ.

Порушення це `OrderRejected` з кодом у `.code`:
    "empty"         `items` відсутній, не список, порожній або довший за 50 рядків;
    "unknown_sku"   sku немає в каталозі (або sku не рядок);
    "inactive_sku"  sku є, але `active` не True;
    "bad_qty"       `qty` не `int` (`bool` теж не підходить) або менше 1;
    "qty_limit"     сумарна кількість sku більша за його `max_qty`: рядки з однаковим sku спершу
                    обʼєднуються (інакше ліміт обходять двома рядками);
    "bad_promo"     `promo_code` не рядок або його немає в `promos`; код нормалізується
                    `strip().upper()`, ключі `promos` записані у верхньому регістрі;
    "promo_expired" `today > valid_until`;
    "promo_min_total" підсумок до знижки менший за `min_total_cents`.
Перевірки йдуть у порядку: "empty", потім по рядках `items` у порядку надходження
("unknown_sku", "inactive_sku", "bad_qty"), потім "qty_limit", потім промокод
("bad_promo", "promo_expired", "promo_min_total").

Результат:
    {"lines": [{"sku", "qty", "unit_cents", "line_cents"}, ...],   # за sku, рядки обʼєднані
     "subtotal_cents": ..., "discount_cents": subtotal * percent // 100,
     "total_cents": subtotal - discount,
     "price_changed": bool}   # True, якщо `claimed_total_cents` задано і не дорівнює total_cents
"""


class OrderRejected(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def price_order(catalog: dict, promos: dict, payload: dict, today) -> dict:
    raise NotImplementedError
