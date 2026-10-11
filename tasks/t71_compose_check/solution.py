"""Завдання №71: перевірка docker-compose.yml.

`check_compose(text)` приймає YAML і повертає відсортований список унікальних рядків
`правило:обʼєкт`.

Правила:
- `unpinned_image:<сервіс>`  `image` без тегу або з `:latest` (digest `@sha256:` та
                             змінні `${...}` не рахуються порушенням);
- `exposed_db:<сервіс>`      образ postgres/redis/mysql/mariadb/mongo (ім'я без реєстру
                             й тегу) публікує `ports` на хост: БД має бути доступна лише
                             з мережі compose;
- `hardcoded_secret:<сервіс>` змінна середовища, чиє ім'я містить PASSWORD, SECRET, TOKEN
                             або KEY, має літеральне непорожнє значення (не `${VAR}` і не
                             без значення). Імена, що закінчуються на `_FILE`, дозволені;
- `missing_healthcheck:<dep>` сервіс є залежністю (`depends_on`) для іншого, але не має
                             `healthcheck` (або має `healthcheck: {disable: true}`);
- `not_waiting:<сервіс>-><dep>` залежність має healthcheck, але сервіс не чекає на неї
                             через `condition: service_healthy`.

`depends_on` буває списком (тоді умова service_started) або мапою з `condition`.
`environment` буває мапою або списком рядків `KEY=value`.
"""


def check_compose(text: str) -> list[str]:
    raise NotImplementedError
