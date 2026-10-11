import random
import sqlite3

import pytest

from solution import create_indexes

Q1 = "SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC LIMIT 20"
Q2 = "SELECT COUNT(*) FROM orders WHERE status = 'pending' AND created_at > ?"
Q3 = "SELECT id FROM users WHERE lower(email) = ?"


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.executescript(
        """
        CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT NOT NULL);
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, status TEXT NOT NULL,
            created_at INTEGER NOT NULL, total REAL NOT NULL
        );
        """
    )
    rnd = random.Random(1)
    c.executemany("INSERT INTO users(email) VALUES (?)", [(f"User{i}@Example.com",) for i in range(5000)])
    statuses = ["pending"] * 5 + ["paid"] * 80 + ["shipped"] * 15
    c.executemany(
        "INSERT INTO orders(user_id, status, created_at, total) VALUES (?,?,?,?)",
        [(rnd.randint(1, 2000), rnd.choice(statuses), rnd.randint(0, 10**6), rnd.random() * 100) for _ in range(40000)],
    )
    c.commit()
    return c


def plan(conn, sql, arg):
    rows = conn.execute("EXPLAIN QUERY PLAN " + sql, (arg,)).fetchall()
    return " | ".join(r[3] for r in rows)


def user_indexes(conn):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_autoindex%'"
    ).fetchall()
    return [r[0] for r in rows]


def test_no_indexes_before(conn):
    assert user_indexes(conn) == []
    assert "SCAN orders" in plan(conn, Q1, 1)


def test_query1_uses_index_without_sort(conn):
    create_indexes(conn)
    p = plan(conn, Q1, 1)
    assert "USING" in p and "INDEX" in p, p
    assert "SCAN orders" not in p, p
    assert "TEMP B-TREE" not in p, f"сортування все ще потрібне: {p}"


def test_query2_uses_index(conn):
    create_indexes(conn)
    p = plan(conn, Q2, 500000)
    assert "SEARCH orders USING" in p and "INDEX" in p, p


def test_query3_uses_expression_index(conn):
    create_indexes(conn)
    p = plan(conn, Q3, "user42@example.com")
    assert "SEARCH users USING" in p and "INDEX" in p, p
    assert conn.execute(Q3, ("user42@example.com",)).fetchall() == [(43,)]


def test_at_most_three_indexes(conn):
    create_indexes(conn)
    names = user_indexes(conn)
    assert 1 <= len(names) <= 3, f"індексів {len(names)}: {names}"


def test_idempotent(conn):
    create_indexes(conn)
    create_indexes(conn)  # другий виклик не має падати
