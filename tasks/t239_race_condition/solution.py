"""Завдання №239: race condition: перевищення ліміту.

Магазин видає промокод на N використань і списує гроші з балансу. Під паралельними запитами
ліміт перевищується: усі запити спершу ПЕРЕВІРЯЮТЬ стан, а потім ЗАПИСУЮТЬ (CWE-362, CWE-367
TOCTOU). Виправ так, щоб інваріанти трималися за будь-якого чергування запитів, навіть якщо
запити йдуть з різних процесів/воркерів (глобальний `threading.Lock` не допоможе: у production
воркерів багато). Тримай перевірку й запис в одній атомарній операції БД: умовний `UPDATE`,
унікальне обмеження, `BEGIN IMMEDIATE`.

Кожен запит має СВОЄ зʼєднання `sqlite3` (до одного файлу БД). Схему створює `init_db(conn)`:
ти можеш додати в неї обмеження (`UNIQUE`, `CHECK`). Тести викликають `init_db` один раз.

Таблиці (мінімум; можна додати обмеження, імена колонок не змінюй):
    promo(code TEXT PRIMARY KEY, max_uses INTEGER, used INTEGER)
    redemptions(code TEXT, user_id INTEGER)
    accounts(id INTEGER PRIMARY KEY, balance INTEGER)         -- у копійках

`redeem_promo(conn, code, user_id, pause=lambda: None) -> bool`
    True: промокод застосовано (`promo.used` збільшено на 1 і додано рядок у `redemptions`
    разом, атомарно). False: ліміт вичерпано або цей `user_id` уже використав цей код (один
    користувач: один раз, навіть коли два його запити прийшли одночасно). Невідомий `code`:
    `LookupError`. Інваріанти: `used <= max_uses`, `used == кількість рядків redemptions`,
    не більше одного рядка на пару (code, user_id).
`charge(conn, account_id, amount, pause=lambda: None) -> bool`
    Списати `amount` копійок. True: списано. False: коштів не вистачає (баланс не змінюється).
    Невідомий рахунок: `LookupError`. `amount` має бути `int` (не `bool`) > 0, інакше
    `ValueError` (відʼємна сума це поповнення «безкоштовно»). Баланс ніколи не стає відʼємним.

`pause` це гачок тесту: у наївній версії він стоїть між перевіркою й записом, і тест
зупиняє там усі потоки, щоб гонка відтворювалась щоразу. Твоє рішення МОЖЕ його не
викликати. Якщо викликаєш, то лише між перевіркою й записом.
"""
import sqlite3


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS promo (code TEXT PRIMARY KEY, max_uses INTEGER, used INTEGER);
        CREATE TABLE IF NOT EXISTS redemptions (code TEXT, user_id INTEGER);
        CREATE TABLE IF NOT EXISTS accounts (id INTEGER PRIMARY KEY, balance INTEGER);
        """
    )
    conn.commit()


def redeem_promo(conn: sqlite3.Connection, code: str, user_id: int, pause=lambda: None) -> bool:
    # НАЇВНА ВРАЗЛИВА РЕАЛІЗАЦІЯ: перевірка і запис розділені.
    row = conn.execute("SELECT used, max_uses FROM promo WHERE code = ?", (code,)).fetchone()
    if row is None:
        raise LookupError(code)
    used, max_uses = row
    if used >= max_uses:
        return False
    if conn.execute("SELECT 1 FROM redemptions WHERE code = ? AND user_id = ?", (code, user_id)).fetchone():
        return False
    pause()
    conn.execute("UPDATE promo SET used = ? WHERE code = ?", (used + 1, code))
    conn.execute("INSERT INTO redemptions (code, user_id) VALUES (?, ?)", (code, user_id))
    conn.commit()
    return True


def charge(conn: sqlite3.Connection, account_id: int, amount: int, pause=lambda: None) -> bool:
    # НАЇВНА ВРАЗЛИВА РЕАЛІЗАЦІЯ: перевірка і запис розділені.
    row = conn.execute("SELECT balance FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if row is None:
        raise LookupError(account_id)
    balance = row[0]
    if balance < amount:
        return False
    pause()
    conn.execute("UPDATE accounts SET balance = ? WHERE id = ?", (balance - amount, account_id))
    conn.commit()
    return True
