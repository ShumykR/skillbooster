"""Завдання №53: throttling входу (захист від перебору паролів).

Ліміт рахується на ключ (наприклад, `username` або `ip:username`). Годинник передається
параметром `clock`, тому тести детерміновані.

Поведінка:
- `check(key)` повертає `(allowed, retry_after)`: чи можна зараз пробувати вхід і скільки
  секунд лишилось до розблокування (0.0, якщо дозволено);
- `record_failure(key)`: невдала спроба. Коли за останні `window` секунд назбиралось
  `max_failures` невдач, ключ блокується на `lockout` секунд, а лічильник невдач обнуляється.
  Спроби в блокуванні (невдачі під час локауту) блокування НЕ подовжують;
- `record_success(key)`: успішний вхід скидає невдачі ключа. Якщо ключ заблокований,
  нічого не змінює: правильний пароль у локауті не розблоковує акаунт;
- невдачі старші за `window` секунд не враховуються; різні ключі незалежні.
"""
import time
from typing import Callable


class LoginThrottle:
    def __init__(
        self,
        max_failures: int = 5,
        window: float = 900.0,
        lockout: float = 900.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        raise NotImplementedError

    def check(self, key: str) -> tuple[bool, float]:
        raise NotImplementedError

    def record_failure(self, key: str) -> None:
        raise NotImplementedError

    def record_success(self, key: str) -> None:
        raise NotImplementedError
