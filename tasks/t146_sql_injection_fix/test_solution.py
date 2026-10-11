import sqlite3

import pytest

from solution import find_users, get_user_by_email

ROWS = [
    (1, "Ann", "ann@example.com", "admin", "HASH-ann-secret"),
    (2, "Anna", "anna@example.com", "user", "HASH-anna-secret"),
    (3, "Bob", "bob@example.com", "user", "HASH-bob-secret"),
    (4, "100% Cotton", "cotton@example.com", "user", "HASH-cotton-secret"),
    (5, "1000 Things", "things@example.com", "user", "HASH-things-secret"),
    (6, "a_b", "ab@example.com", "user", "HASH-ab-secret"),
    (7, "axb", "axb@example.com", "user", "HASH-axb-secret"),
    (8, "back\\slash", "back@example.com", "user", "HASH-back-secret"),
    (9, "O'Brien", "obrien@example.com", "user", "HASH-obrien-secret"),
    (10, "annie", "annie@example.com", "user", "HASH-annie-secret"),
]


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT, role TEXT, password_hash TEXT)")
    c.executemany("INSERT INTO users VALUES (?, ?, ?, ?, ?)", ROWS)
    c.commit()
    yield c
    c.close()


def names(rows):
    return [r["name"] for r in rows]


def assert_no_leak(rows):
    blob = repr(rows)
    assert "HASH-" not in blob and "password_hash" not in blob


# --- чесна поведінка ---------------------------------------------------------------------------

def test_prefix_search_and_result_shape(conn):
    rows = find_users(conn, "Ann")
    assert names(rows) == ["Ann", "Anna", "annie"]  # LIKE нечутливий до регістру для ASCII
    assert rows[0] == {"id": 1, "name": "Ann", "email": "ann@example.com"}
    assert all(set(r) == {"id", "name", "email"} for r in rows)
    assert_no_leak(rows)


def test_empty_prefix_returns_everyone_in_default_order(conn):
    rows = find_users(conn, "")
    assert len(rows) == 10
    assert rows[0]["name"] == "100% Cotton"  # двійкове порівняння: '%' менший за '0'


@pytest.mark.parametrize(
    "sort_by, order, first",
    [("name", "asc", "100% Cotton"), ("name", "desc", "back\\slash"), ("id", "desc", 10), ("id", "ASC", 1),
     ("email", "DESC", "things@example.com"), ("email", "Asc", "ab@example.com")],
)
def test_sorting(conn, sort_by, order, first):
    rows = find_users(conn, "", sort_by=sort_by, order=order)
    key = "id" if sort_by == "id" else sort_by
    assert rows[0][key] == first


def test_limit(conn):
    assert len(find_users(conn, "", limit=3)) == 3
    assert len(find_users(conn, "", limit=100)) == 10
    assert len(find_users(conn, "", limit=1)) == 1


def test_ties_are_broken_by_id(conn):
    conn.execute("INSERT INTO users VALUES (20, 'Ann', 'ann2@example.com', 'user', 'HASH-x')")
    conn.execute("INSERT INTO users VALUES (15, 'Ann', 'ann3@example.com', 'user', 'HASH-y')")
    rows = find_users(conn, "Ann", sort_by="name", order="asc")
    assert [r["id"] for r in rows if r["name"] == "Ann"] == [1, 15, 20]


def test_apostrophe_in_a_real_name_works(conn):
    rows = find_users(conn, "O'Br")
    assert names(rows) == ["O'Brien"]


# --- LIKE-спецсимволи ---------------------------------------------------------------------------

def test_percent_is_literal(conn):
    assert names(find_users(conn, "100%")) == ["100% Cotton"]  # не «1000 Things»
    assert find_users(conn, "%") == []


def test_underscore_is_literal(conn):
    assert names(find_users(conn, "a_")) == ["a_b"]  # не «axb», не «Ann»
    assert find_users(conn, "_nn") == []


def test_backslash_is_literal(conn):
    assert names(find_users(conn, "back\\")) == ["back\\slash"]
    assert names(find_users(conn, "back\\s")) == ["back\\slash"]


# --- ін'єкції у name_prefix -----------------------------------------------------------------------

@pytest.mark.parametrize(
    "payload",
    [
        "' OR '1'='1",
        "' OR 1=1 --",
        "x' OR name LIKE '%",
        "'; DROP TABLE users; --",
        "' UNION SELECT id, password_hash, email FROM users --",
        "' UNION SELECT 1, password_hash, role FROM users WHERE '1'='1",
        "%' OR '%'='",
        "\\' OR 1=1 --",
        "Ann'--",
        "Ann\" OR \"1\"=\"1",
    ],
)
def test_injection_payloads_in_prefix_find_nothing_and_leak_nothing(conn, payload):
    rows = find_users(conn, payload)
    assert rows == []
    assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 10  # таблиця ціла


def test_union_payload_cannot_exfiltrate_hashes_even_with_matching_names(conn):
    rows = find_users(conn, "Ann' UNION SELECT id, password_hash, email FROM users --")
    assert rows == []
    assert_no_leak(rows)


# --- ін'єкції в sort_by / order / limit -----------------------------------------------------------

@pytest.mark.parametrize(
    "sort_by",
    ["password_hash", "role", "name; DROP TABLE users", "(SELECT password_hash FROM users LIMIT 1)", "name--", "1",
     "NAME", "", "name, password_hash", "id DESC", None, 5],
)
def test_sort_by_allowlist(conn, sort_by):
    with pytest.raises(ValueError):
        find_users(conn, "", sort_by=sort_by)


@pytest.mark.parametrize("order", ["asc; DROP TABLE users", "sideways", "", "asc --", "ASC,id", None, 1])
def test_order_allowlist(conn, order):
    with pytest.raises(ValueError):
        find_users(conn, "", order=order)


@pytest.mark.parametrize("limit", [0, -1, 101, 10**6, "5", "5; DROP TABLE users", None, 5.0, True, False, [5]])
def test_limit_must_be_int_in_range(conn, limit):
    with pytest.raises(ValueError):
        find_users(conn, "", limit=limit)


def test_rejected_input_does_not_touch_the_database(conn):
    statements = []
    conn.set_trace_callback(statements.append)
    with pytest.raises(ValueError):
        find_users(conn, "", sort_by="name; DROP TABLE users")
    assert not any("DROP" in s.upper() for s in statements)


# --- get_user_by_email -------------------------------------------------------------------------------

def test_get_user_by_email(conn):
    user = get_user_by_email(conn, "ann@example.com")
    assert user == {"id": 1, "name": "Ann", "email": "ann@example.com", "role": "admin"}
    assert_no_leak(user)


def test_get_user_by_email_not_found(conn):
    assert get_user_by_email(conn, "nobody@example.com") is None


@pytest.mark.parametrize(
    "payload",
    [
        "' OR '1'='1",
        "' OR 1=1 --",
        "ann@example.com' --",
        "x' UNION SELECT id, password_hash, email, role FROM users --",
        "'; DROP TABLE users; --",
        "ann@example.com' OR '1'='1",
    ],
)
def test_get_user_by_email_injection(conn, payload):
    assert get_user_by_email(conn, payload) is None
    assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 10


def test_email_with_apostrophe_is_a_legit_value(conn):
    conn.execute("INSERT INTO users VALUES (30, 'Pat', ?, 'user', 'HASH-pat')", ("o'neil@example.com",))
    assert get_user_by_email(conn, "o'neil@example.com")["name"] == "Pat"
