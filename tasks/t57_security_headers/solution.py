"""Завдання №57: перевірка заголовків безпеки відповіді.

`check_headers(headers)` приймає словник заголовків відповіді (імена нечутливі до регістру) і
повертає відсортований список кодів проблем.

Правила:
- `hsts`             `Strict-Transport-Security` відсутній або `max-age` менший за 15552000
                     (180 днів);
- `csp_missing`      немає `Content-Security-Policy`;
- `csp_weak`         CSP є, але ефективна політика скриптів слабка. Ефективна = директива
                     `script-src`, а якщо її немає, то `default-src`. Слабка: її немає взагалі,
                     або вона містить `'unsafe-inline'`, `'unsafe-eval'` чи `*`;
- `nosniff`          `X-Content-Type-Options` не дорівнює `nosniff`;
- `framing`          немає захисту від iframe: `X-Frame-Options` не DENY/SAMEORIGIN і CSP не
                     містить директиви `frame-ancestors`;
- `referrer_policy`  немає `Referrer-Policy`;
- `cors_wildcard`    `Access-Control-Allow-Origin` дорівнює `*` або `null`;
- `version_leak`     `Server` або `X-Powered-By` містять цифру (версію ПЗ).

Директиви CSP розділені `;`, джерела пробілами, імена директив нечутливі до регістру.
"""


def check_headers(headers: dict[str, str]) -> list[str]:
    raise NotImplementedError
