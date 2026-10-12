"""Завдання №42: Вебхуки, що ми відправляємо.

Ми відправляємо події клієнтам на їхні URL. Приймач буває повільним, падає або
повертає 429. Зроби доставку надійною, перевірюваною і безпечною.

`deliver(event, url, secret, transport, *, clock, sleep, max_attempts=5, base_delay=1.0, max_delay=60.0, timeout=5.0)`
- `transport(url, body: bytes, headers: dict, timeout: float) -> Response` справжня відправка (у тестах мок);
  кидає `TimeoutError` або `ConnectionError`, коли відповіді немає; `Response` має `status` і `headers`;
- тіло: `json.dumps(event, separators=(",", ":"), sort_keys=True)` у UTF-8 (одні й ті самі байти на кожну спробу);
- заголовки КОЖНОЇ спроби: `Content-Type: application/json`, `X-Webhook-Id` (однаковий на всі спроби
  однієї події: приймач за ним дедуплікує; береться з `event["id"]`), `X-Webhook-Timestamp` (цілі секунди
  `clock()` НА МОМЕНТ цієї спроби), `X-Webhook-Signature: v1=<hex>` де hex це HMAC-SHA256(secret, f"{timestamp}.{body}");
- успіх: будь-який 2xx. Повторюємо: мережева помилка/таймаут, 408, 425, 429, 5xx. НЕ повторюємо: інші 4xx
  (приймач відхилив назавжди) і 3xx (редіректи не слідуємо);
- пауза перед наступною спробою: `min(max_delay, base_delay * 2**(attempt-1))` для спроби № attempt (1, 2, ...);
  але якщо відповідь має `Retry-After` (секунди), чекай `max(цю паузу, Retry-After)`, не більше `max_delay`;
  `sleep` не викликається після останньої спроби;
- повертає `DeliveryResult(status, attempts, log)`: `status` це "delivered" / "failed" (вичерпано спроби) /
  "rejected" (не повторюване 4xx/3xx); `log` це список `{"attempt": n, "at": clock(), "outcome": "<код>" або "error:<ТипПомилки>"}`
  у порядку спроб.
"""
import hashlib  # noqa: F401
import hmac  # noqa: F401
import json  # noqa: F401
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Response:
    status: int
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class DeliveryResult:
    status: str
    attempts: int
    log: list[dict[str, Any]]


def deliver(
    event: dict,
    url: str,
    secret: str,
    transport: Callable[..., Response],
    *,
    clock: Callable[[], float],
    sleep: Callable[[float], None],
    max_attempts: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    timeout: float = 5.0,
) -> DeliveryResult:
    raise NotImplementedError
