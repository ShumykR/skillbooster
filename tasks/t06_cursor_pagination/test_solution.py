import sqlite3

import pytest

from solution import fetch_page


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE items (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at INTEGER NOT NULL, title TEXT NOT NULL)")
    c.execute("CREATE INDEX ix ON items (created_at, id)")
    yield c
    c.close()


def seed(conn, n, ts=lambda i: i):
    for i in range(1, n + 1):
        conn.execute("INSERT INTO items (created_at, title) VALUES (?, ?)", (ts(i), f"item-{i}"))
    conn.commit()


def walk(conn, limit, hook=None):
    """Обходить усі сторінки, повертає список id у порядку отримання."""
    ids, cursor, pages = [], None, 0
    while True:
        rows, cursor = fetch_page(conn, limit, cursor)
        ids += [r["id"] for r in rows]
        pages += 1
        assert pages < 1000, "нескінченний обхід"
        if hook:
            hook(pages)
        if cursor is None:
            return ids


def test_first_page_is_newest_first_with_expected_shape(conn):
    seed(conn, 10)
    rows, cursor = fetch_page(conn, 3)
    assert rows == [
        {"id": 10, "created_at": 10, "title": "item-10"},
        {"id": 9, "created_at": 9, "title": "item-9"},
        {"id": 8, "created_at": 8, "title": "item-8"},
    ]
    assert isinstance(cursor, str) and cursor


def test_full_walk_returns_everything_once_in_order(conn):
    seed(conn, 25)
    assert walk(conn, 4) == list(range(25, 0, -1))


def test_last_page_has_no_cursor_and_exact_multiple_does_not_produce_empty_page(conn):
    seed(conn, 6)
    rows, cursor = fetch_page(conn, 3)
    rows2, cursor2 = fetch_page(conn, 3, cursor)
    assert [r["id"] for r in rows2] == [3, 2, 1]
    assert cursor2 is None


def test_empty_table(conn):
    assert fetch_page(conn, 10) == ([], None)


def test_limit_larger_than_data(conn):
    seed(conn, 3)
    rows, cursor = fetch_page(conn, 100)
    assert len(rows) == 3 and cursor is None


def test_ties_in_created_at_are_not_lost_or_duplicated(conn):
    seed(conn, 30, ts=lambda i: i // 10)  # багато записів з однаковим created_at
    ids = walk(conn, 4)
    assert ids == sorted(range(1, 31), reverse=True)
    assert len(ids) == len(set(ids)) == 30


def test_inserts_between_pages_do_not_shift_the_walk(conn):
    seed(conn, 12)
    first, cursor = fetch_page(conn, 5)
    seed(conn, 7, ts=lambda i: 100 + i)  # нові записи з більшим created_at
    ids = [r["id"] for r in first]
    while cursor is not None:
        rows, cursor = fetch_page(conn, 5, cursor)
        ids += [r["id"] for r in rows]
    assert ids == list(range(12, 0, -1))  # жодного дубля й жодного пропуску


def test_deleting_the_cursor_row_between_pages_is_fine(conn):
    seed(conn, 10)
    first, cursor = fetch_page(conn, 3)  # 10, 9, 8
    conn.execute("DELETE FROM items WHERE id = 8")
    conn.commit()
    rest = walk_from(conn, 3, cursor)
    assert rest == [7, 6, 5, 4, 3, 2, 1]


def walk_from(conn, limit, cursor):
    ids = []
    while cursor is not None:
        rows, cursor = fetch_page(conn, limit, cursor)
        ids += [r["id"] for r in rows]
    return ids


def test_no_offset_in_sql(conn):
    seed(conn, 20)
    statements = []
    conn.set_trace_callback(statements.append)
    walk(conn, 5)
    selects = [s for s in statements if s.lstrip().upper().startswith("SELECT")]
    assert selects, "SQL не перехоплено"
    assert not any("OFFSET" in s.upper() for s in selects)


def test_no_count_or_full_scan_in_python(conn):
    seed(conn, 50)
    seen = []
    conn.set_trace_callback(seen.append)
    fetch_page(conn, 5)
    selects = [s for s in seen if s.lstrip().upper().startswith("SELECT")]
    assert selects, "SQL не перехоплено"
    assert not any("COUNT" in s.upper() for s in selects)
    assert any("LIMIT" in s.upper() for s in selects)


@pytest.mark.parametrize("limit", [0, -1, 101, 1000])
def test_bad_limit(conn, limit):
    with pytest.raises(ValueError):
        fetch_page(conn, limit)


@pytest.mark.parametrize("limit", [1.5, "5", None])
def test_non_int_limit(conn, limit):
    with pytest.raises(ValueError):
        fetch_page(conn, limit)


@pytest.mark.parametrize("cursor", ["", "garbage", "!!!!", "bnVsbA==", "W10=", "WyJhIiwgImIiXQ==", 123, b"x"])
def test_bad_cursor(conn, cursor):
    seed(conn, 5)
    with pytest.raises(ValueError):
        fetch_page(conn, 2, cursor)


def test_boundaries_limit_1_and_100(conn):
    seed(conn, 3)
    assert walk(conn, 1) == [3, 2, 1]
    rows, cursor = fetch_page(conn, 100)
    assert len(rows) == 3 and cursor is None
