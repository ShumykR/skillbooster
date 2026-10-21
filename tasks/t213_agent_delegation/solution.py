"""Завдання №213: делеговані права агента (token exchange, RFC 8693).

AI-агент діє від імені користувача. Передавати йому токен користувача «як є» небезпечно
(CWE-269, CWE-863): агент отримує всі права користувача на всі ресурси. Тому агент ОБМІНЮЄ токен
користувача на новий: вужчий, короткоживучий, привʼязаний до одного ресурсу, з записом, хто
саме діє (`act`). Криптографії немає: токен це `dict`, час передається параметром `now` (int).

Токен:
    {"sub": "alice",                       # користувач
     "aud": "files-api" | ["a", "b"],      # ресурс(и), для яких токен виданий
     "scope": "files:read calendar:read",  # імена через пробіл (точний збіг, без wildcard)
     "iat": int, "exp": int,
     "act": {"sub": "agent-b", "act": {"sub": "agent-a"}}}   # необовʼязково
`act` вкладений: ПОТОЧНИЙ виконавець це зовнішній `act`, раніше делегований лежить всередині.

Політика:
    {"max_ttl": 300,        # секунд
     "max_depth": 3,        # максимум елементів у ланцюжку act
     "agents": {            # зареєстровані агенти; решта це `unknown-actor`
        "agent-a": {"audiences": ["files-api"],               # куди агенту взагалі можна
                    "max_scope": ["files:read", "files:write"],  # стеля прав агента
                    "delegates_to": ["agent-b"]}}}            # кому він може передати право далі

`ExchangeError(code, detail=())`: помилка обміну; `code` одне з:
`invalid-token`, `expired`, `unknown-actor`, `delegation-not-allowed`, `actor-cycle`,
`chain-too-deep`, `audience-not-allowed`, `audience-mismatch`, `scope-escalation`, `empty-scope`.
(Клас уже готовий нижче.)

`exchange(subject_token, actor_id, audience, now, policy, task_scope, requested_scope=None) -> dict`
    Видає новий токен. Перевірки в ТАКОМУ порядку (перша невдала дає помилку):
    1. `invalid-token`: `subject_token` не dict або без `sub`, `aud`, `scope`, `exp`, або `act` не dict.
    2. `expired`: `now >= exp` токена.
    3. `unknown-actor`: `actor_id` немає в `policy["agents"]`.
    4. `delegation-not-allowed`: у токені вже є `act`, а поточний виконавець (зовнішній
       `act["sub"]`) не має `actor_id` у своєму `delegates_to` (агент не може сам собі видати
       право, передане іншому агентові: заборона ескалації між агентами).
    5. `actor-cycle`: `actor_id` уже є в ланцюжку `act` (у будь-якій позиції).
    6. `chain-too-deep`: довжина ланцюжка з новим виконавцем перевищила `max_depth`.
    7. `audience-not-allowed`: `audience` не входить в `audiences` агента.
    8. `audience-mismatch`: `audience` не входить в `aud` токена, який обмінюють (токен для
       однієї служби не можна обміняти на токен для іншої: confused deputy).
    9. `scope-escalation`: дозволене = scope токена ∩ `task_scope` ∩ `max_scope` агента. Якщо
       `requested_scope` (рядок через пробіл або ітерабельне) містить щось поза дозволеним,
       помилка, `detail` це відсортований список зайвих імен. Не вказано (`None`): береться
       все дозволене.
    10. `empty-scope`: підсумковий набір порожній.
    Результат: `sub` користувача; `aud` це РІВНО рядок `audience`; `scope` відсортований через
    пробіл; `iat = now`; `exp = min(now + max_ttl, exp токена)`; `act = {"sub": actor_id}` і,
    якщо в токені вже був `act`, то він вкладається як `act["act"]` (ланцюжок росте). Вхідний
    токен і політика НЕ змінюються.

`authorize(token, audience, required_scope, now) -> tuple[bool, str]`
    Перевірка на боці ресурсу. Причини: `"ok"`, `"invalid-token"` (не dict, немає
    `sub`/`aud`/`scope`/`exp`), `"expired"` (`now >= exp`), `"wrong-audience"` (`audience` не
    входить в `aud`: рядок чи список), `"insufficient-scope"` (`required_scope`, рядок чи
    ітерабельне, не є підмножиною scope токена). Порядок саме такий.

`audit_chain(token) -> list[str]`
    Хронологічний ланцюжок для аудиту: `[sub, перший агент, ..., поточний агент]`
    (для `{"sub":"alice","act":{"sub":"b","act":{"sub":"a"}}}` це `["alice", "a", "b"]`).
    Порушений ланцюжок (цикл у вкладених `act`, `act` не dict, немає `sub` у ланці, глибина
    понад 10) це `ValueError`.
"""


class ExchangeError(Exception):
    def __init__(self, code: str, detail=()):
        super().__init__(code)
        self.code = code
        self.detail = list(detail)


def exchange(subject_token: dict, actor_id: str, audience: str, now: int, policy: dict,
             task_scope, requested_scope=None) -> dict:
    raise NotImplementedError


def authorize(token: dict, audience: str, required_scope, now: int) -> tuple[bool, str]:
    raise NotImplementedError


def audit_chain(token: dict) -> list[str]:
    raise NotImplementedError
