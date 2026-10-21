"""Завдання №242: дерево атак і вибір мітигацій.

Дерево атак це модель «як зловмисник досягає цілі»: корінь це ціль, вузол `OR` досягається
будь-якою дочірньою гілкою, вузол `AND` потребує ВСІХ дочірніх. Листки мають вартість для
атакувальника й імовірність успіху. Мітигація «вимикає» листки (атакувальник їх не може
виконати). Питання архітектора: який шлях найдешевший для атакувальника, як змінює картину
мітигація і які мітигації найдешевше перекривають усі шляхи до цілі.

Дерево (вкладені `dict`; усі `id` унікальні в усьому дереві):
    вузол:  {"id": "root", "type": "OR" | "AND", "children": [ ... ]}   (children не порожній)
    листок: {"id": "phish", "cost": 100, "prob": 0.3}                   (cost >= 0, 0 <= prob <= 1)
Корінь може бути й листком. Мітигація:
    {"id": "m_mfa", "cost": 150, "blocks": ["bypass_mfa", "phish"]}     (blocks: id ЛИСТКІВ)

Валідація (`ValueError` у КОЖНІЙ публічній функції): порожній чи нерядковий `id`, дублікати id,
`type` не `AND`/`OR`, порожній `children`, `cost` не число (`bool` не число), від'ємний чи
нескінченний, `prob` не число чи поза 0..1; у мітигацій: дублікат id, від'ємний `cost`,
порожній `blocks`, `blocks` з id, якого немає серед листків; `blocked`/`applied`/`budget`
з невідомим id чи від'ємним числом.

`cheapest_attack(tree, blocked=()) -> {"cost": число, "leaves": [id, ...]} | None`
    Найдешевший набір листків, що досягає кореня. Листки з `blocked` недоступні. `OR` бере
    найдешевшу дочірню гілку, `AND` сумує вартості всіх дочірніх. `None`, якщо ціль недосяжна.
    Ничия на `OR`: менша пара `(cost, відсортований список листків)` (порівняння кортежів);
    `AND` просто обʼєднує вибір кожної дочірньої гілки. `leaves` відсортований за алфавітом.
`success_probability(tree, blocked=()) -> float`
    Імовірність досягти цілі за умови незалежних листків: листок це `prob` (0 для заблокованого),
    `AND` це добуток, `OR` це `1 - добуток(1 - p)`.
`apply_mitigations(tree, mitigations, applied) -> dict`
    `applied` список id мітигацій. Результат:
    `{"blocked_leaves": [відсортовані id], "cheapest_before": ..., "cheapest_after": ...,
      "prob_before": float, "prob_after": float}` (`cheapest_*` у форматі `cheapest_attack`).
`choose_mitigations(tree, mitigations, budget) -> dict`
    Підмножина мітигацій із сумарною вартістю <= `budget`.
    * Якщо є підмножини, що роблять ціль недосяжною, обирай найдешевшу; при рівній вартості
      меншу за кількістю мітигацій; потім лексикографічно за відсортованим списком id.
      Результат `feasible: True`, `attack_cost_after: None`.
    * Інакше (`feasible: False`): підмножина в бюджеті, що МАКСИМІЗУЄ вартість найдешевшої
      атаки після неї; при рівності дешевша підмножина, потім менша, потім лексикографічно
      (порожня підмножина теж кандидат).
    Результат: `{"feasible": bool, "chosen": [відсортовані id], "total_cost": число,
    "attack_cost_after": число | None, "blocked_leaves": [відсортовані id]}`.
    Мітигацій не більше 16 (`ValueError` інакше): достатньо повного перебору.
"""


def cheapest_attack(tree: dict, blocked=()) -> dict | None:
    raise NotImplementedError


def success_probability(tree: dict, blocked=()) -> float:
    raise NotImplementedError


def apply_mitigations(tree: dict, mitigations: list[dict], applied: list[str]) -> dict:
    raise NotImplementedError


def choose_mitigations(tree: dict, mitigations: list[dict], budget) -> dict:
    raise NotImplementedError
