"""Завдання №184: агент як скінченний автомат (патерн State, CWE-841).

Модель вирішує, ЩО викликати, але в якому СТАНІ це дозволено, вирішує код. Незворотні дії
(видалення, оплата, відправка) проходять через гейт людини (HITL), який агент не може
обійти чи «підтвердити» сам.

Стани: `"planning"` (початковий), `"acting"`, `"waiting_approval"`, `"done"`, `"failed"`
(`done` і `failed` термінальні).

Інструменти: `tools = {name: {"kind": "read" | "write" | "irreversible", "fn": callable}}`
(інший `kind` або відсутній `fn` це `ValueError` у конструкторі). Виклик `fn(**args)`.

Що дозволено де:
| стан             | read | write | irreversible                                   |
|------------------|------|-------|------------------------------------------------|
| planning         | так  | ні    | ні                                             |
| acting           | так  | так   | НЕ виконується: запит на підтвердження         |
| waiting_approval | ні   | ні    | ні (будь-який `call`, поки очікуємо людину)    |
| done / failed    | ні   | ні    | ні                                             |

`AgentFSM(tools, *, clock, approval_timeout=300.0, max_denials=3, on_escalate=None)`
`clock()` повертає секунди (float), `on_escalate(event: dict)` необовʼязковий колбек.

`state` властивість: поточний стан.

`call(tool, args=None) -> dict`   (виклики моделі: НІКОЛИ не піднімає винятків)
    * `{"status": "ok", "result": <значення fn>}`;
    * `{"status": "denied", "reason": <код>}`; стан не змінюється. Перевірки в порядку:
        1. термінальний стан: `"terminal_state"` (НЕ рахується в лічильник відмов);
        2. стан `waiting_approval`: `"waiting_approval"`;
        3. невідомий інструмент: `"unknown_tool"`;
        4. `args` не `dict` і не `None`: `"bad_args"`;
        5. `kind` не дозволений у стані (див. таблицю, напр. write у planning):
           `"not_allowed_in_state"`.
      Кожна відмова, крім п.1, збільшує лічильник; коли він досягає `max_denials`, стан стає
      `failed` (причина переходу `"too_many_denials"`: модель, що ломиться в заборонене,
      вважається скомпрометованою). Сама відповідь лишається `denied` зі своїм кодом;
    * `{"status": "pending_approval", "call_id": "c1"}`: незворотний інструмент у `acting`.
      Нічого не виконується. Стан `waiting_approval`, запамʼятовується копія `args`, час
      запиту `clock()`. `call_id` це `"c" + порядковий номер запиту` (c1, c2, ...);
    * `{"status": "error", "error": <імʼя класу винятку>}`: `fn` кинув виняток: стан `failed`
      (причина `"executor_error"`, fail closed).
`finish_planning(plan: list[str])`  planning -> acting (причина `"plan_ready"`). План це
    непорожній список непорожніх рядків, інакше `ValueError`.
`approve(call_id, approver) -> dict`   (API ЛЮДИНИ)
    * не в `waiting_approval` чи інший `call_id`: `IllegalTransition`;
    * `approver` не непорожній рядок: `ValueError`;
    * `approver` (без урахування регістру) `"agent"`, `"model"` чи `"assistant"`:
      `{"status": "denied", "reason": "self_approval"}`, стан не змінюється;
    * якщо `clock() - requested_at >= approval_timeout`: ескалація (див. `tick`) і
      `{"status": "denied", "reason": "expired"}`;
    * інакше виконується інструмент із ЗБЕРЕЖЕНИМИ args, стан `acting` (причина
      `"approved"`), результат як у `call` (`ok` або `error`, тоді `failed`).
`reject(call_id, approver) -> dict`   waiting_approval -> acting (причина `"rejected"`),
    інструмент не виконується, `{"status": "rejected", "call_id": call_id}`. Ті самі
    винятки для стану/`call_id`/`approver`, що й у `approve` (крім перевірки самооцінки).
`tick() -> str`   викликається планувальником. Якщо стан `waiting_approval` і
    `clock() - requested_at >= approval_timeout` (межа ВКЛЮЧНО): стан `failed` (причина
    `"approval_timeout"`) і ескалація: колбек `on_escalate` викликається РІВНО раз з
    `{"reason": "approval_timeout", "call_id", "tool", "args", "waited": секунди}`. Виняток із
    колбека не заважає переходу у `failed`. Повертає поточний стан.
`complete(summary)`  acting -> done (причина `"completed"`); `summary` непорожній рядок
    (`ValueError`); з іншого стану `IllegalTransition`.
`fail(reason)`  будь-який нетермінальний стан -> failed з наданою причиною; з термінального
    `IllegalTransition`.
`pending` властивість: копія `{"call_id", "tool", "args", "requested_at"}` у стані
    `waiting_approval`, а в усіх інших станах `None`.
`history` властивість: копія списку переходів `{"from", "to", "reason"}` по порядку.
"""


class IllegalTransition(Exception):
    """Перехід, неможливий зі стану (помилка коду, що викликає, а не моделі)."""


class AgentFSM:
    def __init__(self, tools: dict, *, clock, approval_timeout: float = 300.0, max_denials: int = 3,
                 on_escalate=None):
        raise NotImplementedError

    @property
    def state(self) -> str:
        raise NotImplementedError

    @property
    def pending(self):
        raise NotImplementedError

    @property
    def history(self) -> list:
        raise NotImplementedError

    def call(self, tool: str, args=None) -> dict:
        raise NotImplementedError

    def finish_planning(self, plan: list) -> None:
        raise NotImplementedError

    def approve(self, call_id: str, approver: str) -> dict:
        raise NotImplementedError

    def reject(self, call_id: str, approver: str) -> dict:
        raise NotImplementedError

    def tick(self) -> str:
        raise NotImplementedError

    def complete(self, summary: str) -> None:
        raise NotImplementedError

    def fail(self, reason: str) -> None:
        raise NotImplementedError
