"""Завдання №41: Перевірка підпису вебхука.

Формат заголовка (як у Stripe):  t=1700000000,v1=<hex>[,v1=<hex>...]
Підпис = HMAC-SHA256(secret, f"{t}." + payload), у hex.
"""
import hashlib
import hmac  # не прибирай: тест перевіряє constant-time порівняння


class WebhookError(Exception):
    pass


class InvalidSignature(WebhookError):
    pass


class ExpiredTimestamp(WebhookError):
    pass


class ReplayedEvent(WebhookError):
    pass


def verify_webhook(
    payload: bytes,
    signature_header: str,
    secret: str,
    *,
    now: float,
    tolerance: int = 300,
    seen: set | None = None,
) -> None:
    """Нічого не повертає, якщо все гаразд; інакше кидає підклас WebhookError."""
    raise NotImplementedError
