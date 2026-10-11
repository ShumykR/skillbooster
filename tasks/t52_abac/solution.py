"""Завдання №52: від RBAC до ABAC.

`authorize(user, action, resource)` повертає True/False. Приклад даних:

    user     = {"id": "u1", "tenant": "t1", "roles": ["editor"], "clearance": 1}
    resource = {"id": "r1", "tenant": "t1", "owner_id": "u2", "status": "active",
                "classification": "internal"}

Дії: `read`, `update`, `delete`, `share`. Невідома дія завжди заборонена.

ДОЗВОЛИ (об'єднуються):
- роль `viewer`: read;  `editor`: read, update;  `admin`: read, update, delete, share;
  невідомі ролі ігноруються; `roles` може бути відсутнім або порожнім;
- власник ресурсу (`user.id == resource.owner_id`, обидва не None): read, update, delete.

ЗАБОРОНИ (мають пріоритет над будь-яким дозволом, перевіряй їх першими):
1. `tenant` користувача і ресурсу різні або відсутні (порожні) → заборона (навіть для admin);
2. `classification == "confidential"` і `clearance` користувача (за замовчуванням 0) менший за 2
   → заборона будь-якої дії;
3. `status == "archived"`: дозволено лише `read`; єдиний виняток: `admin` може `delete`.

Принцип: все, що не дозволено явно, заборонено (default deny). Відсутні поля не повинні
викликати виняток.
"""


def authorize(user: dict, action: str, resource: dict) -> bool:
    raise NotImplementedError
