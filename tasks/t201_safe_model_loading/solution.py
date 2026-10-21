"""Завдання №201: безпечне завантаження моделей.

Файл моделі з інтернету (Hugging Face, чужий реліз) у форматі `pickle` (`.pkl`, `.pt`, `.bin`,
`.ckpt`) це ВИКОНУВАНИЙ КОД: `pickle.loads` викликає будь-яку функцію, яку назвав автор файлу
(`os.system`, `builtins.exec`). Формат `safetensors` це лише заголовок JSON і сирі тензори.
Тут ти пишеш перевірки ДО завантаження. Нічого в цьому завданні не виконує pickle:
`pickle.load`/`pickle.loads` викликати ЗАБОРОНЕНО (аналізуй лише опкоди через `pickletools`).

Дані-підказки (уже в модулі, користуйся ними):
    DENY_MODULES   модулі, для яких ЗАВЖДИ небезпечно (за першою частиною до крапки: `os.path` це `os`)
    DENY_BUILTINS  імена з `builtins`, небезпечні завжди
    DEFAULT_ALLOW  пари `(module, name)`, які звичайні дані (set, bytes тощо) створюють самі
    SAFE_EXT / PICKLE_EXT  розширення (малим регістром), за якими файл вважається кандидатом
    DTYPE_SIZES    розмір елемента safetensors у байтах

`scan_pickle(data: bytes, allow=None) -> list[dict]`
    Знахідки `{"rule", "module", "name", "pos"}` (`pos` це зсув опкода в `data`), відсортовані
    за `(pos, rule)`. `allow` це множина пар `(module, name)`; `None` означає `DEFAULT_ALLOW`.
    Імена модулів нормалізуються: `__builtin__` це `builtins`, `copy_reg` це `copyreg`.
    Глобальні посилання беруться з опкодів `GLOBAL`, `INST` (аргумент `"module name"`) і
    `STACK_GLOBAL`. Для `STACK_GLOBAL` модуль і імʼя це ДВА останні опкоди-рядки
    (`SHORT_BINUNICODE`, `BINUNICODE`, `BINUNICODE8`, `UNICODE`) безпосередньо перед ним, а опкоди
    збереження в memo (`MEMOIZE`, `PUT`, `BINPUT`, `LONG_BINPUT`) при цьому ПРОПУСКАЮТЬСЯ. Memo
    НЕ відстежується (тому другий глобал з того самого модуля в протоколі 4, де рядок береться з memo,
    це `unresolved-global`: так задумано, fail closed).
    Правила:
    * `dangerous-global`: модуль з `DENY_MODULES` (за першою частиною) або `builtins` з імʼям з
      `DENY_BUILTINS`. Поля `module` і `name` заповнені (нормалізовані);
    * `unlisted-global`: не небезпечне, але пари немає в `allow` (allowlist, а не denylist:
      невідоме це відмова);
    * `unresolved-global`: `STACK_GLOBAL`, якого не вдалося розкласти (перед ним не два рядкові
      опкоди, наприклад `BINGET` з memo), або опкоди `EXT1`/`EXT2`/`EXT4`. `module` і `name` це `None`;
    * `trailing-data`: після першого `STOP` лишились байти (другий потік не скануємо). `pos` це
      позиція одразу після `STOP`, `module` і `name` це `None`;
    * `malformed`: `pickletools.genops` не зміг розібрати (порожні дані, обрізаний потік, немає
      `STOP`, сміття). Тоді результат це РІВНО один запис
      `{"rule": "malformed", "module": None, "name": None, "pos": -1}`.
    Безпечний pickle простих даних (dict, list, str, int, float, bool, None, tuple, set,
    frozenset, bytes, OrderedDict; протоколи 0..5) дає `[]`.

`is_safe(data, allow=None) -> bool`
    `True`, лише коли `scan_pickle` повертає порожній список.

`verify_hash(data: bytes, expected_sha256: str) -> bool`
    SHA-256 `data` збігається з `expected_sha256` (малі й великі hex-літери допустимі, пробіли
    по краях ігноруються). Порівняння за постійний час. Будь-яке інше значення `expected`
    (не рядок, не 64 hex-символи) це `False`, без винятків.

`check_safetensors(data: bytes) -> str | None`
    Перевірка формату БЕЗ зовнішніх бібліотек: 8 байтів little-endian `N`, далі `N` байтів
    JSON-заголовка, далі буфер тензорів. `None` означає «все гаразд», інакше ПЕРШИЙ код
    проблеми за порядком:
    * `"too-short"`: менше 8 байтів;
    * `"header-size"`: `N > 10_000_000` або `8 + N > len(data)`;
    * `"header-json"`: заголовок не UTF-8, не JSON або не обʼєкт;
    * `"metadata"`: `__metadata__` є, але це не обʼєкт із рядкових значень;
    * для кожного тензора (ключі, крім `__metadata__`, за зростанням імені), по черзі:
      `"tensor-spec"` (значення не обʼєкт; `dtype` не з `DTYPE_SIZES`; `shape` не список
      невідʼємних `int`, `bool` не `int`; `data_offsets` не список із двох невідʼємних `int`),
      `"offsets"` (`begin > end` або `end` більше за розмір буфера),
      `"size-mismatch"` (`end - begin` не дорівнює добутку `shape` на розмір елемента; порожній
      `shape` це скаляр, один елемент);
    * `"layout"`: тензори, відсортовані за `begin`, не лежать суцільно: перший починається не
      з 0, між сусідніми є проміжок чи перекриття, останній закінчується не в кінці буфера
      (без тензорів буфер має бути порожнім).

`choose_model_file(files: dict[str, bytes], manifest: dict[str, str]) -> dict`
    Обирає, який файл безпечно завантажувати. `files` це імена файлів репозиторію моделі й
    їхній вміст, `manifest` це очікувані SHA-256 (з доверенного джерела). Кандидати це файли з
    розширенням (за суфіксом імені, без урахування регістру) із `SAFE_EXT` або `PICKLE_EXT`;
    решта (`config.json`, `README.md`, `model.onnx`) ігноруються. Порядок перевірки: спершу
    `safetensors` за іменем, потім pickle-подібні за іменем. Для кожного кандидата, у такому
    порядку, перший збіг:
    * pickle-подібний при наявності ХОЧА Б ОДНОГО кандидата-safetensors (навіть відхиленого):
      `"safetensors-preferred"` (перевіряється ПЕРШИМ для pickle-подібних: без хешу й без сканування;
      до pickle в такому репозиторії не вертаємось: fail closed);
    * немає в `manifest`: відхилено, причина `"no-hash"`;
    * `verify_hash` хибне: `"hash-mismatch"`;
    * `safetensors` із проблемою `check_safetensors`: `"bad-safetensors"`;
    * pickle-подібний із непорожнім `scan_pickle`: `"unsafe-pickle"`;
    * інакше файл ПРИЙНЯТО й перевірка зупиняється.
    Результат: `{"file": імʼя | None, "format": "safetensors" | "pickle" | None, "rejected":
    [{"file", "reason"}, ...]}` (відхилені до моменту вибору, у порядку перевірки).
"""
import hashlib
import hmac
import io
import json
import pickletools

DENY_MODULES = frozenset({
    "os", "posix", "nt", "subprocess", "sys", "socket", "shutil", "pty", "importlib", "runpy", "ctypes",
    "multiprocessing", "operator", "functools", "code", "codeop", "pickle", "_pickle", "marshal", "types",
    "webbrowser", "urllib", "http", "ftplib", "smtplib", "telnetlib", "signal", "platform", "pdb", "timeit",
})
DENY_BUILTINS = frozenset({
    "eval", "exec", "compile", "__import__", "open", "getattr", "setattr", "delattr", "globals", "locals",
    "vars", "input", "breakpoint",
})
DEFAULT_ALLOW = frozenset({
    ("builtins", "set"), ("builtins", "frozenset"), ("builtins", "bytearray"), ("builtins", "complex"),
    ("_codecs", "encode"), ("collections", "OrderedDict"),
})
SAFE_EXT = (".safetensors",)
PICKLE_EXT = (".pkl", ".pickle", ".pt", ".pth", ".bin", ".ckpt")
DTYPE_SIZES = {"F64": 8, "F32": 4, "F16": 2, "BF16": 2, "I64": 8, "I32": 4, "I16": 2, "I8": 1, "U8": 1, "BOOL": 1}


def scan_pickle(data: bytes, allow=None) -> list[dict]:
    raise NotImplementedError


def is_safe(data: bytes, allow=None) -> bool:
    raise NotImplementedError


def verify_hash(data: bytes, expected_sha256: str) -> bool:
    raise NotImplementedError


def check_safetensors(data: bytes):
    raise NotImplementedError


def choose_model_file(files: dict, manifest: dict) -> dict:
    raise NotImplementedError
