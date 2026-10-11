"""Завдання №154: Specification (композовані правила).

Правила доступу чи відбору («активний І не заблокований АБО адмін») складають з маленьких іменованих
предикатів, а не з вкладених `if`. Python дозволяє зробити це читабельно через оператори.

`Spec(fn, name)`: обгортка над предикатом `fn(obj) -> bool`.
    * `spec(obj) -> bool` (результат приводиться до bool);
    * `a & b` (І), `a | b` (АБО), `~a` (НЕ) повертають нові Spec; оператори з не-Spec (число, функція)
      це `TypeError` (поверніть NotImplemented);
    * `&` та `|` ЛІНИВІ: `a & b` не викликає `b`, якщо `a` дало False; `a | b` не викликає `b`, якщо `a` дало True;
    * `name`: ім'я. Для складених правил: `(a AND b)`, `(a OR b)`, `NOT a` (імена вкладених підставляються як є,
      дужки є лише в AND/OR);
    * `repr(spec)` це `Spec(<name>)`;
    * `failures(obj) -> list[str]`: ПОЯСНЕННЯ відмови, тобто імена листових правил, через які результат False:
        - лист: `[]`, якщо True, інакше `[name]`;
        - AND: об'єднання failures УСІХ операндів (без ліні: пояснення має бути повним, лише для відмови);
          якщо весь AND True, то `[]`;
        - OR: `[]`, якщо хоч один операнд True, інакше об'єднання failures усіх операндів;
        - NOT x: `[]`, якщо x False (тобто NOT True), інакше `["NOT " + x.name]`.
      Результат `failures(obj) == []` тоді й лише тоді, коли `spec(obj)` True.

`spec(name=None)`: декоратор, що робить зі звичайної функції Spec (ім'я за замовчуванням `fn.__name__`);
    вживається і як `@spec`, і як `@spec("ім'я")`.
`all_of(*specs)`: І всіх (порожній набір завжди True, ім'я "TRUE"); `any_of(*specs)`: АБО всіх
    (порожній набір завжди False, ім'я "FALSE"). Приймають лише Spec, інакше TypeError.
"""
from typing import Callable


class Spec:
    def __init__(self, fn: Callable[[object], bool], name: str):
        raise NotImplementedError

    @property
    def name(self) -> str:
        raise NotImplementedError

    def __call__(self, obj) -> bool:
        raise NotImplementedError

    def __and__(self, other):
        raise NotImplementedError

    def __or__(self, other):
        raise NotImplementedError

    def __invert__(self):
        raise NotImplementedError

    def failures(self, obj) -> list[str]:
        raise NotImplementedError

    def __repr__(self) -> str:
        raise NotImplementedError


def spec(arg=None):
    raise NotImplementedError


def all_of(*specs: Spec) -> Spec:
    raise NotImplementedError


def any_of(*specs: Spec) -> Spec:
    raise NotImplementedError
