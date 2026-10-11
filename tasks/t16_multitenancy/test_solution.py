import sqlite3

import pytest

from solution import NoteRepo


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL, title TEXT NOT NULL)")
    yield c
    c.close()


@pytest.fixture
def repos(conn):
    return NoteRepo(conn, "acme"), NoteRepo(conn, "globex")


def test_add_and_get_roundtrip(repos):
    a, _ = repos
    nid = a.add("hello")
    assert isinstance(nid, int)
    assert a.get(nid) == {"id": nid, "title": "hello"}


def test_get_missing_is_none(repos):
    a, _ = repos
    assert a.get(12345) is None


def test_list_is_scoped_and_ordered(repos):
    a, b = repos
    ids_a = [a.add("a1"), b.add("b1"), a.add("a2"), b.add("b2"), a.add("a3")]
    assert [n["title"] for n in a.list()] == ["a1", "a2", "a3"]
    assert [n["title"] for n in b.list()] == ["b1", "b2"]
    assert [n["id"] for n in a.list()] == sorted(n["id"] for n in a.list())
    assert len(set(ids_a)) == 5


def test_count_is_scoped(repos):
    a, b = repos
    a.add("x")
    a.add("y")
    b.add("z")
    assert (a.count(), b.count()) == (2, 1)
    assert NoteRepo(a.conn, "empty").count() == 0


def test_cannot_read_foreign_note_by_id(repos):
    a, b = repos
    secret = b.add("globex secret")
    assert a.get(secret) is None
    assert b.get(secret) == {"id": secret, "title": "globex secret"}


def test_foreign_and_missing_are_indistinguishable(repos):
    a, b = repos
    foreign = b.add("s")
    assert a.get(foreign) == a.get(999999) is None
    assert a.update(foreign, "x") == a.update(999999, "x") is False
    assert a.delete(foreign) == a.delete(999999) is False


def test_cannot_update_foreign_note(repos):
    a, b = repos
    nid = b.add("original")
    assert a.update(nid, "hacked") is False
    assert b.get(nid)["title"] == "original"


def test_cannot_delete_foreign_note(repos):
    a, b = repos
    nid = b.add("keep me")
    assert a.delete(nid) is False
    assert b.count() == 1


def test_update_and_delete_own_note(repos):
    a, _ = repos
    nid = a.add("v1")
    assert a.update(nid, "v2") is True
    assert a.get(nid)["title"] == "v2"
    assert a.delete(nid) is True
    assert a.get(nid) is None
    assert a.delete(nid) is False


def test_sql_injection_in_tenant_id_does_not_leak(conn):
    NoteRepo(conn, "acme").add("private")
    evil = NoteRepo(conn, "x' OR '1'='1")
    assert evil.list() == []
    assert evil.count() == 0
    evil.add("mine")
    assert [n["title"] for n in NoteRepo(conn, "acme").list()] == ["private"]


def test_sql_injection_in_title_is_stored_literally(conn, repos):
    a, _ = repos
    nid = a.add("'); DROP TABLE notes; --")
    assert a.get(nid)["title"] == "'); DROP TABLE notes; --"
    assert conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == 1


def test_like_wildcards_in_tenant_id_are_not_patterns(conn):
    NoteRepo(conn, "acme").add("private")
    assert NoteRepo(conn, "%").list() == []
    assert NoteRepo(conn, "ac_e").list() == []


def test_tenant_ids_differing_only_by_case_are_different(conn):
    NoteRepo(conn, "Acme").add("upper")
    assert NoteRepo(conn, "acme").list() == []


@pytest.mark.parametrize("bad", ["", None, 5])
def test_invalid_tenant_id(conn, bad):
    with pytest.raises(ValueError):
        NoteRepo(conn, bad)


def test_rows_are_really_stored_with_tenant_id(conn, repos):
    a, b = repos
    a.add("x")
    b.add("y")
    rows = conn.execute("SELECT tenant_id, title FROM notes ORDER BY id").fetchall()
    assert rows == [("acme", "x"), ("globex", "y")]
