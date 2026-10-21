"""Завдання №191: Evals траєкторій агента: інструменти, порядок, зайві виклики, pass@k і pass^k.

Агент може дійти до правильної відповіді «не тим шляхом»: викликати заборонений інструмент, зациклитись на одному
запиті, пропустити обов'язковий крок або спершу зробити зміну, а потім перевірку. Тому в evals агентів перевіряють не лише
фінальний текст, а й ТРАЄКТОРІЮ. А оскільки агент недетермінований, одного запуску мало: рахують pass@k і pass^k.

Траєкторія:   {"steps": [{"tool": str, "args": dict}, ...], "final": str}   (`final` необовʼязковий, за замовчуванням "")
Специфікація: dict з необовʼязковими ключами (невідомий ключ: ValueError):
    "required":    list[str]            кожен інструмент має бути викликаний щонайменше раз
    "forbidden":   list[str]            жоден із них не має бути викликаний
    "order":       list[[a, b], ...]    пари часткового порядку: КОЖЕН виклик b має мати раніше щонайменше один виклик a
                                        (якщо b немає в траєкторії, пара виконана; якщо b є, а a перед ним немає: порушення)
    "max_calls":   int                  усього викликів не більше (len(steps) > max_calls: порушення)
    "max_repeats": int                  однаковий виклик (той самий tool і ті самі args, порівнювати через
                                        json.dumps(args, sort_keys=True)) не більше стількох разів
Крок без рядкового "tool" чи траєкторія без списку "steps": ValueError.

`evaluate_trajectory(traj, spec, *, success=None) -> dict`
    Повертає {"ok": bool, "violations": [str, ...]}. Коди порушень (унікальні, відсортовані за алфавітом):
      "missing-tool:<tool>"        обовʼязковий інструмент не викликано
      "forbidden-tool:<tool>"      заборонений викликано (один код на інструмент, скільки б разів він не викликався)
      "order:<a>><b>"              порушено пару порядку (один код на пару)
      "too-many-calls"             перевищено max_calls
      "repeated-call:<tool>"       однаковий виклик цього інструмента повторено більше за max_repeats (один код на інструмент)
      "task-failed"                `success` задано, але `success(final)` повернув хибне значення або кинув Exception
    `success(final: str) -> bool` це перевірка результату задачі (функція-параметр). ok це відсутність порушень.

`pass_at_k(n, c, k) -> float`
    Незміщена оцінка ймовірності, що ХОЧА Б ОДИН із k запусків успішний, за n запусків, з яких c успішних:
    1 - C(n-c, k) / C(n, k). Якщо n-c < k, результат 1.0. Це метрика «можливості» (чи вміє агент взагалі).
`pass_hat_k(n, c, k) -> float`
    Оцінка ймовірності, що ВСІ k запусків успішні (метрика надійності, як pass^k у τ-bench): C(c, k) / C(n, k).
    Умови для обох: 0 <= c <= n, 1 <= k <= n, цілі числа (не bool), інакше ValueError.

`run_agent_eval(agent, tasks, *, n=5, ks=(1, 3)) -> dict`
    tasks: список {"id", "input", "spec", "success" (необовʼязково)}. Для кожної задачі агент запускається n разів:
    `agent(task["input"], attempt)` де attempt це 0..n-1, повертає траєкторію. Виняток агента (чи некоректна
    траєкторія): запуск провалений з кодом "agent-error". Будь-яке k > n або n < 1: ValueError (до запусків).
    Результат:
      {"tasks": {id: {"n": n, "c": успішних, "pass_at_k": {k: float}, "pass_hat_k": {k: float},
                      "violations": {код: у скількох запусках зустрівся}}},   # словник відсортований за кодом
       "pass_at_k": {k: середнє по задачах}, "pass_hat_k": {k: середнє по задачах}}
    Порожній список задач: ValueError.
"""


def evaluate_trajectory(traj: dict, spec: dict, *, success=None) -> dict:
    raise NotImplementedError


def pass_at_k(n: int, c: int, k: int) -> float:
    raise NotImplementedError


def pass_hat_k(n: int, c: int, k: int) -> float:
    raise NotImplementedError


def run_agent_eval(agent, tasks: list[dict], *, n: int = 5, ks: tuple = (1, 3)) -> dict:
    raise NotImplementedError
