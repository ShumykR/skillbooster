"""Завдання №211: безпечний text-to-SQL.

LLM перетворює питання користувача на SQL. Виконувати цей SQL «як є» небезпечно: модель можна
переконати (prompt injection у даних чи питанні) видати `DELETE`, `ATTACH`, `PRAGMA`, читання
чужих таблиць чи `UNION` із секретами (CWE-89, CWE-863, ~CWE-639). Тому запит від моделі це
НЕДОВІРЕНИЙ ввід. Захист будується на ВБУДОВАНИХ механізмах SQLite, а не на регулярках:
`sqlite3.Connection.set_authorizer`, тимчасові VIEW для фільтра власника й обгортка з LIMIT.

Policy (словник):
    {"tables": {"orders": {"columns": ["id", "amount", "owner_id"], "owner_column": "owner_id"},
                "products": {"columns": ["id", "title"], "owner_column": None}},
     "functions": ["count", "sum", ...],     # необовʼязково; за замовчуванням DEFAULT_FUNCTIONS
     "max_rows": 50}                          # необовʼязково; int >= 1; за замовчуванням 50
`owner_column` це колонка таблиці з власником рядка; `None`: таблиця спільна для всіх. Колонка
власника МОЖЕ не входити в `columns` (тоді модель її не бачить, але фільтр працює).
Таблиця чи колонка з policy, якої немає в БД, це `ValueError` (помилка конфігурації).

`run_query(conn, sql, policy, owner_id) -> dict`
    Виконує запит і повертає `{"columns": [імена], "rows": [tuple, ...], "truncated": bool}`.
    Будь-яка відмова це `SQLRejected(reason, detail)` (атрибути `.reason`, `.detail`). Дані БД
    ніколи не змінюються, зовнішні файли не відкриваються.
    * `owner_id`: `int` (не `bool`) або `str`, інакше `ValueError`. Підставляється в SQL ЛИШЕ
      безпечно (значення не може змінити структуру запиту: `"1 OR 1=1"` це просто рядок).
    * Рівно ОДИН `SELECT` (допускаються `WITH ...`, підзапити, `JOIN`, `UNION`, кінцеві `;` та
      пробіли). Довжина `sql` <= `MAX_SQL_LENGTH` символів.
    * Таблиці й колонки лише з policy; бачити можна лише `columns` (`SELECT *` розгортається в
      дозволені колонки). Модель бачить ТІЛЬКИ рядки власника `owner_id` у таблицях із
      `owner_column`, як би вона не писала `WHERE`, `UNION` чи підзапити. Звернення
      `main.orders` в обхід фільтра заборонене.
    * Функції лише з allowlist (без урахування регістру). `like` це функція в SQLite, тому вона
      у списку за замовчуванням.
    * Ліміт рядків: результат містить НЕ БІЛЬШЕ `max_rows` рядків; якщо їх було більше,
      `truncated=True`. Власний `LIMIT` моделі лише зменшує результат.
    * Після виклику (успішного чи ні) зʼєднання `conn` у початковому стані: authorizer знято,
      допоміжні обʼєкти прибрані, `conn` придатне для звичайної роботи.
    Коди `reason`:
      `empty`              порожній чи не-рядковий запит;
      `too-long`           довший за `MAX_SQL_LENGTH`;
      `multiple-statements` більше одного statement (нічого з них не виконується);
      `forbidden-action`   не `SELECT`: INSERT/UPDATE/DELETE/DROP/CREATE/ALTER/ATTACH/PRAGMA/VACUUM/...;
      `forbidden-table`    таблиця поза policy (включно з `sqlite_master`, неіснуючими, `main.x`);
      `forbidden-column`   колонка поза policy або неіснуюча (`rowid` теж);
      `forbidden-function` функція поза allowlist (`load_extension`, `randomblob`, `printf`, ...);
      `syntax-error`       некоректний SQL.
    `detail` це пояснення для МОДЕЛІ (щоб вона виправила запит): імʼя порушника, а для таблиць і
    колонок ще й дозволені таблиці й колонки.

`build_prompt(question, policy, previous=None) -> str`
    Рядки через "\n": "Write one SQLite SELECT query that answers the question.",
    f"Question: {question}", "Allowed tables and columns:", по рядку на таблицю за алфавітом
    f"- {table}: {колонки за алфавітом через ', '}", f"At most {max_rows} rows. Reply with the SQL only.".
    Якщо `previous` (словник `{"sql", "reason", "detail"}`) заданий, ще три рядки:
    "Previous attempt:", previous["sql"], f"Rejected: {reason}: {detail}".

`ask(llm, conn, question, policy, owner_id, max_attempts=3) -> dict`
    `llm(prompt) -> str`. Цикл до `max_attempts` спроб (< 1: `ValueError`): промпт через
    `build_prompt` (з останньою відмовою), відповідь очищується: пробіли по краях і обгортка
    ```sql ... ``` чи ``` ... ``` знімається; `run_query`. Не-рядкова відповідь рахується як
    порожня (`empty`) і витрачає спробу.
    * успіх: `{"status": "ok", "sql": очищений sql, "attempts": n, "columns", "rows", "truncated"}`;
    * усі спроби відхилені: `{"status": "rejected", "attempts": max_attempts, "reason": reason
      останньої, "history": [{"sql", "reason", "detail"}, ...]}`;
    * `llm` кинула виняток: `{"status": "llm-error", "attempts": n, "history": [...]}` без повторів.
"""
import sqlite3  # noqa: F401  (знадобиться)

DEFAULT_FUNCTIONS = {"count", "sum", "avg", "min", "max", "lower", "upper", "round", "coalesce", "length", "abs", "like"}
MAX_SQL_LENGTH = 2000


class SQLRejected(Exception):
    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


def run_query(conn: sqlite3.Connection, sql: str, policy: dict, owner_id) -> dict:
    raise NotImplementedError


def build_prompt(question: str, policy: dict, previous: dict | None = None) -> str:
    raise NotImplementedError


def ask(llm, conn: sqlite3.Connection, question: str, policy: dict, owner_id, max_attempts: int = 3) -> dict:
    raise NotImplementedError
