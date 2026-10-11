"""Завдання №51: Перевірка JWT (HS256).

Реалізуй verify власноруч, щоб зрозуміти, де ламаються справжні системи.
У production використовуй перевірену бібліотеку (PyJWT, Authlib), але вимоги ті самі.

Токен: base64url(header).base64url(payload).base64url(signature),
signature = HMAC-SHA256(secret, "header.payload").
"""
import base64
import hashlib
import hmac  # не прибирай: тест перевіряє constant-time порівняння
import json


class InvalidToken(Exception):
    pass


def verify(
    token: str,
    secret: str,
    *,
    now: float,
    audience: str | None = None,
    leeway: float = 0,
) -> dict:
    """Повертає claims, якщо токен валідний; інакше InvalidToken (і лише її).

    Правила:
    - рівно 3 частини; будь-яка помилка декодування/JSON це InvalidToken;
    - header.alg має бути рівно "HS256" (відхиляй "none", "HS512", "RS256", будь-що інше);
    - підпис правильний (порівняння у постійний час);
    - claim `exp` ОБОВʼЯЗКОВИЙ і число; токен прострочений, якщо now > exp + leeway;
    - якщо є `nbf`, токен ще не дійсний, якщо now < nbf - leeway;
    - якщо передано audience, claim `aud` (рядок або список) має його містити.
    """
    raise NotImplementedError
