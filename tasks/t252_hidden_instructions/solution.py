"""Завдання №252: детектор прихованих інструкцій у файлах, які читає coding-агент.

Агент довіряє тексту README, `AGENTS.md`, `CLAUDE.md`, `.cursor/rules`, коментарям і описам
issue. Зловмисник ховає там інструкції, невидимі для людини в діффі (rules file backdoor,
Trojan Source). Твій сканер знаходить такі місця. Код і текст НЕ виконуються й не
«інтерпретуються», лише аналізуються.

`scan_text(text: str) -> list[dict]`
    Повертає знахідки `{"rule", "line", "col", "detail"}`. `line` і `col` рахуються з 1,
    `col` у символах Unicode (code points) від початку рядка (рядки розділяє `\\n`).
    Порядок: за `(line, col, rule)`. Правила:

    | rule                       | що шукати | detail |
    |----------------------------|-----------|--------|
    | `tag-characters`           | серія підряд символів U+E0000..U+E007F (прихований ASCII). Одна знахідка на серію, позиція першого символу | розкодований текст: символ U+E0020..U+E007E це `chr(cp - 0xE0000)`, інші символи серії пропускаються |
    | `zero-width`               | серія підряд символів U+200B, U+200C, U+200D, U+2060, U+FEFF. Одна знахідка на серію. Винятки: U+FEFF на самому початку тексту (BOM); U+200D, що стоїть відразу після емодзі-символу (код >= U+1F000, діапазон U+2600..U+27BF або U+FE0F), це законна склейка емодзі: така серія не знахідка | коди через пробіл, у порядку появи: `"U+200B U+200B"` |
    | `bidi-control`             | КОЖЕН символ U+202A..U+202E, U+2066..U+2069, U+200E, U+200F (Trojan Source) окремою знахідкою | `"U+202E"` |
    | `html-comment-instruction` | HTML-коментар `<!-- ... -->` (може бути багаторядковим), вміст якого (без урахування регістру) збігається з будь-яким із шаблонів нижче. Позиція це початок `<!--` | вміст коментаря без крайніх пробілів |
    | `base64-blob`              | слово `[A-Za-z0-9+/_-]{40,}` з 0..2 символами `=` в кінці, яке після декодування base64 (стандартного або urlsafe, з доповненням `=`) дає коректний UTF-8 довжиною >= 8 символів, де КОЖЕН символ друкований (`str.isprintable()`) або пробіл/таб/перенос рядка. Бінарні дані (хеші, зображення) не знахідка | перші 200 символів декодованого тексту |
    | `homoglyph-identifier`     | слово (максимальна серія символів `\\w`), що містить і латинські літери ASCII, і літери кирилиці чи грецької (за `unicodedata.name`: починається з `CYRILLIC` або `GREEK`). Слово повністю кирилицею (український текст) не знахідка | коди нелатинських літер через кому, унікальні, у порядку появи: `"U+0430,U+0435"` |

    Шаблони для `html-comment-instruction` (регістр ігнорується, застосовуються до вмісту):
      1. `\\b(ignore|disregard|forget)\\b.{0,40}\\b(previous|above|prior|earlier|all)\\b`
      2. `\\byou (must|should|will|are now)\\b`
      3. `\\b(do not|don't|never)\\s+(tell|mention|reveal|show)\\b`
      4. `\\bsystem prompt\\b`
      5. `\\b(ai|assistant|agent|claude|copilot|cursor)\\b.{0,30}\\b(must|should|always|run|execute|send|read|add|install)\\b`
      6. `\\b(curl|wget|eval|exec)\\b`
    (`.` у шаблонах збігається і з переносом рядка.) Звичайні коментарі на кшталт
    `<!-- TODO: update badge -->` чи `<!-- markdownlint-disable -->` не знахідка.
    Знахідки різних правил можуть перекриватися (base64 усередині коментаря це дві знахідки).

`scan_repo(files: dict[str, str]) -> list[dict]`
    Скануватиме кожен файл (`шлях -> вміст`) через `scan_text`, додає до знахідки поле
    `"file"` і повертає все одним списком, відсортованим за `(file, line, col, rule)`.

`verdict(findings: list[dict]) -> str`
    `"block"`, якщо є хоча б одна знахідка з правил `tag-characters`, `bidi-control`,
    `html-comment-instruction`; інакше `"review"`, якщо знахідки є; інакше `"ok"`.
"""


def scan_text(text: str) -> list[dict]:
    raise NotImplementedError


def scan_repo(files: dict[str, str]) -> list[dict]:
    raise NotImplementedError


def verdict(findings: list[dict]) -> str:
    raise NotImplementedError
