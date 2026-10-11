"""Завдання №25: аномалії паралельних транзакцій.

Два користувачі одночасно оновлюють один баланс, і одне оновлення тихо зникає (lost update). Така помилка не видна в тестах,
де запити йдуть по черзі. Тут ми працюємо з РОЗКЛАДОМ (schedule): послідовністю операцій кількох транзакцій у порядку,
в якому вони реально виконались, і шукаємо в ньому класичні аномалії (за Berenson et al., «A Critique of ANSI SQL Isolation Levels»).

Операція це кортеж: ("begin", tx), ("read", tx, key), ("write", tx, key), ("commit", tx), ("abort", tx).
`tx` та `key` це рядки. Розклад це список операцій у порядку виконання.

`find_anomalies(schedule) -> list[tuple[str, str, str, str]]`
    Повертає відсортований список УНІКАЛЬНИХ кортежів `(аномалія, tx_а, tx_б, ключ)`. Нижче r1[x] читання x транзакцією T1,
    w2[x] запис T2 і т. д.; "раніше" означає позицію в розкладі.
    * "dirty_read": T2 читає x ПІСЛЯ запису w1[x], коли T1 ще не завершилась (немає commit/abort T1 до цього читання).
      Кортеж: ("dirty_read", T1 (хто писав), T2 (хто читав), x). Результат T1 (commit чи abort) значення не має.
    * "non_repeatable_read": T1 читає x двічі, а між двома читаннями T2 ЗАФІКСУВАЛА (commit) запис x. Кортеж: (…, T1 (хто читав), T2, x).
      T1 може бути навіть незавершеною.
    * "lost_update": T1 і T2 обидві зафіксовані, T1: r1[x], потім T2: w2[x], потім T1: w1[x] (T2 записала між читанням і записом T1).
      Кортеж: ("lost_update", T1 (чиє оновлення перезаписало), T2 (чиє пропало), x). Якщо T2 відкотилась, втрати немає.
    * "write_skew": T1 і T2 обидві зафіксовані, T1 читає a і пише b, T2 читає b і пише a (a != b), і обидва читання відбулись до першого
      commit у розкладі. Кортеж: ("write_skew", меншa tx за алфавітом, більша tx, "a,b" де a < b за алфавітом).
    Той самий факт не повторюється двічі. Операції відкотів і незавершені транзакції враховуються лише там, де сказано вище.
    Некоректний розклад: невідома операція/форма кортежа, операція транзакції без `begin`, повторний `begin`,
    операція після commit/abort цієї транзакції, `tx`/`key` не рядки: ValueError.

`anomalies_allowed(level) -> set[str]`
    Які з чотирьох аномалій ДОЗВОЛЯЄ рівень ізоляції (PostgreSQL; регістр і пробіли у назві неважливі, "read committed" тощо):
        "read uncommitted": у PostgreSQL він поводиться як READ COMMITTED, тож дозволяє те саме, що й read committed;
        "read committed":   {"non_repeatable_read", "lost_update", "write_skew"};
        "repeatable read":  {"write_skew"} (знімок даних; lost update блокується помилкою серіалізації);
        "serializable":     порожня множина.
    Невідомий рівень: ValueError.

`violations(schedule, level) -> list[tuple]`
    Аномалії з `find_anomalies`, які рівень `level` НЕ повинен допускати (тобто яких там не мало б бути). Якщо розклад
    їх містить, то він не міг виникнути на цьому рівні: це й виявляє баг (або невірно вказаний рівень).
"""

ANOMALIES = ("dirty_read", "non_repeatable_read", "lost_update", "write_skew")


def find_anomalies(schedule) -> list[tuple[str, str, str, str]]:
    raise NotImplementedError


def anomalies_allowed(level: str) -> set[str]:
    raise NotImplementedError


def violations(schedule, level: str) -> list[tuple]:
    raise NotImplementedError
