"""Завдання №20: нормалізація до 3NF через функціональні залежності (FD).

Відношення це множина імен атрибутів (`{"A", "B", "C"}`). Функціональна залежність це пара
`(lhs, rhs)` двох множин атрибутів: `({"A"}, {"B", "C"})` означає «A визначає B і C».
Список FD передається як `fds: list[tuple[set, set]]`. Вхідні дані не змінюй.

Функції:
- `closure(attrs, fds) -> frozenset`
    Замикання множини атрибутів: усе, що вона визначає прямо чи транзитивно.
- `candidate_keys(relation, fds) -> set[frozenset]`
    Усі кандидатні ключі: МІНІМАЛЬНІ множини, замикання яких дорівнює всьому відношенню.
- `is_3nf(relation, fds) -> bool`
    Відношення в 3NF, якщо для кожної нетривіальної FD `X -> A` (A не входить у X) виконується
    одне з двох: X це суперключ, або A це «простий» атрибут (входить у якийсь кандидатний
    ключ). Тривіальні частини FD (атрибути rhs, що вже є в lhs) ігноруй.
- `minimal_cover(fds) -> list[tuple[frozenset, frozenset]]`
    Мінімальне покриття, еквівалентне вхідним FD: (1) кожна права частина це один атрибут;
    (2) у лівих частинах немає зайвих атрибутів; (3) немає FD, що випливає з решти.
    Покриття не єдине; тести перевіряють властивості, а не конкретний список.
- `synthesize_3nf(relation, fds) -> set[frozenset]`
    Алгоритм синтезу Бернштейна: схема на кожну групу FD мінімального покриття з однаковою
    лівою частиною (lhs ∪ усі rhs групи); якщо жодна схема не містить кандидатного ключа,
    додай схему з одним (найменшим за відсортованим списком імен) ключем; викинь схеми, що є
    власною підмножиною іншої. Результат це множина схем-frozenset.
"""


def closure(attrs: set, fds: list[tuple[set, set]]) -> frozenset:
    raise NotImplementedError


def candidate_keys(relation: set, fds: list[tuple[set, set]]) -> set[frozenset]:
    raise NotImplementedError


def is_3nf(relation: set, fds: list[tuple[set, set]]) -> bool:
    raise NotImplementedError


def minimal_cover(fds: list[tuple[set, set]]) -> list[tuple[frozenset, frozenset]]:
    raise NotImplementedError


def synthesize_3nf(relation: set, fds: list[tuple[set, set]]) -> set[frozenset]:
    raise NotImplementedError
