"""Завдання №177: constrained decoding.

Модель не вміє «гарантувати» валідний JSON: вона лише оцінює ймовірності наступного токена.
Constrained decoding (як у Outlines, xgrammar, llguidance) вирішує це інакше: на КОЖНОМУ кроці
рахується маска допустимих токенів словника, а недопустимі отримують ймовірність 0. Тоді
невалідний JSON фізично неможливий. Ти реалізуєш скінченний автомат префіксів для вузької
підмножини JSON Schema та цикл генерації з маскою. Жодної мережі й LLM: «модель» це функція
`choose`, яку передає тест.

Підмножина схеми (усе інше це `ValueError` з БУДЬ-ЯКОЇ функції нижче):
    {"type": "object", "properties": {ключ: опис, ...}, "required": [...]}
* `required` необовʼязковий; якщо є, має містити РІВНО всі ключі з `properties` (необовʼязкових
  полів немає). Зайвих ключів у обʼєкті бути не може. `properties` може бути порожнім.
* опис поля, одне з:
    {"type": "string", "maxLength": n}  n це `int` 0..64 (не `bool`), за замовчуванням 16
    {"type": "integer"}
    {"type": "boolean"}
    {"enum": [рядок, ...]}              непорожній список унікальних рядків
  Вкладених обʼєктів і масивів немає.

Канонічний вивід (єдиний допустимий текст): компактний JSON БЕЗ пробілів, поля СТРОГО в порядку
`properties`: `{"k1":v1,"k2":v2}`; порожній обʼєкт це `{}`. Ключі й enum-значення записуються
як `json.dumps(s)` (з `ensure_ascii=False`).
* string: `"` + символи + `"`. Символ це будь-який, крім `"`, `\\` і керівних (< U+0020), або
  екранування `\\"`, `\\\\`, `\\n` (лише ці три). Екранування це ОДИН символ для `maxLength`.
  Не-ASCII символи (`é`, `я`) дозволені як є.
* integer: `0` або `-?[1-9][0-9]{0,8}` (до 9 цифр; `-0`, `01`, `+1`, `1.0` недопустимі).
* boolean: `true` або `false`. enum: один із рядків, записаний як JSON-рядок.

Функції:

`valid_prefix(schema, text) -> bool`
    Чи можна дописати `text` до повного валідного документа (порожній рядок це префікс).
    Повний документ теж префікс самого себе; будь-який символ ПІСЛЯ повного документа робить
    текст невалідним.
`is_complete(schema, text) -> bool`
    Чи `text` це повний валідний документ.
`token_mask(schema, prefix, vocab) -> list[bool]`
    `vocab` це список токенів (рядки довжиною 1..3 символи, інакше `ValueError`).
    `mask[i]` це `True` тоді й лише тоді, коли `valid_prefix(schema, prefix + vocab[i])`.
    Якщо `prefix` сам не є валідним префіксом, `ValueError`. Токен може перетинати межі
    елементів (наприклад `","` закриває рядок, ставить кому й відкриває ключ).
`constrained_generate(schema, vocab, choose, max_steps=200) -> str`
    Цикл: поки `text` не повний, порахуй маску й список дозволених індексів, виклич
    `choose(text, allowed)` (повертає індекс зі списку `allowed`) і допиши токен.
    * `choose` повернув індекс поза `allowed` це `ValueError`;
    * дозволених токенів немає, а документ неповний (словник не вміє продовжити) це
      `RuntimeError`;
    * за `max_steps` кроків документ не завершився це `RuntimeError`.
    Повертає повний валідний документ.
"""


def valid_prefix(schema: dict, text: str) -> bool:
    raise NotImplementedError


def is_complete(schema: dict, text: str) -> bool:
    raise NotImplementedError


def token_mask(schema: dict, prefix: str, vocab: list[str]) -> list[bool]:
    raise NotImplementedError


def constrained_generate(schema: dict, vocab: list[str], choose, max_steps: int = 200) -> str:
    raise NotImplementedError
