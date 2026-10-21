"""Завдання №241: помилки й винятки: fail closed (OWASP A10:2025 Mishandling of Exceptional Conditions).

Дві частини. Код студента ніколи не виконується: аудит працює лише через модуль `ast`.

1. `audit_source(source: str) -> list[tuple[str, int]]`
   Аналізує текст Python-коду й повертає знахідки `(rule, line)`, відсортовані за
   `(line, rule)`, без дублікатів. Некоректний синтаксис це `ValueError`. `try/except*`
   (`ast.TryStar`) обробляється так само, як `try`. Вкладені `def`/`lambda`/`class` усередині
   обробника чи `finally` НЕ скануються (їхній `raise`/`return` не стосується обробника).

   Визначення:
   * «широкий» тип: `Exception` або `BaseException` (імʼям, як `builtins.Exception`, чи
     елементом кортежу). Обробник без типу (`except:`) це «голий».
   * «тривіальне» тіло обробника: усі інструкції це `pass`, `continue` або вираз-константа
     (`...`, рядок).

   Правила (рядок знахідки це `lineno` обробника `except`, якщо не сказано інакше):
   | rule                    | коли |
   |-------------------------|------|
   | `bare-except`           | `except:` без типу (CWE-396) |
   | `swallowed`             | голий або широкий обробник із тривіальним тілом (CWE-390) |
   | `broad-except`          | широкий (НЕ голий) обробник, у тілі якого немає жодного `raise` (CWE-396) |
   | `fail-open`             | голий або широкий обробник містить `return <константа>`, що істинна (`True`, число != 0, непорожній рядок/bytes): помилка стає дозволом (CWE-636) |
   | `error-detail-leak`     | у обробнику значення `return` або keyword-аргумент `detail`/`content`/`body`/`message` містить: виклик `format_exc`/`format_exception`/`format_tb` (за імʼям чи як атрибут), `str(e)`/`repr(e)`, f-рядок із `e` або `e.args`, де `e` це імʼя з `except ... as e` (CWE-209) |
   | `ignored-verification`  | `try`, тіло якого викликає функцію чи метод, імʼя якого (без урахування регістру) містить `verify`, `validate` або `check_sig`, а обробник не містить жодного `raise`, `return`, `continue`, `break`: після провалу перевірки код іде далі як ніби все добре (CWE-755) |
   | `return-in-finally`     | `return` усередині `finally` (ковтає виняток; рядок це `lineno` самого `return`) (CWE-390) |

   Один обробник може мати кілька знахідок (наприклад, `except Exception: pass` це
   `broad-except` і `swallowed`). Специфічні типи (`except KeyError: pass`) самі по собі НЕ
   знахідка.

2. `fail_closed(logger)` декоратор для функцій авторизації/перевірки доступу.
   * Результат функції пропускається, лише якщо він `is True`; будь-що інше (`None`, `1`,
     `"yes"`, непорожній словник) це `False`.
   * Будь-який `Exception` усередині: результат `False` і РІВНО один виклик
     `logger.exception(msg, *args)`: повідомлення (після `msg % args`, якщо `args` є) містить
     імʼя функції та імʼя класу винятку, але НЕ значення аргументів виклику (там можуть бути
     токени). Якщо сам `logger.exception` кидає виняток, результат все одно `False`.
   * `BaseException`, що не є `Exception` (`KeyboardInterrupt`, `SystemExit`,
     `asyncio.CancelledError`) проходить нагору без змін.
   * Працює для звичайних і `async def` функцій (для async обгортка теж `async`), зберігає
     `__name__`/`__doc__` (`functools.wraps`), передає `*args, **kwargs`.
"""


def audit_source(source: str) -> list[tuple[str, int]]:
    raise NotImplementedError


def fail_closed(logger):
    raise NotImplementedError
