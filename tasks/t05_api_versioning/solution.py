"""Завдання №5: Валідація та контракти, версіонування API.

Сервіс користувачів досі має один ендпоінт `/users`, де телефон це рядок.
Мобільний застосунок v1 уже в сторах, і оновити його не можна. Для нового
вебклієнта телефон має бути структурою. Зроби два контракти над ОДНИМ сховищем.

POST /v1/users  {"name": str, "phone": "+380501234567", ...будь-які зайві поля ігноруються}
  -> 201 {"id": int, "name": str, "phone": "+380501234567"}
POST /v2/users  {"name": str, "phone": {"country_code": "+380", "number": "501234567"}}
  -> 201 {"id": int, "name": str, "phone": {"country_code": "+380", "number": "501234567"}}
GET  /v1/users/{id}, GET /v2/users/{id}: той самий користувач у форматі своєї версії
  (створений через v1 читається через v2 і навпаки); немає -> 404.

Правила:
- name: 1..50 символів після обрізання пробілів;
- v2 сувора: зайві поля -> 422, `country_code` виду "+<1-3 цифри>", `number` лише 4..12 цифр;
- v1 терпима до зайвих полів (старі клієнти), але телефон перевіряється: "+<код><номер>", де код один із
  KNOWN_CODES (рядок однозначно ділиться на код і номер; номер 4..12 цифр), інакше 422;
- кожна відповідь v1 має заголовок `Deprecation: true` і `Sunset` (дата виведення з експлуатації).
"""
from fastapi import FastAPI
from pydantic import BaseModel

KNOWN_CODES = ("+380", "+44", "+49", "+1")  # код країни v1-телефону має починатися з одного з них


class UserIn(BaseModel):
    name: str
    phone: str


def create_app() -> FastAPI:
    app = FastAPI()
    users: dict[int, dict] = {}

    @app.post("/users", status_code=201)
    def create_user(payload: UserIn):
        user = {"id": len(users) + 1, "name": payload.name, "phone": payload.phone}
        users[user["id"]] = user
        return user

    return app
