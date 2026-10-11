"""Завдання №143: CSRF-захист і безпека cookie.

Якщо сесія живе в cookie, браузер сам додає її до КОЖНОГО запиту на наш сайт, навіть коли
запит ініціює чужа сторінка (`<form action="https://bank.example/transfer" method=POST>`).
Це CSRF (CWE-352, №3 у MITRE CWE Top 25). Захист складається з кількох шарів.

1. `audit_set_cookie(header) -> list[str]`
   Приймає значення заголовка `Set-Cookie` (`"sid=abc; Path=/; Secure; HttpOnly"`) і повертає
   ВІДСОРТОВАНИЙ список кодів проблем. Імена атрибутів нечутливі до регістру, пробіли навколо
   `;` ігноруються. Значення без `name=value` на початку це `ValueError`.
   * `missing_secure`        немає `Secure` (cookie піде по http);
   * `missing_httponly`      немає `HttpOnly` (JavaScript, а отже й XSS, бачить cookie);
   * `missing_samesite`      немає `SameSite` або значення не з {Lax, Strict, None};
   * `samesite_none_insecure` `SameSite=None` без `Secure` (браузер такий cookie відкине);
   * `broad_domain`          задано атрибут `Domain` (cookie піде на всі піддомени);
   * `long_lived`            `Max-Age` більший за 30 днів (2592000 с); нечисловий ігноруємо;
   * `bad_host_prefix`       ім'я з префіксом `__Host-`, але немає `Secure`, або `Path` не
                             дорівнює `/`, або заданий `Domain`;
   * `bad_secure_prefix`     ім'я з префіксом `__Secure-`, але немає `Secure`.

2. `CsrfGuard(secret: bytes, allowed_origins, clock=time.time, max_age=3600)`
   * `issue(session_id) -> str`: токен виду `"<ts>.<hex>"`, де `ts` це ціле число секунд за
     `clock()`, а `hex` це HMAC-SHA256(secret, f"{session_id}|{ts}"). Токен прив'язаний до
     сесії: токен зловмисника не підходить до сесії жертви;
   * `check(method, headers, session_id, token) -> bool`:
       - методи GET, HEAD, OPTIONS (без урахування регістру) безпечні: `True` без перевірок
         (звідси правило: GET ніколи не змінює стан);
       - для решти методів усе нижче має виконуватись, інакше `False`:
         a) `session_id` і `token` непорожні, `token` це рядок формату `<цифри>.<hex>`;
         b) заголовок `Origin` (імена заголовків нечутливі до регістру) входить у
            `allowed_origins`; якщо `Origin` немає, береться схема+хост (+порт) із `Referer`;
            якщо немає жодного з двох, або `Origin: null`, це `False`;
         c) вік токена `clock() - ts` не від'ємний і не більший за `max_age`;
         d) підпис збігається; порівнюй через `hmac.compare_digest` (стала за часом дія).
     Метод не повинен піднімати виняток на сміттєвих токенах.
"""
import hashlib
import hmac  # не прибирай: тест перевіряє constant-time порівняння
import time
from typing import Callable, Collection, Mapping


def audit_set_cookie(header: str) -> list[str]:
    raise NotImplementedError


class CsrfGuard:
    def __init__(
        self,
        secret: bytes,
        allowed_origins: Collection[str],
        clock: Callable[[], float] = time.time,
        max_age: int = 3600,
    ):
        raise NotImplementedError

    def issue(self, session_id: str) -> str:
        raise NotImplementedError

    def check(self, method: str, headers: Mapping[str, str], session_id: str, token: str | None) -> bool:
        raise NotImplementedError
