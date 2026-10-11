"""Завдання №162: Mass assignment (CWE-915) у FastAPI.

Нижче наївний код: «оновлюємо користувача тим, що прислав клієнт». Він працює, поки клієнт чесний, але
`PATCH /users/me` з тілом `{"role": "admin"}` робить будь-кого адміністратором. Виправ його за вимогами.

`create_app(users: dict[int, dict]) -> FastAPI`, де `users` це «БД»: `{id: {"id", "name", "bio", "email", "role",
"is_active", "password_hash"}}`. Зміни мають потрапляти в цей самий словник.

Автентифікація (спрощена): заголовок `X-User-Id: <ціле>`.
    * нема заголовка, не ціле число або такого користувача немає: 401;
    * користувач є, але `is_active` це False: 403.
Усі перевірки доступу виконуються ДО валідації тіла (непривілейований не повинен дізнаватись, які поля існують).

`GET /users/me` -> 200 `{"id", "name", "bio", "email"}` і БІЛЬШЕ НІЧОГО (ні `password_hash`, ні `role`).

`PATCH /users/me` змінює лише власний профіль. Тіло: `name` (рядок; пробіли по краях обрізаються; після цього 1..50 символів) і/або
    `bio` (рядок до 500 символів або null: очищує). Правила:
    * будь-яке інше поле (`role`, `is_active`, `id`, `email`, `password_hash`, `is_admin`, що завгодно) це 422 і НІЧОГО не змінюється
      (навіть дозволені поля з того ж запиту: операція атомарна);
    * ті самі 422 для порожнього тілу `{}`, не-об'єкта (масив, рядок), `name: null`, чисел замість рядків (БЕЗ приведення типів);
    * успіх: 200 і той самий набір полів, що в `GET /users/me`, зі збереженими значеннями.

`PATCH /admin/users/{user_id}` лише для `role == "admin"` (інакше 403). Тіло: `role` ("user" або "admin") і/або `is_active` (справжній bool).
    * будь-які інші поля 422; порожнє тіло 422; `is_active: "yes"` чи `1` 422;
    * користувача немає: 404; змінювати СЕБЕ (навіть тими самими значеннями) заборонено: 409;
    * успіх: 200 `{"id", "name", "email", "role", "is_active"}` (без `password_hash` і `bio`).
"""
from fastapi import FastAPI, Header, HTTPException, Request


def create_app(users: dict[int, dict]) -> FastAPI:
    app = FastAPI()

    def current_user(x_user_id: str | None) -> dict:
        try:
            return users[int(x_user_id)]
        except (TypeError, ValueError, KeyError):
            raise HTTPException(401, "unauthorized")

    # НАЇВНА ВРАЗЛИВА РЕАЛІЗАЦІЯ: перепиши.
    @app.get("/users/me")
    def get_me(x_user_id: str | None = Header(default=None)):
        return current_user(x_user_id)

    @app.patch("/users/me")
    async def patch_me(request: Request, x_user_id: str | None = Header(default=None)):
        user = current_user(x_user_id)
        user.update(await request.json())
        return user

    @app.patch("/admin/users/{user_id}")
    async def patch_user(user_id: int, request: Request, x_user_id: str | None = Header(default=None)):
        current_user(x_user_id)
        target = users.get(user_id)
        if target is None:
            raise HTTPException(404, "not found")
        target.update(await request.json())
        return target

    return app
