"""Завдання №176: реєстр промптів.

Промпт у production це код: його версіонують, перевіряють змінні, розкочують на частину
користувачів і відкочують. Реалізуй `PromptRegistry`. Мережі й LLM немає, годинник передається
параметром `clock` (функція без аргументів, повертає число).

Імена промптів: `[a-z0-9_.-]+` (інакше `ValueError`). Версії це цілі 1, 2, 3, ... для кожного
імені окремо. Версії НЕЗМІННІ: нова редакція це нова версія.

Шаблон: текст із плейсхолдерами `{{var}}`, де `var` відповідає `[a-z_][a-z0-9_]*` (без пробілів
усередині). Усе інше з `{{` чи `}}` (наприклад `{{ x }}`, `{{1}}`, незакрита `{{`, одинокий
`}}`) це `ValueError` при `register`. Одинарні `{` і `}` це звичайні символи (JSON у промпті
не ламається). НЕ використовуй `str.format` (CWE-1336): підстановка має бути за цим синтаксисом.

`register(name, template) -> int`
    Додає версію й робить її активною. Якщо `template` дослівно збігається з ОСТАННЬОЮ
    версією цього імені, нову версію не створює і повертає її номер (ідемпотентність,
    активність не змінюється).
`get(name, version=None) -> str`
    Текст шаблону; `None` це активна версія. Невідоме імʼя чи версія: `LookupError`.
`variables(name, version=None) -> list[str]`
    Відсортований список унікальних змінних шаблону.
`activate(name, version)`
    Робить версію активною (запамʼятовує попередню для відкату). Якщо вона вже активна, нічого
    не робить. Невідома версія: `LookupError`.
`rollback(name) -> int`
    Повертає активною ПОПЕРЕДНЮ активну версію (як стек: два відкати поспіль ідуть далі
    вглиб) і повертає її номер. Якщо повертатись нікуди: `ValueError`.
`set_experiment(name, weights, salt="")`
    A/B-розподіл: `weights` це `{version: int_weight}`; версії існують, ваги це `int` (не `bool`) >= 0, сума
    > 0, інакше `ValueError`/`LookupError`. `clear_experiment(name)` вимикає.
`assign(name, user_id) -> int`
    Версія для користувача. Без експерименту це активна версія. З експериментом:
    `bucket = int(sha256(f"{name}:{salt}:{user_id}".encode()).hexdigest()[:8], 16) % total`,
    де `total` це сума ваг; версії обходяться за ЗРОСТАННЯМ номера, і береться перша, для якої
    `bucket < накопичена сума ваг`. Той самий користувач завжди отримує ту саму версію.
`render(name, variables, *, version=None, user_id=None) -> Rendered`
    `Rendered` це `namedtuple("Rendered", "text version source")`. Яку версію брати:
    явний `version` (source `"explicit"`), інакше за експериментом, якщо він є і задано
    `user_id` (source `"experiment"`), інакше активну (source `"active"`).
    `variables` має містити РІВНО змінні шаблону: відсутня змінна це `MissingVariable`
    (підклас `ValueError`), зайва це `ValueError`. Значення підставляються як `str(value)`
    за ОДИН прохід: якщо значення саме містить `{{x}}`, воно лишається літерально.
    Кожен виклик додає запис у `registry.journal`:
    `{"name", "version", "user_id", "source", "ts": clock()}`.
`history(name) -> list[dict]`
    Події в порядку виникнення: `{"event": "register"|"activate"|"rollback"|"experiment"|
    "experiment-clear", "version": ..., "ts": clock()}` (для експерименту `version` це `None`).
"""
from collections import namedtuple

Rendered = namedtuple("Rendered", "text version source")


class MissingVariable(ValueError):
    pass


class PromptRegistry:
    def __init__(self, clock=lambda: 0.0):
        self.clock = clock
        self.journal: list[dict] = []

    def register(self, name: str, template: str) -> int:
        raise NotImplementedError

    def get(self, name: str, version: int | None = None) -> str:
        raise NotImplementedError

    def variables(self, name: str, version: int | None = None) -> list[str]:
        raise NotImplementedError

    def activate(self, name: str, version: int) -> None:
        raise NotImplementedError

    def rollback(self, name: str) -> int:
        raise NotImplementedError

    def set_experiment(self, name: str, weights: dict, salt: str = "") -> None:
        raise NotImplementedError

    def clear_experiment(self, name: str) -> None:
        raise NotImplementedError

    def assign(self, name: str, user_id) -> int:
        raise NotImplementedError

    def render(self, name: str, variables: dict, *, version: int | None = None, user_id=None) -> Rendered:
        raise NotImplementedError

    def history(self, name: str) -> list[dict]:
        raise NotImplementedError
