"""Завдання №56: мінімальний SAST-сканер Python-коду на модулі `ast` (ідея bandit/semgrep).

`scan_python(source)` розбирає код (НЕ виконує його!) і повертає відсортований список
унікальних пар `(номер_рядка, правило)`. Номер рядка це `lineno` виклику (для виклику на
кількох рядках початковий). Синтаксична помилка в коді це `ValueError`.

Правила (спрацьовують на ВИКЛИКАХ):
- PY001  вбудовані `eval(...)` і `exec(...)`;
- PY002  виконання команд оболонкою: `os.system(...)` завжди; `subprocess.run/call/Popen/
         check_call/check_output(..., shell=True)` (лише коли `shell=True` явно);
- PY003  небезпечна десеріалізація: `pickle.load/loads`; `yaml.load(...)`, якщо не задано
         безпечний завантажувач (`Loader=yaml.SafeLoader`, `yaml.CSafeLoader` чи
         `yaml.BaseLoader`, ключовим або другим позиційним аргументом);
- PY004  вимкнена перевірка TLS: виклик `requests.*` або `httpx.*` з `verify=False`;
- PY005  слабкі хеші `hashlib.md5/sha1`, якщо не передано `usedforsecurity=False`;
- PY006  SQL з динамічного рядка: першим аргументом `.execute(...)`/`.executemany(...)`
         (будь-якого обʼєкта) передано f-рядок, конкатенацію/форматування `+` чи `%`, або
         `"...".format(...)`. Параметризований запит `execute("... ?", (x,))` це норма;
- PY007  `tempfile.mktemp(...)` (гонка створення файлу).

Вимоги до розбору:
- імена модулів можуть бути перейменовані: `import subprocess as sp`, `from subprocess import
  run`, `from os import system as sh` мають розпізнаватись;
- рядок із коментарем `# nosec` пропускається повністю (як у bandit);
- рядки й коментарі, що ЗГАДУЮТЬ `eval(` чи `os.system(`, знахідок не дають (це не виклики).
"""


def scan_python(source: str) -> list[tuple[int, str]]:
    raise NotImplementedError
