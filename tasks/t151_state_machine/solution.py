"""Завдання №151: скінченний автомат (State).

Життєвий цикл (замовлення, платіж, документ) це таблиця переходів, а не купа `if status == ...`.

`transitions: dict[(state, event), new_state]`, стани й події це рядки.

`analyze(transitions, initial) -> {"unreachable": set, "terminal": set}`
    states = усі стани, що згадані в таблиці (і як джерело, і як ціль) плюс `initial`.
    * unreachable: стани, до яких не можна дійти з `initial`;
    * terminal: досяжні стани, з яких НЕ виходить жоден перехід.
    Порожній `initial` або не-рядок: ValueError.

`StateMachine(transitions, initial, *, guards=None, on_transition=None)`
    guards: dict[(state, event), callable(ctx) -> bool]; якщо охоронець є і повертає не істину, перехід заборонено.
    on_transition: callable(old, event, new, ctx), викликається ПІСЛЯ зміни стану й запису в історію.
    * `state`: поточний стан;
    * `history`: список кортежів `(old, event, new)` виконаних переходів (копія: зовнішня зміна не псує автомат);
    * `available(ctx=None) -> list[str]`: відсортовані події, дозволені зараз (з урахуванням охоронців);
    * `can(event, ctx=None) -> bool`;
    * `fire(event, ctx=None) -> str`: виконує перехід і повертає новий стан.
        Немає переходу зі стану для події: `InvalidTransition`; охоронець заборонив: `GuardRejected`
        (обидва підклас `TransitionError`). Стан і історія при відмові НЕ змінюються;
    * `ctx` за замовчуванням `{}`; охоронці та хук отримують той самий об'єкт;
    * у кінцевому стані (з нього немає переходів): `available() == []`, `can(...)` це False, `fire` дає InvalidTransition;
    * `initial` має бути стартовим станом таблиці (згаданим у ній), інакше ValueError при створенні;
    * таблиця копіюється при створенні: зміна оригінального словника потім не впливає на автомат.
"""
from typing import Callable


class TransitionError(Exception):
    pass


class InvalidTransition(TransitionError):
    pass


class GuardRejected(TransitionError):
    pass


def analyze(transitions: dict[tuple[str, str], str], initial: str) -> dict[str, set[str]]:
    raise NotImplementedError


class StateMachine:
    def __init__(self, transitions, initial, *, guards=None, on_transition: Callable | None = None):
        raise NotImplementedError

    @property
    def state(self) -> str:
        raise NotImplementedError

    @property
    def history(self) -> list[tuple[str, str, str]]:
        raise NotImplementedError

    def available(self, ctx: dict | None = None) -> list[str]:
        raise NotImplementedError

    def can(self, event: str, ctx: dict | None = None) -> bool:
        raise NotImplementedError

    def fire(self, event: str, ctx: dict | None = None) -> str:
        raise NotImplementedError
