import datetime
import random
import re
import sqlite3

import pytest

from solution import INDEXES, QUERY

COUNTRIES = ["UA", "PL", "DE", "FR", "ES", "IT", "US", "CA", "GB", "NL"]
N_USERS = 2000
N_ORDERS = 40000
STEP_BUDGET = 10_000


def build_big():
    rnd = random.Random(7)
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE users(id INTEGER PRIMARY KEY, email TEXT NOT NULL, country TEXT NOT NULL)")
    c.execute(
        "CREATE TABLE orders(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),"
        " status TEXT NOT NULL, total_cents INTEGER NOT NULL, created_at TEXT NOT NULL)"
    )
    c.executemany(
        "INSERT INTO users VALUES(?,?,?)",
        [(i, f"u{i}@x.io", COUNTRIES[i % 10]) for i in range(1, N_USERS + 1)],
    )
    base = datetime.datetime(2026, 1, 1)
    rows = []
    for i in range(1, N_ORDERS + 1):
        t = base + datetime.timedelta(minutes=(i // 3) * 10)  # по 3 замовлення на один момент
        rows.append((i, rnd.randint(1, N_USERS), rnd.choices(["paid", "pending", "cancelled"], [7, 2, 1])[0],
                     rnd.randint(100, 50000), t.strftime("%Y-%m-%d %H:%M:%S")))
    c.executemany("INSERT INTO orders VALUES(?,?,?,?,?)", rows)
    c.commit()
    return c


@pytest.fixture(scope="module")
def template():
    return build_big()


@pytest.fixture
def db(template):
    c = sqlite3.connect(":memory:")
    template.backup(c)
    yield c
    c.close()


def apply_indexes(conn):
    for ddl in INDEXES:
        conn.execute(ddl)


def expected(conn, country, since):
    users = {u: (e, cc) for u, e, cc in conn.execute("SELECT id, email, country FROM users")}
    rows = [
        (oid, users[uid][0], total, created)
        for oid, uid, status, total, created in conn.execute(
            "SELECT id, user_id, status, total_cents, created_at FROM orders"
        )
        if status == "paid" and users[uid][1] == country and created >= since
    ]
    rows.sort(key=lambda r: (r[3], r[0]), reverse=True)
    return [r[:3] for r in rows[:20]]


def run(conn, country, since):
    return conn.execute(QUERY, {"country": country, "since": since}).fetchall()


def steps(conn, country, since):
    n = [0]

    def tick():
        n[0] += 1
        return 0

    conn.set_progress_handler(tick, 1)
    try:
        run(conn, country, since)
    finally:
        conn.set_progress_handler(None, 0)
    return n[0]


CASES = [("UA", "2026-01-20"), ("PL", "2026-03-30"), ("DE", "2026-01-01"), ("US", "2026-12-31"), ("GB", "2026-04-03")]


# ---------- форма рішення ----------

def test_query_is_single_select_with_named_params():
    q = QUERY.strip()
    assert q.upper().startswith(("SELECT", "WITH"))
    assert ":country" in q and ":since" in q
    assert ";" not in q.rstrip(";")


def test_at_most_two_plain_indexes():
    assert len(INDEXES) <= 2
    for ddl in INDEXES:
        assert re.match(r"\s*CREATE\s+INDEX\b", ddl, re.I), ddl


def test_indexes_apply_cleanly(db):
    apply_indexes(db)


# ---------- коректність ----------

@pytest.mark.parametrize("country, since", CASES)
def test_same_result_as_reference(db, country, since):
    apply_indexes(db)
    assert run(db, country, since) == expected(db, country, since)


def test_reference_data_is_meaningful(db):
    assert len(expected(db, "UA", "2026-01-20")) == 20
    assert 0 < len(expected(db, "GB", "2026-04-03")) < 20
    assert expected(db, "US", "2026-12-31") == []


def test_boundary_and_filters_on_tiny_data():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE users(id INTEGER PRIMARY KEY, email TEXT NOT NULL, country TEXT NOT NULL)")
    c.execute(
        "CREATE TABLE orders(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, status TEXT NOT NULL,"
        " total_cents INTEGER NOT NULL, created_at TEXT NOT NULL)"
    )
    c.executemany("INSERT INTO users VALUES(?,?,?)", [(1, "a@x", "UA"), (2, "b@x", "PL")])
    c.executemany("INSERT INTO orders VALUES(?,?,?,?,?)", [
        (1, 1, "paid", 10, "2026-02-09 23:59:59"),     # раніше межі
        (2, 1, "paid", 20, "2026-02-10 00:00:00"),     # рівно на межі: входить
        (3, 1, "pending", 30, "2026-02-10 12:00:00"),  # не оплачено
        (4, 2, "paid", 40, "2026-02-10 12:00:00"),     # інша країна
        (5, 1, "paid", 50, "2026-02-10 12:00:00"),
        (6, 1, "paid", 60, "2026-02-10 12:00:00"),     # той самий момент: більший id вище
        (7, 1, "cancelled", 70, "2026-02-11 00:00:00"),
        (8, 1, "paid", 80, "2026-02-11 23:59:59"),
    ])
    apply_indexes(c)
    assert run(c, "UA", "2026-02-10") == [(8, "a@x", 80), (6, "a@x", 60), (5, "a@x", 50), (2, "a@x", 20)]
    assert run(c, "PL", "2026-02-10") == [(4, "b@x", 40)]
    assert run(c, "UA", "2026-02-12") == []


def test_limit_is_20(db):
    apply_indexes(db)
    assert len(run(db, "UA", "2026-01-01")) == 20


def test_new_rows_are_visible(db):
    apply_indexes(db)
    db.execute("INSERT INTO orders VALUES(999999, 10, 'paid', 123, '2027-01-01 00:00:00')")
    assert run(db, "UA", "2026-01-01")[0] == (999999, "u10@x.io", 123)


# ---------- швидкодія (кроки SQLite VM замість секунд: детерміновано) ----------

@pytest.mark.parametrize("country, since", CASES)
def test_within_step_budget(db, country, since):
    apply_indexes(db)
    n = steps(db, country, since)
    assert n <= STEP_BUDGET, f"{n} кроків VM, потрібно не більше {STEP_BUDGET}"


def test_plan_has_no_full_scan_or_sort(db):
    apply_indexes(db)
    plan = [r[3] for r in db.execute("EXPLAIN QUERY PLAN " + QUERY, {"country": "UA", "since": "2026-01-20"})]
    assert not any(re.match(r"SCAN (o|orders)\b", p) for p in plan), plan
    assert not any("TEMP B-TREE" in p for p in plan), plan
