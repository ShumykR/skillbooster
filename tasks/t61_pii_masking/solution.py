"""Завдання №61: Логи без PII.

Логи потрапляють у стороннє сховище, до якого має доступ багато людей.
Напиши функцію, що маскує чутливі дані перед записом.
"""


def mask_pii(text: str) -> str:
    """Маскує чутливі дані в рядку логу.

    - email: `john.doe@example.com` -> `j***@example.com`;
    - банківські картки (13–19 цифр, можливо з пробілами/дефісами, що проходять
      перевірку Луна) -> `**** **** **** 1111` (лише останні 4 цифри).
      Довгі числа, що НЕ є картками (id замовлень тощо), не чіпати;
    - `Bearer <token>` -> `Bearer [REDACTED]`;
    - значення ключів password, passwd, secret, api_key, apikey, api-key, token
      у форматах `key=value`, `key: value` і JSON `"key": "value"`
      -> `[REDACTED]` (у JSON зберігай лапки: `"password": "[REDACTED]"`).

    Функція має бути ідемпотентною: mask_pii(mask_pii(x)) == mask_pii(x).
    """
    raise NotImplementedError
