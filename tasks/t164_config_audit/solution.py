"""Завдання №164: аудит конфігурації застосунку за середовищем (CWE-489 Active Debug Code, A02 Security Misconfiguration).

У production лишається `debug=True`, відкритий `/docs`, `CORS: *` і ключ `changeme`. Це не помилки коду, а помилки
конфігурації, тож їх ловить перевірка налаштувань у CI/на старті застосунку, до того як сервіс почне приймати трафік.

`audit_settings(env, settings) -> list[str]`
    `env`: "prod"/"production"/"staging" (суворі правила) або "dev"/"development"/"local"/"test" (там усе дозволено, результат
    порожній). Регістр і пробіли по краях неважливі; будь-яке інше значення: ValueError. `settings` не dict: TypeError.
    Повертає відсортований список ІДЕНТИФІКАТОРІВ порушених правил (без дублікатів). Невідомі ключі ігноруються.

    Значення з змінних оточення приходять РЯДКАМИ, тому "булеве" значення розбирається так: True/ненульове число або рядок, що
    (без урахування регістру й пробілів) не входить до {"", "0", "false", "no", "off", "none", "null"}; None, False, 0 це хиба.

    Правила для prod/staging:
    CFG001  `debug` істинне.
    CFG002  відкрита документація: `docs_url`, `redoc_url` або `openapi_url` істинні (у FastAPI їх вимикають значенням None).
    CFG003  `cors_allow_origins` містить `"*"` або `"null"` (без урахування регістру).
    CFG004  `allowed_hosts` відсутній, порожній, не список/кортеж або містить `"*"`.
    CFG005  `secret_key` відсутній, не рядок, коротший за 32 символи, входить до `WEAK_SECRETS` (без урахування регістру й пробілів)
            або містить 4 і менше різних символів (`"a" * 40`).
    CFG006  cookie сесії: `session_cookie_secure` або `session_cookie_httponly` відсутні чи хибні, або `session_cookie_samesite`
            відсутній чи дорівнює "none" (без урахування регістру). Дозволені "lax" та "strict".
    CFG007  `database_url`: у ньому `sslmode=disable` або пароль збігається з іменем користувача чи входить до `WEAK_DB_PASSWORDS`
            (розбирай URL через `urllib.parse`, пароль із percent-кодуванням треба декодувати). Відсутній `database_url` це не порушення.
    CFG008  `show_error_details` істинне (трасування стеку в відповідях).
    CFG009  `log_level` дорівнює "debug" або "trace" (без урахування регістру).
    CFG010  `public_url` починається з `http://` (без урахування регістру); відсутній не порушення.
"""

WEAK_SECRETS = frozenset({
    "changeme", "change-me", "secret", "secretkey", "secret-key", "your-secret-key", "dev", "development", "default",
    "password", "supersecret", "super-secret", "test", "insecure", "please-change-me",
})
WEAK_DB_PASSWORDS = frozenset({"postgres", "password", "root", "admin", "123456", "changeme", "secret", "test"})
STRICT_ENVS = frozenset({"prod", "production", "staging"})
LAX_ENVS = frozenset({"dev", "development", "local", "test"})


def audit_settings(env: str, settings: dict) -> list[str]:
    raise NotImplementedError
