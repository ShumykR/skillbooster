"""Завдання №89: Secrets Manager / Parameter Store замість змінних у коді: клієнт секретів.

Прибрати пароль із коду мало: треба ще не викликати Secrets Manager на кожен запит (затримка, гроші, ліміти API), пережити його
короткий збій, не зламатись під час ротації пароля й не надрукувати секрет у лозі. Реалізуй клієнт, який це робить.

fetch(name, stage) -> str    обгортка над GetSecretValue (у тестах мок); stage це "AWSCURRENT" або "AWSPREVIOUS". Кидає
    SecretNotFound, якщо секрету чи стадії немає, TemporaryError при збої/тротлінгу.

SecretsClient(fetch, *, clock, ttl=300, max_stale=3600, jitter=None)
    .get(name) -> str
        * кеш за імʼям: значення, отримане менше ніж `ttl'` секунд тому, віддається без звернення до fetch, де
          ttl' = jitter(ttl), якщо jitter задано (розкид, щоб тисяча інстансів не оновлювались одночасно), інакше ttl.
          ttl' обчислюється ОДИН раз при отриманні значення; кеш діє, поки `clock() - fetched_at < ttl'`;
        * промах або протермінований запис: fetch(name, "AWSCURRENT");
        * TemporaryError при оновленні: якщо є протермінований запис, віддати його, поки він молодший за `max_stale`
          секунд від fetched_at (stale-if-error); інакше кинути TemporaryError;
        * SecretNotFound ніколи не кешується й не ховається (кидається далі), запис у кеші для цього імені видаляється;
    .invalidate(name=None): забути одне імʼя або весь кеш;
    .call_with_secret(name, use) -> результат use(...)
        value = get(name); спробувати use(value). Якщо use кинув AuthError (облікові дані відхилено, типово після ротації):
        1. invalidate(name), завантажити свіжий AWSCURRENT; якщо він ВІДРІЗНЯЄТЬСЯ від використаного, повторити use(new)
           один раз (результат або помилка цього повтору остаточні) і закешувати new;
        2. якщо AWSCURRENT той самий (ротація ще не завершилась на боці бази), спробувати use(fetch(name, "AWSPREVIOUS")) один раз;
           якщо успішно, повернути результат (у кеші лишається свіже AWSCURRENT); якщо знову AuthError або AWSPREVIOUS
           немає (SecretNotFound), кинути AuthError (початковий).
        Будь-який інший виняток з use іде нагору без повторів.
    .fetch_count: скільки разів викликався fetch (усього).
    repr(client) / str(client) НЕ повинні містити жодного значення секрету.
"""


class SecretNotFound(Exception):
    pass


class TemporaryError(Exception):
    pass


class AuthError(Exception):
    pass


class SecretsClient:
    fetch_count: int = 0

    def __init__(self, fetch, *, clock, ttl: float = 300, max_stale: float = 3600, jitter=None) -> None:
        raise NotImplementedError

    def get(self, name: str) -> str:
        raise NotImplementedError

    def invalidate(self, name: str | None = None) -> None:
        raise NotImplementedError

    def call_with_secret(self, name: str, use):
        raise NotImplementedError
