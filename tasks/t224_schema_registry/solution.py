"""Завдання №224: еволюція схем подій: реєстр схем і upcasting.

Події живуть роками: у журналі лежать події версії 1, а споживач уже на версії 4. Реєстр
схем (як Confluent Schema Registry) не пускає несумісні зміни, а upcasting підтягує старі
події до поточної схеми під час читання.

Схема це словник:
    {"fields": {"name": {"type": "string", "required": True, "default": ...}, ...}}
    * `type`: одне з `"string"`, `"int"`, `"float"`, `"bool"`, `"list"`, `"dict"` (обовʼязкове);
    * `required`: `bool`, за замовчуванням `True`;
    * `default`: необовʼязкове; якщо є, то має відповідати `type`.
Поле «може бути відсутнім» (`tolerates_absence`), якщо `required` це `False` АБО є `default`.
Значення відповідає типу так: `string` це `str`; `int` це `int` (не `bool`); `float` це `float`
або `int` (не `bool`); `bool` це `bool`; `list`; `dict`. `None` допустимий лише для поля з
`required: False`. Некоректна схема це `ValueError`.

`IncompatibleSchemaError(reasons)`: виняток з атрибутом `reasons`: список пар `(код, поле)`,
відсортований за `(поле, код)`, без дублікатів.

`SchemaRegistry(default_mode="backward")`: режими `"none"`, `"backward"`, `"forward"`,
`"full"` (інакше `ValueError`).
    `set_mode(subject, mode)`: режим конкретного subject; без нього діє `default_mode`.
    `check(subject, schema) -> list[tuple[str, str]]`: причини несумісності нової схеми з
        ОСТАННЬОЮ зареєстрованою версією за режимом subject (порожньо, якщо версій ще немає
        або режим `none`). Нічого не реєструє. Невалідна схема це `ValueError`.
    `register(subject, schema) -> int`: версії нумеруються з 1. Схема, що дорівнює останній
        (за вмістом), не створює нової версії й повертає номер останньої. Якщо `check` дав
        причини, це `IncompatibleSchemaError(reasons)`, нічого не реєструється. Порівняння
        лише з останньою версією (не транзитивно).
    `get(subject, version) -> dict`: копія схеми; невідомий subject чи версія це `KeyError`.
    `latest(subject) -> tuple[int, dict]`: номер і копія останньої; невідомий subject це `KeyError`.
    Зміна переданого словника після `register` не повинна змінювати збережену схему.

Правила сумісності (старий словник полів `O`, новий `N`):
    BACKWARD: новий читач `N` читає дані, записані за `O`:
        * поле є в `N`, немає в `O`, і `N` не допускає відсутності: `("added-required-field", поле)`;
        * поле є в обох, тип змінився (крім розширення `int` в `O` -> `float` в `N`):
          `("type-changed", поле)`;
        * поле є в обох, `N` не допускає відсутності, а `O` допускав: `("became-required", поле)`.
        Поля, що є лише в `O`, дозволені (читач їх ігнорує).
    FORWARD: старий читач `O` читає дані, записані за `N`:
        * поле є в `O`, немає в `N`, і `O` не допускає відсутності:
          `("removed-required-field", поле)`;
        * поле є в обох, тип змінився (крім випадку, коли `O` це `float`, а `N` це `int`:
          старий читач приймає ціле): `("type-changed", поле)`;
        * поле є в обох, `O` не допускає відсутності, а `N` допускає: `("became-optional", поле)`.
        Поля, що є лише в `N`, дозволені.
    FULL: обʼєднання причин BACKWARD і FORWARD (дублікати прибрати).
    NONE: без перевірок.

`UpcastError`: виняток для даних, які неможливо привести до схеми.
`register_upcaster(subject, from_version, fn)`: `fn(data: dict) -> dict` переводить дані з версії
    `from_version` у `from_version + 1`. Обидві версії мають існувати, інакше `ValueError`;
    повторна реєстрація для тієї самої версії перезаписує.
`upcast(subject, version, data, to_version=None) -> dict`: нова копія даних на версії
    `to_version` (за замовчуванням остання). Алгоритм:
    1. `data` має відповідати схемі `version`: усі поля, що не допускають відсутності, є;
       типи правильні; невідомих полів немає. Інакше `UpcastError`.
    2. Кожен крок `v -> v+1`: якщо для `v` зареєстрований upcaster, він викликається на КОПІЇ
       даних; інакше автокрок: відсутні поля нової схеми заповнюються `default` (у вигляді
       копії), а поля, яких у новій схемі немає, видаляються.
    3. Результат кроку перевіряється за схемою `v+1` як у пункті 1 (після автокроку помилкою
       може бути лише відсутнє обовʼязкове поле без `default` чи тип). Інакше `UpcastError`.
    Вхідний `data` не змінюється. `to_version < version` це `ValueError`; невідомий
    subject/версія це `KeyError`.
"""
import copy


class IncompatibleSchemaError(Exception):
    def __init__(self, reasons):
        super().__init__(f"incompatible schema: {reasons}")
        self.reasons = reasons


class UpcastError(Exception):
    pass


class SchemaRegistry:
    def __init__(self, default_mode: str = "backward"):
        raise NotImplementedError

    def set_mode(self, subject: str, mode: str) -> None:
        raise NotImplementedError

    def check(self, subject: str, schema: dict) -> list:
        raise NotImplementedError

    def register(self, subject: str, schema: dict) -> int:
        raise NotImplementedError

    def get(self, subject: str, version: int) -> dict:
        raise NotImplementedError

    def latest(self, subject: str) -> tuple:
        raise NotImplementedError

    def register_upcaster(self, subject: str, from_version: int, fn) -> None:
        raise NotImplementedError

    def upcast(self, subject: str, version: int, data: dict, to_version: int | None = None) -> dict:
        raise NotImplementedError
