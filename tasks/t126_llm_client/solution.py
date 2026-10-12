"""Завдання №126: Перший виклик LLM: запит, streaming (SSE), класифікація помилок, таймаути та ретраї.

Мережі в завданні немає: HTTP-шар (`transport`) і сон (`sleep`) передаються параметрами, у тестах це підробки.
Формат як у OpenAI-сумісних API (/v1/chat/completions), тож твій код працюватиме з проксі з CLAUDE.md.

Помилки (усі наслідують LLMError; атрибут `retryable`):
    AuthError(retryable False), BadRequest(False), RateLimited(True, поле retry_after: float | None), ServerError(True),
    Timeout(True), StreamError(False; зіпсований чанк, подія error у потоці, обрив потоку), BadResponse(False; відповідь 2xx без тексту).

build_request(model, user, *, system=None, max_tokens=512, temperature=0.2, stream=False) -> dict
    {"model", "messages": [{"role": "system", "content": system} (лише якщо system не None), {"role": "user", "content": user}],
     "max_tokens", "temperature"} і, якщо stream, ще "stream": True та "stream_options": {"include_usage": True}.
    Порожній (після strip) user, max_tokens < 1, temperature поза [0, 2], model порожня: ValueError.

classify_response(status, headers, body) -> None
    Для статусу 2xx нічого не робить. Інакше кидає: 401/403 AuthError, 429 RateLimited, 400/404/413/422 BadRequest, 5xx ServerError,
    інші коди BadRequest. Текст помилки: body["error"]["message"], якщо body це словник із таким полем, інакше str(body)[:200].
    RateLimited.retry_after береться із заголовка Retry-After (імʼя без урахування регістру), якщо це невід'ємне число секунд; інакше None.

iter_sse_events(lines) -> Iterator[str]
    lines це ітератор рядків потоку (без \n). Подія завершується порожнім рядком; рядки "data:" збираються (один пробіл після двокрапки
    відкидається) і зʼєднуються через "\n". Рядки-коментарі (починаються з ":") та інші поля (event:, id:, retry:) ігноруються.
    Подія без data не віддається. Остання подія без завершального порожнього рядка теж віддається.

stream_text(lines) -> Iterator[str]
    Віддає шматки тексту з потоку чанків. Подія "[DONE]" завершує потік. Інакше подія це JSON: якщо є ключ "error", кидає StreamError;
    не JSON або не словник: StreamError. Текст: choices[0].delta.content, віддається, якщо це непорожній рядок (порожні й відсутні
    пропускаються; чанк без choices, напр. з usage, пропускається). Потік вважається завершеним, коли отримано [DONE] або чанк із
    непорожнім finish_reason; якщо ітератор закінчився без цього, StreamError("interrupted") (текст, що вже віддано, лишається у споживача).

complete(transport, request, *, max_retries=2, base_delay=1.0, max_wait=30.0, timeout=30.0, sleep=time.sleep) -> dict
    transport(request, timeout) -> (status, headers, body) або кидає TimeoutError. Спроб не більше 1 + max_retries.
    TimeoutError перетворюється на Timeout. Помилки classify_response: нелетючі (retryable False) летять одразу. Летючі: якщо спроби
    лишились, sleep(затримка) і нова спроба, де затримка = retry_after (для RateLimited, якщо він є), інакше base_delay * 2 ** (спроба - 1)
    (спроба рахується з 1). Якщо retry_after > max_wait, чекати не варто: помилка летить одразу. Після останньої спроби летить остання помилка.
    Успіх: body["choices"][0]["message"]["content"] має бути непорожнім рядком, інакше BadResponse.
    Результат {"text", "usage": body.get("usage", {}), "attempts": кількість спроб}.
"""

import time


class LLMError(Exception):
    retryable = False


class AuthError(LLMError):
    pass


class BadRequest(LLMError):
    pass


class RateLimited(LLMError):
    retryable = True

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ServerError(LLMError):
    retryable = True


class Timeout(LLMError):
    retryable = True


class StreamError(LLMError):
    pass


class BadResponse(LLMError):
    pass


def build_request(model: str, user: str, *, system: str | None = None, max_tokens: int = 512, temperature: float = 0.2,
                  stream: bool = False) -> dict:
    raise NotImplementedError


def classify_response(status: int, headers: dict, body) -> None:
    raise NotImplementedError


def iter_sse_events(lines):
    raise NotImplementedError


def stream_text(lines):
    raise NotImplementedError


def complete(transport, request: dict, *, max_retries: int = 2, base_delay: float = 1.0, max_wait: float = 30.0, timeout: float = 30.0,
             sleep=time.sleep) -> dict:
    raise NotImplementedError
