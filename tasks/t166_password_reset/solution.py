"""Завдання №166: безпечне скидання пароля.

Наївна версія: токен `user_id + timestamp`, зберігається як є, живе вічно, повторно
використовується, а відповідь «такого email немає» показує, хто є користувачем.

Реалізуй `ResetService`. Усі залежності передаються ззовні (детермінованість):
    ResetService(users, send, set_password, *, clock, new_token=None, ttl=900, min_length=12)
- `users`: {email: user_id}; ключі вже у нижньому регістрі;
- `send(email, token)`: надсилає лист; викликається ЛИШЕ для відомих email;
- `set_password(user_id, new_password)`: змінює пароль;
- `clock()` повертає поточний час у секундах (float/int);
- `new_token()`: джерело токенів, за замовчуванням `secrets.token_urlsafe(32)`;
- `ttl`: час життя токена в секундах;

`request_reset(email) -> str`
    Повертає ЗАВЖДИ один і той самий текст `GENERIC_MESSAGE` (для відомого й невідомого email,
    щоб не розкривати існування акаунта). Email нормалізується: `strip()` і `lower()`.
    Некоректний вхід (не рядок) теж дає `GENERIC_MESSAGE` без винятків.
    Для відомого email створює новий токен, ДЕАКТИВУЄ усі попередні токени цього користувача
    й викликає `send(email, token)`. Сервіс не зберігає сам токен, лише його
    `hashlib.sha256(token.encode()).hexdigest()`: витік сховища не дає працюючих токенів.

`confirm_reset(token, new_password) -> bool`
    True, якщо пароль змінено. Спершу перевіряється токен, потім пароль. Токен дійсний,
    якщо він виданий цим сервісом, не використаний, не застарілий і не дезактивований новішим. Строк: токен перестає діяти в момент
    `issued_at + ttl` (рівно в цей момент вже недійсний).
    Пароль коротший за `min_length` символів це `ValueError("weak_password")`, і токен
    при цьому НЕ споживається (користувач може спробувати ще раз).
    Усе інше (невідомий, чужий, прострочений, повторний токен, не рядок) це просто `False`,
    без винятків і без підказок, що саме не так.
    Після успіху токен споживається (одноразовий).
"""

GENERIC_MESSAGE = "Якщо такий акаунт існує, ми надіслали лист із інструкцією."


class ResetService:
    def __init__(self, users, send, set_password, *, clock, new_token=None, ttl=900, min_length=12):
        raise NotImplementedError

    def request_reset(self, email) -> str:
        raise NotImplementedError

    def confirm_reset(self, token, new_password) -> bool:
        raise NotImplementedError
