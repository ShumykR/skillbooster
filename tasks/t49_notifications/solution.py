"""Завдання №49: Листи й сповіщення: шаблони, черга, відписка, bounce.

Реалізуй `NotificationService`. SMTP/API провайдера це `transport(message)`: у тестах мок, що кидає
`TemporaryFailure` (4xx/«спробуй пізніше») або `PermanentFailure` (5xx/«адреси не існує»).

Види листів: "transactional" (скидання пароля, чек) і "marketing" (розсилки).

enqueue(to, kind, subject, html, text, context, dedupe_key=None) -> bool
  * адреса: обрізати пробіли, привести до нижнього регістру; без "@" або з \\r чи \\n -> ValueError
    (інʼєкція заголовків); невідомий `kind` -> ValueError;
  * шаблони: `{{ name }}` (пробіли всередині довільні) береться з `context`; невідома змінна -> TemplateError
    одразу при постановці; у `html` значення екрануються (`html.escape(..., quote=True)`), у `text` ні;
    у `subject` кожен \\r і \\n у значенні замінюється пробілом (інакше це інʼєкція заголовків);
  * повертає False і нічого не ставить у чергу, якщо адреса придушена для цього виду (див. нижче) або
    пара (адреса, dedupe_key) уже ставилась у чергу раніше; інакше True;
  * marketing: заголовки `List-Unsubscribe: <URL>` та `List-Unsubscribe-Post: List-Unsubscribe=One-Click`;
    наприкінці `text` додається "\\n\\n--\\nUnsubscribe: URL", наприкінці `html` додається
    `<p><a href="URL">Unsubscribe</a></p>` (URL екранований для html). Для transactional цього немає.
unsubscribe_url(email, kind) -> str: f"{base_url}/unsubscribe?token=<token>", токен =
  base64url(без "=")(f"{email}|{kind}") + "." + перші 32 hex-символи HMAC-SHA256(secret, f"{email}|{kind}").
unsubscribe(token): перевіряє підпис (сталий час), потім забороняє marketing для цієї адреси;
  підроблений/зіпсований токен або токен не для marketing -> InvalidToken; повторний виклик безпечний.
record_bounce(email, kind): kind "hard" придушує адресу для УСІХ видів, "complaint" лише для marketing,
  "soft" нічого не придушує.
is_suppressed(email, kind) -> bool.
process() -> int: обробляє повідомлення, у яких `not_before <= clock()`, у порядку постановки; повертає кількість
  звернень до transport. Для кожного: якщо адресу вже придушено для цього виду (відписався після постановки)
  - повідомлення тихо відкидається без звернення до transport; успіх - прибрати з черги;
  TemporaryFailure - спроба n (1, 2, ...): якщо n >= max_attempts, повідомлення йде в `dead_letters`, інакше
  повертається в чергу з `not_before = clock() + retry_delay * 2**(n-1)`; PermanentFailure - адреса придушується
  для всіх видів, повідомлення відкидається.
pending() -> int: скільки повідомлень у черзі (включно з тими, що чекають повтору).
"""
import base64  # noqa: F401
import hashlib  # noqa: F401
import hmac  # noqa: F401
import html as htmllib  # noqa: F401
import re  # noqa: F401
from dataclasses import dataclass, field
from typing import Callable

KINDS = ("transactional", "marketing")


class TemplateError(Exception):
    pass


class InvalidToken(Exception):
    pass


class TemporaryFailure(Exception):
    pass


class PermanentFailure(Exception):
    pass


@dataclass
class Message:
    to: str
    kind: str
    subject: str
    html: str
    text: str
    headers: dict[str, str] = field(default_factory=dict)
    attempts: int = 0
    not_before: float = 0.0


class NotificationService:
    def __init__(
        self,
        transport: Callable[[Message], None],
        secret: str,
        base_url: str,
        clock: Callable[[], float],
        max_attempts: int = 3,
        retry_delay: float = 60.0,
    ) -> None:
        self.dead_letters: list[Message] = []
        raise NotImplementedError

    def enqueue(self, to: str, kind: str, subject: str, html: str, text: str, context: dict, dedupe_key: str | None = None) -> bool:
        raise NotImplementedError

    def unsubscribe_url(self, email: str, kind: str = "marketing") -> str:
        raise NotImplementedError

    def unsubscribe(self, token: str) -> None:
        raise NotImplementedError

    def record_bounce(self, email: str, kind: str) -> None:
        raise NotImplementedError

    def is_suppressed(self, email: str, kind: str) -> bool:
        raise NotImplementedError

    def process(self) -> int:
        raise NotImplementedError

    def pending(self) -> int:
        raise NotImplementedError
