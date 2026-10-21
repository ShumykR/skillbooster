"""Завдання №188: multi-agent оркестратор (orchestrator-workers).

Один «менеджер» (orchestrator) просить LLM розбити задачу на підзадачі, воркери-спеціалісти
виконують їх кожен у СВОЄМУ контексті й з СВОЇМ бюджетом, оркестратор зливає результати.
Усе працює на мок-LLM: `llm(messages) -> {"content": str, "usage": {"prompt_tokens": int,
"completion_tokens": int}}`. Мережі й справжніх моделей немає. Вартість викликів це
`prompt_tokens + completion_tokens`.

Ролі воркерів: `roles = {"researcher": {"system": "...", "budget": 400}, ...}`. Поле
`budget` (токенів на ОДИН виклик воркера) необовʼязкове: без нього обмеження немає.

`run(task, llm, roles, *, total_budget, max_subtasks=6, max_parallel=3, max_handoffs=2) -> dict`

1. План. Виклик `llm([system=PLANNER_SYSTEM, user])`; текст користувача містить `task`, імена ролей
   (через кому, відсортовані) і `max_subtasks`. Відповідь це JSON
   `{"subtasks": [{"id": "a", "role": "researcher", "goal": "...", "depends_on": ["x"]}]}`
   (`depends_on` необовʼязкове). План некоректний, якщо: не JSON-обʼєкт; `subtasks` не
   непорожній список; підзадач більше за `max_subtasks`; `id` не непорожній рядок чи дублікат;
   `role` не з `roles`; `goal` не непорожній рядок; залежність на невідомий id, на себе чи цикл.
   Тоді результат `status="failed"`, `error="invalid-plan: <будь-яка причина>"`, воркери не
   викликаються. Виняток із `llm` у плануванні: `error="plan-llm-error"`. Токени плану
   зараховуються завжди.
2. Воркери. Підзадачі виконуються ХВИЛЯМИ: хвиля це до `max_parallel` підзадач, готових до
   запуску (усі залежності `done`), у порядку плану. Воркери однієї хвилі бачать лише результати
   попередніх хвиль (не сусідів по хвилі). Підзадача, чия залежність не `done`, має статус
   `skipped`, `error="dependency-failed"` і НЕ викликає LLM (у хвилі не зʼявляється).
   Контекст воркера ізольований: `[{"role": "system", "content": roles[role]["system"]},
   {"role": "user", "content": "Goal: <goal>" + (якщо є залежності: "\\n\\nInputs:\\n" і рядки
   "[<dep_id>] <output>" через \\n)}]`. Початкова `task`, промпт планувальника й виходи
   недекларованих залежностей у контекст воркера НЕ потрапляють.
3. Handoff. Якщо відповідь воркера починається з `HANDOFF ` і далі JSON
   `{"to": "<role>", "context": "<текст>"}`, підзадачу продовжує воркер `to` у СВОЇЙ системі:
   user-повідомлення `"Goal: <goal>\\n\\nHandoff from <попередня роль>: <context>"` (+ блок
   `Inputs`, як вище). Історія й system-промпт попереднього воркера не передаються. Некоректний
   JSON, невідома роль, повернення до ролі, що вже була в ланцюжку (включно з самою собою), або
   більше `max_handoffs` передач: підзадача `failed`, `error="bad-handoff"`.
4. Бюджет. Перед КОЖНИМ викликом воркера (включно з handoff): якщо витрачено `>= total_budget`
   токенів, виклику немає: підзадача без жодного виклику `skipped`, з уже зробленими викликами
   `failed`, `error="total-budget-exhausted"`. Якщо токенів одного виклику більше за
   `roles[role]["budget"]` (строго), підзадача `failed`, `error="worker-budget-exceeded"`, вихід
   відкидається, але токени зараховані. Виняток із `llm` у воркері: `failed`,
   `error="llm-error"`.
5. Злиття. Якщо жодна підзадача не `done`: LLM не викликається, `status="failed"`,
   `error="no-results"`. Якщо витрачено `>= total_budget`: `status="failed"`,
   `error="budget-exhausted-before-merge"`, `answer=""`. Інакше виклик
   `llm([system=MERGER_SYSTEM, user])`, де user: `"Task: <task>\\n\\nResults:"` і по рядку на
   підзадачу в порядку плану: `"[<id>] (<role>) <output>"` або `"[<id>] FAILED: <error>"`.
   `answer` це `content`. Виняток: `status="failed"`, `error="merge-llm-error"`.
   `status`: `ok`, якщо усі підзадачі `done`; `partial`, якщо злиття відбулось, але не всі.

Результат:
    {"status": "ok"|"partial"|"failed", "answer": str, "error": str | None,
     "subtasks": {id: {"status": "done"|"failed"|"skipped", "role": <планова роль>,
                       "chain": [ролі, що виконували, по порядку], "output": str | None,
                       "tokens": int, "error": str | None}},
     "waves": [[id, ...], ...],
     "tokens": {"total": int, "orchestrator": int, "by_role": {role: int}}}
`tokens.orchestrator` це план + злиття, `by_role` це виклики воркерів за роллю, що відповідала.
Некоректні аргументи (`total_budget`, `max_subtasks`, `max_parallel` < 1; `max_handoffs` < 0)
це `ValueError`. Вхідний `roles` не змінюється.

`run_single(task, llm) -> {"answer": str, "tokens": int}`: один виклик
`llm([system=SINGLE_SYSTEM, user=task])`.

`cost_report(multi, single) -> dict` (`multi` це результат `run`, `single` це результат
`run_single`): `{"multi_tokens", "single_tokens", "overhead", "cheaper", "orchestrator_share"}`;
`overhead = round(multi_tokens / single_tokens, 2)`; `cheaper` це `"single"`, `"multi"` або
`"equal"`; `orchestrator_share = round(orchestrator / total, 2)` (0.0 при нульовій вартості).
`single_tokens == 0` це `ValueError`.
"""

PLANNER_SYSTEM = "You are the orchestrator. Split the task into subtasks and answer with JSON only."
MERGER_SYSTEM = "You are the orchestrator. Merge the workers' results into one final answer."
SINGLE_SYSTEM = "You are a single agent. Solve the task."


def run(task: str, llm, roles: dict, *, total_budget: int, max_subtasks: int = 6, max_parallel: int = 3,
        max_handoffs: int = 2) -> dict:
    raise NotImplementedError


def run_single(task: str, llm) -> dict:
    raise NotImplementedError


def cost_report(multi: dict, single: dict) -> dict:
    raise NotImplementedError
