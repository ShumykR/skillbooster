"""Завдання №183: harness «evaluator-optimizer».

Агент (мок-LLM) пропонує патч, ВЕРИФІКАТОР (тести, не модель) його оцінює, агент виправляє.
Модель не вирішує, чи «вже добре»: рішення приймає код harness за результатом тестів.

Контракти (звичайні функції, нічого не виконується):

    propose(request: dict) -> dict
        request = {"task": str, "attempt": int,           # attempt з 1
                   "base_patch": str | None,              # НАЙКРАЩИЙ прийнятий патч (або None)
                   "feedback": dict | None}               # результат верифікації ОСТАННЬОЇ спроби
        повертає {"patch": str, "cost": float}            # cost >= 0, відсутній cost це 0.0
    verify(patch: str) -> dict
        {"passed": int, "failed": int, "total": int, "errors": [str, ...]}

`run_harness(task, propose, verify, *, max_iters=5, max_cost=1.0) -> dict`

Цикл (кожна спроба це одна ітерація, нумерація з 1):
1. Перед ітерацією: якщо виконано `max_iters` ітерацій, зупинка зі статусом `"max_iters"`;
   інакше якщо накопичена вартість `>= max_cost`, зупинка `"budget"` (вартість сума `cost` усіх
   відповідей `propose`; відповідь, що перетнула ліміт, ще верифікується, а наступної не буде).
2. Виклик `propose`. Виняток з `propose` це запис `reason="propose_error"` (ітерація
   витрачена, вартість 0), цикл продовжується. Патч, що не є непорожнім рядком, це
   `reason="bad_proposal"` (не верифікується, вартість рахується). Відʼємний `cost` або
   не число це `ValueError` (помилка агента-автора harness, а не моделі).
3. Патч, ТОЧНО рівний будь-якому раніше запропонованому, не верифікується повторно:
   запис `reason="duplicate"`. Дві `duplicate` ПІДРЯД це зупинка зі статусом `"stalled"`.
4. `verify(patch)`. Виняток з `verify` це запис `reason="verify_error"`, патч НЕ прийнято
   (fail closed). Результат «успіх» це `failed == 0` І `total > 0` (нуль тестів не є
   успіхом: `reason="no_tests"`, патч не прийнято, але `feedback` йому все одно передається).
5. Рішення про прийняття (порівнюємо `failed` з найкращим прийнятим):
   * немає найкращого: патч стає найкращим, `reason="baseline"` (навіть якщо є падіння);
   * `failed` менше: прийнято, `reason="improved"`;
   * `failed` більше: ВІДКАТ, патч відкинуто, `reason="regression"`, наступна спроба
     отримує `base_patch` = колишній найкращий (регресія не стає базою);
   * `failed` порівну: не прийнято, `reason="no_improvement"`.
   Успіх (п.4) завжди приймається, `reason="solved"`, і цикл зупиняється зі статусом
   `"success"`, наступний `propose` не викликається.
6. `feedback` для наступного `propose` це результат `verify` ОСТАННЬОЇ верифікованої спроби
   (навіть відкинутої), а якщо остання спроба не верифікувалась, то попередній `feedback`.

Результат: `{"status": "success"|"max_iters"|"budget"|"stalled"|"no_valid_patch",
"patch": str | None, "iterations": int, "cost": float, "trajectory": list[dict]}`.
`patch` це найкращий прийнятий (`None`, якщо жодного не було; тоді статус для будь-якої
зупинки НЕ успіху `"no_valid_patch"` замість `"max_iters"`/`"budget"`/`"stalled"`).

`trajectory` журнал для відлагодження, по запису на ітерацію:
`{"iter": int, "patch": str | None, "cost": float, "passed": int | None, "failed": int | None,
"total": int | None, "accepted": bool, "reason": str}` (`passed/failed/total` це `None`, якщо
верифікації не було). Повертається КОПІЯ: зміна результату не впливає на harness, а
`request`, переданий в `propose`, не мутується пізніше.
"""


def run_harness(task: str, propose, verify, *, max_iters: int = 5, max_cost: float = 1.0) -> dict:
    raise NotImplementedError
