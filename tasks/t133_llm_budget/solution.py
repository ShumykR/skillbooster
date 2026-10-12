"""Завдання №133: Контроль витрат на LLM: облік токенів на користувача, ліміти, бюджети та fallback на дешевшу модель.

Один циклічний агент чи скрипт може спалити сотні доларів за ніч. Потрібні: точний облік вартості кожного виклику, ліміти (на користувача
за день і місяць, глобальний за місяць) і політика «якщо дорога модель не вміщується в залишок бюджету, використати дешевшу».
Час приходить із clock() (секунди епохи, UTC); день = ціле число діб від епохи, місяць = (рік, місяць) за time.gmtime.

prices: {"model": {"in": ціна за 1 000 000 вхідних токенів у USD, "out": ціна за 1 000 000 вихідних}}

cost(prices, model, usage) -> float
    usage: {"prompt_tokens": n, "completion_tokens": m (необовʼязково, типово 0)}.
    round((n * in + m * out) / 1_000_000, 6). Невідома модель, відсутній prompt_tokens чи від'ємні значення: ValueError.

BudgetManager(prices, limits, clock)
    limits: {"user_daily": USD | None, "user_monthly": USD | None, "global_monthly": USD | None, "warn_at": 0.8}
    (відсутні ключі та None означають «без ліміту»; warn_at типово 0.8).
    .record(user, model, usage) -> float      вартість виклику (cost) додається до обліку на поточний момент; повертає її.
                                              Облік не відхиляє виклики: він лише рахує (відмовляє plan).
    .events -> list[dict]                     {"ts", "user", "model", "cost"} у порядку запису.
    .spent(user, period) -> float             витрати користувача за поточний день ("day") або місяць ("month"), round(.., 6).
    .global_spent() -> float                  витрати всіх користувачів за поточний місяць, round(.., 6).
    .remaining(user) -> float                 мінімум із (user_daily - spent day), (user_monthly - spent month), (global_monthly - global_spent)
                                              по заданих лімітах, не менше 0, round(.., 6); без жодного ліміту float("inf").
    .plan(user, models, prompt_tokens, max_tokens) -> dict
        models: імена моделей від бажаної до найдешевшої. Оцінка вартості моделі = cost(prices, model, {"prompt_tokens": prompt_tokens,
        "completion_tokens": max_tokens}). Береться ПЕРША модель, чия оцінка <= remaining(user).
        {"model": імʼя або None, "reason": "ok" (перша модель) | "fallback" (одна з наступних) | "budget_exhausted" (жодна не вміщується),
         "estimated_cost": оцінка вибраної моделі (для budget_exhausted оцінка найдешевшої за оцінкою з перелічених, 0.0 якщо список порожній),
         "warning": True, якщо хоч для одного заданого ліміту round((spent + estimated_cost) / ліміт, 9) >= warn_at (для budget_exhausted False)}.
        models порожній: ValueError. Токени від'ємні: ValueError.
"""

import time  # noqa: F401


def cost(prices: dict, model: str, usage: dict) -> float:
    raise NotImplementedError


class BudgetManager:
    def __init__(self, prices: dict, limits: dict, clock) -> None:
        raise NotImplementedError

    @property
    def events(self) -> list[dict]:
        raise NotImplementedError

    def record(self, user: str, model: str, usage: dict) -> float:
        raise NotImplementedError

    def spent(self, user: str, period: str) -> float:
        raise NotImplementedError

    def global_spent(self) -> float:
        raise NotImplementedError

    def remaining(self, user: str) -> float:
        raise NotImplementedError

    def plan(self, user: str, models: list[str], prompt_tokens: int, max_tokens: int) -> dict:
        raise NotImplementedError
