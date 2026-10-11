"""Завдання №147: Strategy як функції + реєстр.

Правила знижок це «стратегії». У Python стратегія це просто функція, тож жодних класів-обгорток.
Правило: `rule(total_cents: int, ctx: dict) -> int` повертає розмір знижки в копійках.

`StrategyRegistry`
    register(name) -> декоратор. Реєструє функцію під іменем і повертає її без змін.
        Повторна реєстрація того ж імені: ValueError. Порожнє/не-рядкове ім'я: ValueError.
    get(name) -> функція; невідоме ім'я: UnknownStrategy.
    names() -> відсортований список імен.
    apply(total_cents, names, ctx=None) -> int
        Застосовує правила ПО ЧЕРЗІ до поточної суми (кожне бачить суму після попередніх).
        * усі імена перевіряються ДО виконання будь-якого правила: невідоме ім'я -> UnknownStrategy,
          і жодне правило при цьому не викликається;
        * знижка це int >= 0, інакше ValueError (bool, float, від'ємні не годяться);
        * знижка не може зробити суму від'ємною: більше за поточну суму означає «до нуля»;
        * `total_cents` має бути int >= 0, інакше ValueError;
        * `ctx` за замовчуванням порожній словник; усі правила отримують той самий об'єкт.

Фабрики правил (функції, що повертають правило):
    percent_off(percent)  -> знижка = total * percent // 100 (ціле ділення); percent це int 0..100, інакше ValueError
    fixed_off(cents)      -> знижка = cents; cents це int >= 0, інакше ValueError
    capped(rule, max_cents) -> правило, чия знижка не більша за max_cents
"""
from typing import Callable

Rule = Callable[[int, dict], int]


class UnknownStrategy(KeyError):
    pass


class StrategyRegistry:
    def register(self, name: str):
        raise NotImplementedError

    def get(self, name: str) -> Rule:
        raise NotImplementedError

    def names(self) -> list[str]:
        raise NotImplementedError

    def apply(self, total_cents: int, names: list[str], ctx: dict | None = None) -> int:
        raise NotImplementedError


def percent_off(percent: int) -> Rule:
    raise NotImplementedError


def fixed_off(cents: int) -> Rule:
    raise NotImplementedError


def capped(rule: Rule, max_cents: int) -> Rule:
    raise NotImplementedError
