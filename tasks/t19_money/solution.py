"""Завдання №19: гроші на Decimal.

Правила для всіх функцій: працюємо з `decimal.Decimal`, ніколи з `float`; результати це
суми з рівно двома знаками після коми (`Decimal("12.30")`, тобто `exponent == -2`);
округлення «школярське» `ROUND_HALF_UP` (0.005 -> 0.01), а не банківське за замовчуванням.

- `parse_money(text) -> Decimal`
    Приймає: необов'язковий знак `+`/`-`, цілу частину (з комами-роздільниками тисяч строго
    групами по 3: `1,234,567`), необов'язкові 1-2 знаки після крапки. Пробіли навколо
    ігноруються. Все інше (`1.234`, `1,23`, `1.2.3`, `abc`, порожнє, `1e3`, `.5`, `5.`,
    `1 000`) це `ValueError`.
- `convert(amount, rate) -> Decimal`
    Множить суму на курс і округлює до копійок: `convert(Decimal("2.675"), Decimal("1"))`
    це `2.68` (float дав би 2.67).
- `add_vat(net, rate_percent) -> tuple[Decimal, Decimal]`
    Повертає `(vat, gross)`. `vat` = `net * rate_percent / 100`, округлений до копійок;
    `gross = net + vat` (сума точна, без повторного округлення).
- `allocate(total, weights) -> list[Decimal]`
    Ділить суму між частинами за вагами (цілі невід'ємні числа) так, щоб СУМА ЧАСТИН
    дорівнювала `total` до копійки (`100.00` на три рівні частини це 33.34, 33.33, 33.33).
    Метод найбільших залишків: кожна частина спершу отримує цілу кількість копійок
    (округлення вниз), решта копійок роздається по одній частинам з найбільшим дробовим
    залишком; при рівних залишках раніше йде частина з меншим індексом.
    `total` < 0, порожні ваги, відʼємна вага або сума ваг 0 це `ValueError`.
    `total` має не більше двох знаків після коми.
"""
from decimal import Decimal


def parse_money(text: str) -> Decimal:
    raise NotImplementedError


def convert(amount: Decimal, rate: Decimal) -> Decimal:
    raise NotImplementedError


def add_vat(net: Decimal, rate_percent: Decimal) -> tuple[Decimal, Decimal]:
    raise NotImplementedError


def allocate(total: Decimal, weights: list[int]) -> list[Decimal]:
    raise NotImplementedError
