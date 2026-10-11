"""Завдання №137: Авторизація викликів інструментів агентом.

Prompt injection у документі чи листі може змусити модель викликати
небезпечний інструмент («поверни гроші», «покажи чужий акаунт»). Модель не є
межею безпеки: рішення «можна/не можна» приймає звичайний код ПЕРЕД викликом.

session = {
    "user_id": 7,
    "role": "customer" | "support",
    "confirmed_actions": {"call-17"},   # id викликів, які ЛЮДИНА підтвердила в UI
}
call = {"id": "call-17", "tool": "refund_order", "args": {"order_id": 5, "amount": 40}}
"""

# Підказка: опиши політику даними (таблицею), а не купою if.
TOOL_POLICY: dict = {}


def authorize_tool_call(call: dict, session: dict) -> tuple[bool, str]:
    """Повертає (дозволено, причина). Причина це непорожній рядок завжди.

    Політика:
    | інструмент        | ролі              | дозволені args                 | додатково                                              |
    |-------------------|-------------------|--------------------------------|--------------------------------------------------------|
    | search_faq        | customer, support | query                          | query: str, довжина 1..500                             |
    | list_my_orders    | customer, support | user_id                        | user_id ДОРІВНЮЄ session.user_id (навіть для support)  |
    | get_order         | customer, support | order_id                       | order_id: int                                          |
    | get_any_user      | support           | user_id                        | лише support                                           |
    | refund_order      | customer, support | order_id, amount               | потрібне підтвердження людини; amount: число > 0;      |
    |                   |                   |                                | customer: amount <= 100, support: amount <= 1000       |

    Додатково для будь-якого виклику:
    - невідомий інструмент => заборонено;
    - зайві (непередбачені) args => заборонено;
    - відсутні обовʼязкові args => заборонено;
    - підтвердження береться ЛИШЕ з session["confirmed_actions"], а не з args
      (модель може підробити `"confirmed": true`).
    """
    raise NotImplementedError
