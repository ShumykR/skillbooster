"""Завдання №101: структуровані JSON-логи з correlation id.

Логи, які читає людина, не масштабуються: у проді їх читає машина (Loki, CloudWatch, ELK), і кожен рядок має бути одним JSON-обʼєктом,
який можна відфільтрувати за `correlation_id` через усі сервіси.

correlation_id: ContextVar[str | None]    значення за замовчуванням None.
bind_correlation_id(value)                контекстний менеджер: на час блоку correlation_id.get() == value, після виходу значення
                                          відновлюється (також після винятку).
extract_correlation_id(headers, generate) -> str
    `headers`: dict {імʼя: значення}; імʼя заголовка X-Request-ID порівнюється без урахування регістру. Якщо значення є і відповідає
    ^[A-Za-z0-9._-]{8,64}$ (довжина 8..64 без пробілів, переносів рядків та інших символів), повертає його. Інакше
    (немає, порожнє, задовге, зі сміттям) повертає generate(): значення чужого заголовка не можна довіряти (інʼєкція в лог).

JsonFormatter(service)                    logging.Formatter. format(record) -> один рядок JSON (без переносів рядка всередині) з ключами:
    "ts"      UTC-час із record.created у форматі YYYY-MM-DDTHH:MM:SS.mmmZ, де mmm = int((created - int(created)) * 1000);
    "level"   record.levelname;  "service"   імʼя сервісу;  "logger"   record.name;  "message"   record.getMessage();
    "correlation_id"   поточне значення correlation_id, ключ ЛИШЕ коли воно не None;
    додаткові поля, передані через `extra={...}` (усе, чого немає в стандартних атрибутах LogRecord), у тому самому рівні;
    "exc"     лише якщо є exc_info: {"type": імʼя класу, "message": str(виняток), "stack": відформатований traceback рядком}.
    Ключі, чиє імʼя (без урахування регістру) містить одне з: password, token, secret, authorization, api_key, apikey, cookie,
    отримують значення "***" (також усередині вкладених словників). Значення, що не серіалізуються в JSON, записуються як str(...).
    Кирилиця лишається читабельною (ensure_ascii=False). Додаткові поля не можуть перезаписати ключі ts/level/service/logger/message
    /correlation_id: у разі конфлікту діє стандартне значення.

CorrelationMiddleware(app, generate)      ASGI-middleware для http-запитів (інші типи scope пропускає без змін):
    бере id із заголовка x-request-id (extract_correlation_id), виставляє його на час обробки запиту (скидання в finally), а у відповідь
    (повідомлення http.response.start) додає заголовок (b"x-request-id", id), замінюючи наявний із тим самим іменем.
"""

import contextvars
import logging
from contextlib import contextmanager

correlation_id: contextvars.ContextVar = contextvars.ContextVar("correlation_id", default=None)


@contextmanager
def bind_correlation_id(value):
    raise NotImplementedError
    yield


def extract_correlation_id(headers: dict, generate) -> str:
    raise NotImplementedError


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str) -> None:
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        raise NotImplementedError


class CorrelationMiddleware:
    def __init__(self, app, generate) -> None:
        self.app = app
        self.generate = generate

    async def __call__(self, scope, receive, send):
        raise NotImplementedError
