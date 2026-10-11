"""Завдання №24: повільний запит.

Звіт «20 останніх оплачених замовлень клієнтів країни X, починаючи з дати Y» на 40 000
замовлень роботи майже 200 000 кроків SQLite VM (на справжньому Postgres з 5 млн рядків це
і є «8 секунд»). Зроби його швидким.

Таблиці (див. test_solution.py):
    users(id INTEGER PRIMARY KEY, email, country)
    orders(id INTEGER PRIMARY KEY, user_id, status, total_cents, created_at)
        created_at це текст 'YYYY-MM-DD HH:MM:SS'; status це 'paid' | 'pending' | 'cancelled'.

Що змінити:
- `QUERY`: один SELECT з іменованими параметрами `:country` і `:since` (дата 'YYYY-MM-DD'),
  що повертає рядки `(order_id, email, total_cents)`: оплачені замовлення користувачів цієї
  країни, створені НЕ раніше початку дня `:since`, від нових до старих
  (`ORDER BY created_at DESC, id DESC`), не більше 20. Результат має лишитись точно таким самим;
- `INDEXES`: список із НЕ БІЛЬШЕ ніж 2 операторів `CREATE INDEX ...`, які допоможуть запиту.

Заглушка нижче правильна, але повільна.
"""

QUERY = """
SELECT o.id, u.email, o.total_cents
FROM orders o
JOIN users u ON u.id = o.user_id
WHERE u.country = :country
  AND date(o.created_at) >= :since
  AND o.status = 'paid'
ORDER BY o.created_at DESC, o.id DESC
LIMIT 20
"""

INDEXES: list[str] = []
