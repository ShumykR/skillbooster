r"""Завдання №255: security-лінтер для диффу від AI.

AI-асистент пише багато коду, а ревʼю бачить лише дифф. Лінтер читає unified diff (формат
`git diff`), перевіряє ЛИШЕ додані рядки і повертає коментарі до рядків. Старі проблеми в
контекстних чи видалених рядках не звітуються (інакше лінтер заглушать). Код зі збірки диффу
ніколи не виконується: усі перевірки через `ast` і регулярні вирази.

`lint_diff(diff: str) -> list[dict]`
    Повертає знахідки `{"file": str, "line": int, "rule": str, "cwe": int, "comment": str}`,
    відсортовані за `(file, line, rule)`, без дублікатів `(file, line, rule)`.
    * `file`: шлях після `+++ b/` (без `b/`; хвіст після табуляції відкинути). Файли з
      `+++ /dev/null` (видалені) і двійкові пропускаються.
    * `line`: номер рядка в НОВОМУ файлі (лічильник береться з `@@ -a,b +c,d @@`: контекстні й
      додані рядки його збільшують, видалені ні; `@@ -1 +1 @@` означає лічильник 1).
    * Межі hunk визначаються ЛІЧИЛЬНИКАМИ із заголовка, а не за виглядом рядка: видалений
      рядок SQL-коментаря `-- comment` у диффі виглядає як `--- comment`, але це не заголовок
      файлу. Рядок `\ No newline at end of file` ігнорується. Порожній дифф чи текст без hunk це
      `[]`; заголовок `@@`, який не розбирається, це `ValueError`.
    * AST-правила діють лише для файлів `*.py`. Фрагмент розбирається так: спершу весь новий
      бік hunk (контекстні + додані рядки, `textwrap.dedent`); якщо це не парситься, то кожен
      блок підряд доданих рядків окремо; якщо й це ні, то кожен доданий рядок окремо.
      Фрагмент, що не парситься, пропускається без помилки. Вузол AST звітується, лише якщо
      хоча б один рядок його діапазону `lineno..end_lineno` доданий; `line` це ПЕРШИЙ доданий
      рядок діапазону.
    * Правило секретів діє на додані рядки ВСІХ файлів (`.env`, yaml, py).

Правила (`rule`, `cwe`; у `comment` має бути підрядок, указаний у стовпці «слово», без
урахування регістру; `comment` це непорожнє пояснення з виправленням):
| rule                      | cwe | що ловимо | слово |
|---------------------------|-----|-----------|-------|
| `tls-verify-disabled`     | 295 | виклик із `verify=False`; виклик `ssl._create_unverified_context(...)` | `verify=True` |
| `shell-injection`         | 78  | виклик із `shell=True`, чия команда (перший позиційний аргумент або `args=`) динамічна; `os.system`/`os.popen` з динамічною командою. «Динамічна» це f-рядок із підстановкою, `+` чи `%` із не-константою, `"...".format(...)`. Константний рядок із `shell=True` не знахідка | `shell=False` |
| `unsafe-yaml-load`        | 502 | `yaml.load(...)` без Loader із `SafeLoader`/`CSafeLoader` (ключове або другий позиційний аргумент); будь-який `yaml.unsafe_load` | `safe_load` |
| `unsafe-deserialization`  | 502 | `pickle`/`cPickle`/`_pickle`/`dill`/`marshal` `.load`/`.loads`, чий перший аргумент НЕ літерал | `json` |
| `hardcoded-secret`        | 798 | див. нижче | `environment` |
| `sql-injection`           | 89  | виклик `execute`/`executemany`/`executescript`/`text`/`raw` (імʼя чи атрибут), перший аргумент якого динамічний (як вище) | `parameter` |
| `insecure-random-token`   | 330 | присвоєння (або `AnnAssign`), ціль якого (`Name.id` чи `Attribute.attr`) відповідає `token\|secret\|passw\|otp\|nonce\|api_?key\|session\|csrf\|salt\|reset_?code` (без регістру), а значення містить виклик `random.<choice\|choices\|randint\|random\|getrandbits\|randrange\|sample\|randbytes>`; або `return` із таким викликом у функції з такою назвою | `secrets` |
| `cors-wildcard-credentials` | 942 | виклик, де `allow_origins` це `"*"` або список/кортеж/множина з `"*"`, а `allow_credentials=True` | `origins` |
| `debug-enabled`           | 489 | `DEBUG = True`, `<x>.debug = True`; виклик `run`/`FastAPI`/`Flask`/`Starlette`/`Quart` із `debug=True` | `DEBUG` |

Секрети (`hardcoded-secret`), максимум одна знахідка на рядок; значення секрету НЕ повинно
потрапити в `comment` (максимум перші 4 символи):
* відомі префікси в будь-якому місці рядка: `AKIA[0-9A-Z]{16}`, `ghp_[A-Za-z0-9]{36}`,
  `xox[baprs]-[A-Za-z0-9-]{10,}`, `sk-[A-Za-z0-9_-]{20,}`, блок
  `-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----`;
* або присвоєння/ключ рядкового літерала довжиною >= 20 без пробілів, імʼя якого містить
  `secret`, `token`, `passwd`, `password`, `api_key`/`api-key`/`apikey`, `private_key`,
  `access_key` (без регістру), ентропія Шеннона значення >= 3.5 біта на символ, і воно не є
  заглушкою: містить (без регістру) `example`, `changeme`, `your`, `placeholder`, `xxxx`,
  або починається з `${`, `<`, `{{`, `%(`.
"""


def lint_diff(diff: str) -> list[dict]:
    raise NotImplementedError
