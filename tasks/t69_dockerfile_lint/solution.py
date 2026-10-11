"""Завдання №69: мінімальний лінтер Dockerfile.

Повертає відсортований список унікальних кодів порушених правил.

Правила:
- DF001  базовий образ без тегу або з `:latest` (digest `@sha256:...`, `scratch`,
         посилання на попередню стадію й змінні `$ARG` не рахуються порушенням);
- DF002  ОСТАННЯ стадія працює від root: немає `USER` або останній `USER` це root/0
         (`USER 1000:1000` та `USER app` нормально);
- DF003  `ADD` для локальних файлів (дозволено лише URL та архіви .tar/.tgz/.tar.*,
         які `ADD` розпаковує сам): для решти використовуй `COPY`;
- DF004  `apt-get install`/`apt install` без `--no-install-recommends`;
- DF005  `apt-get install`/`apt install` без `rm -rf /var/lib/apt/lists` у ТІЙ САМІЙ `RUN`
         (інакше кеш лишається в шарі);
- DF006  `pip install` без `--no-cache-dir`;
- DF007  у межах стадії `COPY . ...` (весь контекст) стоїть РАНІШЕ за `RUN pip install -r ...`:
         кожна правка коду інвалідує кеш шару із залежностями.
"""


def lint_dockerfile(text: str) -> list[str]:
    raise NotImplementedError
