"""Завдання №65: systemd: аудит unit-файлу сервісу.

`audit_unit(text)` повертає відсортований список унікальних кодів порушень для unit-файлу `.service`.
Розбір файлу вже зроблено: `parse_unit(text)` дає {секція: [(ключ, значення), ...]} у порядку появи
(коментарі `#`/`;` прибрано, рядки з `\\` в кінці склеєно, ключі можуть повторюватись, наприклад `Environment=`).
Секції, яких немає у файлі, це порожні списки. Значення `Type`, `Restart` порівнюй без урахування регістру.

Правила (секція [Service], якщо не сказано інше; «немає» означає, що ключа немає або його значення порожнє):
- SD001  Restart відсутній або `no`, коли Type не `oneshot` (сервіс не піднімається після збою);
- SD002  Restart задано (не `no`), але RestartSec немає (типово 100 мс: безперервне гамселення при збої);
- SD003  немає `User=` і немає `DynamicUser=yes`, або `User=` це `root`/`0` (сервіс працює від root);
- SD004  немає `NoNewPrivileges=yes` (також `true`/`1`/`on`);
- SD005  `ProtectSystem` не `yes`/`true`/`1`/`full`/`strict`;
- SD006  будь-який `ExecStart=` не починається зі шляху, що стартує з `/` (після необовʼязкових префіксів
         `@`, `-`, `:`, `+`, `!`); `systemd` не шукає виконувані файли в PATH;
- SD007  у [Unit] є `Wants=network-online.target` (або `Requires=`), але `After=` не містить `network-online.target`
         (Wants без After не впорядковує запуск; значення в Wants/After можуть бути списком через пробіл);
- SD008  `Environment=` містить присвоєння, імʼя якого має `PASSWORD`, `SECRET`, `TOKEN` або `KEY` (без урахування регістру)
         з непорожнім значенням, що не починається з `%` чи `$`: секрети тримають в `EnvironmentFile=` з правами 600
         (в одному `Environment=` може бути кілька присвоєнь через пробіл, у лапках теж: `shlex.split`);
- SD009  [Install] не містить `WantedBy=` або `RequiredBy=` (сервіс неможливо `enable`);
- SD010  Type=forking без `PIDFile=`;
- SD011  немає жодного з `MemoryMax=`, `MemoryHigh=` (один сервіс з витоком може з'їсти всю памʼять хоста).
"""
import shlex  # noqa: F401 (знадобиться для SD008)


def parse_unit(text: str) -> dict[str, list[tuple[str, str]]]:
    sections: dict[str, list[tuple[str, str]]] = {"Unit": [], "Service": [], "Install": []}
    current = None
    joined: list[str] = []
    buf = ""
    for raw in text.splitlines():
        line = raw.strip()
        if buf:
            line = buf + " " + line
            buf = ""
        if line.endswith("\\"):
            buf = line[:-1].rstrip()
            continue
        joined.append(line)
    if buf:
        joined.append(buf)
    for line in joined:
        if not line or line[0] in "#;":
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1]
            sections.setdefault(current, [])
            continue
        if current is not None and "=" in line:
            key, value = line.split("=", 1)
            sections[current].append((key.strip(), value.strip()))
    return sections


def audit_unit(text: str) -> list[str]:
    raise NotImplementedError
