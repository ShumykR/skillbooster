"""Завдання №7: єдиний формат помилок API за RFC 7807 («Problem Details»).

`install_error_handlers(app)` реєструє у FastAPI-застосунку обробники, після яких КОЖНА
помилка виглядає однаково: тіло JSON і заголовок `Content-Type: application/problem+json`.

Поля відповіді: `type` (за замовчуванням "about:blank"), `title`, `status` (дорівнює
HTTP-статусу), `detail`, `instance` (шлях запиту, `request.url.path`).

Що обробити:
- `HTTPException` (і 404/405 від самого роутера): `title` це стандартна фраза статусу
  ("Not Found", "Forbidden", ...), `detail` це `exc.detail` (як рядок). Заголовки, задані в
  `HTTPException(headers=...)`, мають лишитись у відповіді;
- помилки валідації тіла/параметрів (`RequestValidationError`): статус 422,
  `title` = "Validation Error", `detail` = "Request validation failed" і додаткове поле
  `errors`: список `{"loc": [...], "msg": "..."}` ТІЛЬКИ з цими двома ключами (без `input`,
  `ctx`, `url` та іншого, щоб не відбивати назад чутливі дані клієнта);
- `AppError` (доменна помилка нижче): статус, `title`, `detail` і `type` беруться з неї;
- будь-який інший виняток: статус 500, `title` = "Internal Server Error",
  `detail` = "An unexpected error occurred". Текст винятку й трасування в тілі НЕ показувати
  (там можуть бути паролі, SQL, шляхи).
"""
from fastapi import FastAPI


class AppError(Exception):
    """Доменна помилка: кидай її з бізнес-логіки, не знаючи про HTTP-формат."""

    def __init__(self, status: int, title: str, detail: str | None = None, type: str = "about:blank"):
        super().__init__(title)
        self.status = status
        self.title = title
        self.detail = detail
        self.type = type


def install_error_handlers(app: FastAPI) -> None:
    raise NotImplementedError
