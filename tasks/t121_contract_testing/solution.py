"""Завдання №121: contract testing: чи не зламає зміна API тих, хто ним користується (consumer-driven contracts).

Споживач (фронтенд, інший сервіс) очікує від API певні поля й типи. Провайдер змінює API й не знає, чи цього хтось не чекає. Контракт це
запис «що саме мені потрібно», і його перевіряють при кожній зміні провайдера. Pact і schemathesis роблять це з реальними запитами, а тут
ти зробиш ядро: порівняння на рівні схем.

Схема провайдера (спрощений OpenAPI): {"GET /users/{id}": {
        "query":     {"verbose": {"type": "bool", "required": False}},
        "request":   {"name": {"type": "str", "required": True}},                     # поля тіла запиту
        "responses": {200: {"id": {"type": "int", "required": True}, "email": {"type": "str", "required": False}}, 404: {}}}}
    Відсутні "query" і "request" означають порожні. Коди статусів це цілі числа. Типи це рядки: "int", "float", "number", "str", "bool", ...

Контракт споживача (одна взаємодія): {"endpoint": "GET /users/{id}", "query": ["verbose"], "request": {"name": "str"},
    "status": 200, "response": {"id": "int", "email": "str"}}   (query, request і response необовʼязкові; query це імена параметрів; без "status" перевірки відповіді пропускаються).

accepts(expected, actual) -> bool    actual == expected, або expected == "number" і actual в ("int", "float").

verify_contract(provider, interactions) -> list[str]
    Відсортований список унікальних порушень (порожній, якщо контракт виконується). Для кожної взаємодії:
      * ендпоінта немає в схемі: "missing_endpoint:<endpoint>" (решта перевірок цієї взаємодії пропускається);
      * параметра запиту немає в query провайдера: "unknown_param:<endpoint>:<імʼя>";
      * поле запиту, якого провайдер не приймає: "unknown_request_field:<endpoint>:<поле>"; тип, який провайдер не приймає
        (not accepts(тип провайдера, тип споживача)): "type_mismatch:<endpoint>:request.<поле>:<тип споживача>!=<тип провайдера>";
      * обовʼязкове поле запиту провайдера, яке споживач не надсилає: "missing_required_request:<endpoint>:<поле>";
      * статусу немає серед responses: "missing_status:<endpoint>:<статус>" (перевірки відповіді пропускаються);
      * поля відповіді, якого провайдер не повертає: "missing_field:<endpoint>:<статус>:<поле>";
      * поле є, але необовʼязкове (споживач на нього покладається): "optional_field:<endpoint>:<статус>:<поле>";
      * тип провайдера не підходить споживачу (not accepts(тип споживача, тип провайдера)):
        "type_mismatch:<endpoint>:<статус>:<поле>:<тип споживача>!=<тип провайдера>".

diff_schemas(old, new) -> list[str]
    Критичні зміни провайдера для вже наявних клієнтів, відсортований список унікальних записів:
      * ендпоінт зник: "removed_endpoint:<endpoint>" (решта для нього пропускається);
      * статус відповіді зник: "removed_status:<endpoint>:<статус>";
      * поле відповіді (старого статусу, який лишився) зникло: "removed_field:<endpoint>:<статус>:<поле>";
      * тип поля відповіді змінився: "type_changed:<endpoint>:<статус>:<поле>:<старий>-><новий>";
      * поле відповіді було обовʼязковим, стало необовʼязковим: "became_optional:<endpoint>:<статус>:<поле>";
      * нове обовʼязкове поле запиту (в new воно required, а в old його не було або воно не було обовʼязковим):
        "new_required_request:<endpoint>:<поле>";
      * тип поля запиту змінився (поле є в обох): "request_type_changed:<endpoint>:<поле>:<старий>-><новий>";
      * новий обовʼязковий параметр запиту (аналогічно полю запиту): "new_required_param:<endpoint>:<імʼя>".
    НЕ є критичним: нові ендпоінти, нові поля відповіді, нові необовʼязкові поля й параметри запиту, поле відповіді, що стало обовʼязковим.
is_breaking(old, new) -> bool        diff_schemas(old, new) не порожній.
"""


def accepts(expected: str, actual: str) -> bool:
    raise NotImplementedError


def verify_contract(provider: dict, interactions: list[dict]) -> list[str]:
    raise NotImplementedError


def diff_schemas(old: dict, new: dict) -> list[str]:
    raise NotImplementedError


def is_breaking(old: dict, new: dict) -> bool:
    raise NotImplementedError
