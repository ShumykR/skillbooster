"""Завдання №21: лінтер міграцій без простою (PostgreSQL).

`ALTER TABLE users ADD COLUMN age int NOT NULL` на таблиці з мільйонами рядків або падає (рядки без значення), або надовго
блокує таблицю, і всі запити застосунку стають у чергу. Безпечний шлях це expand -> backfill -> contract: спершу
додати колонку як NULLABLE, потім заповнити пакетами, потім додати обмеження, не блокуючи запису. Лінтер перевіряє SQL
міграції ДО її запуску (так працюють squawk, strong_migrations).

`split_statements(sql) -> list[str]`
    Розбиває скрипт на оператори по `;`, не ламаючи: рядкові літерали `'...'` (подвоєна `''` усередині), ідентифікатори в `"..."`,
    долар-лапки (`$$...$$`, `$tag$...$tag$`), коментарі `-- до кінця рядка` та `/* ... */` (вкладені коментарі можна не підтримувати).
    Коментарі з результату ВИДАЛЯЮТЬСЯ; кожен оператор обрізаний по краях, порожні відкинуті, `;` у результат не входить.
`lint_migration(sql) -> list[tuple[str, int]]`
    Повертає відсортований за (номер, правило) список `(правило, номер)`, де номер це позиція оператора в
    `split_statements` (з 1). Регістр ключових слів і пробіли неважливі; `IF [NOT] EXISTS`, `ONLY`, лапки навколо імен допускаються.
    ALTER TABLE може містити кілька дій через кому (на верхньому рівні, поза дужками), кожна дія перевіряється окремо;
    одне правило на оператор повідомляється один раз.

    MIG001  ADD COLUMN ... NOT NULL без DEFAULT.
    MIG002  ADD COLUMN, що переписує таблицю: тип SERIAL/BIGSERIAL/SMALLSERIAL, DEFAULT з летючою функцією
            (random(), gen_random_uuid(), uuid_generate_v4(), clock_timestamp(), nextval(...), timeofday()), або `GENERATED ... STORED`.
            (Постійні DEFAULT та now()/current_timestamp у PostgreSQL 11+ таблицю не переписують.)
    MIG003  CREATE [UNIQUE] INDEX без CONCURRENTLY, якщо таблицю НЕ створено раніше в цьому ж скрипті.
    MIG004  DROP COLUMN або DROP TABLE (незворотне; потрібне окреме підтвердження в фазі contract).
            `DROP CONSTRAINT`, `DROP DEFAULT`, `DROP NOT NULL` сюди не входять.
    MIG005  ALTER COLUMN ... [SET DATA] TYPE (переписування таблиці).
    MIG006  ADD [CONSTRAINT x] FOREIGN KEY або CHECK без NOT VALID.
    MIG007  ADD [CONSTRAINT x] UNIQUE або PRIMARY KEY без USING INDEX.
    MIG008  RENAME (колонки чи таблиці) в ALTER TABLE: стара версія застосунку одразу зламається.
    MIG009  ALTER COLUMN ... SET NOT NULL (повне сканування під блокуванням).
    MIG010  Скрипт починає блокуючі DDL (ALTER TABLE, CREATE INDEX, DROP TABLE/INDEX, TRUNCATE) без попереднього
            `SET [LOCAL|SESSION] lock_timeout`. Повідомляється ОДИН раз, на першому такому операторі.
            CREATE INDEX на таблиці, створеній раніше в цьому ж скрипті, блокуючим не вважається.
    Рядкові літерали не повинні давати хибних спрацювань (`DEFAULT 'DROP COLUMN'`, `COMMENT ON ... IS 'NOT NULL'`).
"""


def split_statements(sql: str) -> list[str]:
    raise NotImplementedError


def lint_migration(sql: str) -> list[tuple[str, int]]:
    raise NotImplementedError
