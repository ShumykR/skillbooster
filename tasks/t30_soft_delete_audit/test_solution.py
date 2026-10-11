import sqlite3

import pytest

from solution import DocRepo

SCHEMA = """
CREATE TABLE docs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    deleted_at REAL
);
CREATE TABLE audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    actor TEXT NOT NULL,
    at REAL NOT NULL,
    old_title TEXT,
    new_title TEXT
);
"""


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        self.now += 10.0
        return self.now


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.executescript(SCHEMA)
    yield c
    c.close()


@pytest.fixture
def repo(conn):
    return DocRepo(conn, clock=Clock())


def test_create_and_get(repo):
    doc_id = repo.create("Contract", "alice")
    assert repo.get(doc_id) == {"id": doc_id, "title": "Contract", "deleted_at": None}
    assert repo.get(999) is None


def test_list_in_id_order(repo):
    ids = [repo.create(t, "a") for t in ("one", "two", "three")]
    assert [d["id"] for d in repo.list()] == ids


def test_soft_delete_hides_but_keeps_row(repo, conn):
    doc_id = repo.create("Secret", "alice")
    assert repo.delete(doc_id, "bob") is True
    assert repo.get(doc_id) is None
    assert repo.list() == []
    kept = repo.get(doc_id, include_deleted=True)
    assert kept["title"] == "Secret" and kept["deleted_at"] is not None
    assert conn.execute("SELECT COUNT(*) FROM docs").fetchone()[0] == 1


def test_deleted_at_comes_from_the_injected_clock(conn):
    repo = DocRepo(conn, clock=lambda: 42.5)
    doc_id = repo.create("x", "a")
    repo.delete(doc_id, "a")
    assert repo.get(doc_id, include_deleted=True)["deleted_at"] == 42.5
    assert {h["at"] for h in repo.history(doc_id)} == {42.5}


def test_delete_twice_or_unknown_returns_false(repo):
    doc_id = repo.create("x", "a")
    assert repo.delete(doc_id, "a") is True
    assert repo.delete(doc_id, "a") is False
    assert repo.delete(404, "a") is False
    assert len(repo.history(doc_id)) == 2  # create + один delete


def test_restore(repo):
    doc_id = repo.create("Doc", "alice")
    repo.delete(doc_id, "bob")
    assert repo.restore(doc_id, "carol") is True
    assert repo.get(doc_id) == {"id": doc_id, "title": "Doc", "deleted_at": None}
    assert repo.list() == [repo.get(doc_id)]


def test_restore_when_not_deleted_or_unknown(repo):
    doc_id = repo.create("Doc", "a")
    assert repo.restore(doc_id, "a") is False
    assert repo.restore(404, "a") is False
    assert [h["action"] for h in repo.history(doc_id)] == ["create"]


def test_rename_records_old_and_new_title(repo):
    doc_id = repo.create("v1", "alice")
    assert repo.rename(doc_id, "v2", "bob") is True
    assert repo.get(doc_id)["title"] == "v2"
    last = repo.history(doc_id)[-1]
    assert (last["action"], last["actor"], last["old_title"], last["new_title"]) == ("rename", "bob", "v1", "v2")


def test_cannot_rename_deleted_or_unknown(repo):
    doc_id = repo.create("v1", "a")
    repo.delete(doc_id, "a")
    assert repo.rename(doc_id, "v2", "a") is False
    assert repo.rename(404, "v2", "a") is False
    assert repo.get(doc_id, include_deleted=True)["title"] == "v1"
    assert [h["action"] for h in repo.history(doc_id)] == ["create", "delete"]


def test_full_history_shape_and_order(conn):
    clock = Clock()
    repo = DocRepo(conn, clock=clock)
    other = repo.create("other", "zed")
    doc_id = repo.create("A", "alice")
    repo.rename(doc_id, "B", "bob")
    repo.delete(doc_id, "carol")
    repo.restore(doc_id, "dave")
    history = repo.history(doc_id)
    assert [(h["action"], h["actor"], h["old_title"], h["new_title"]) for h in history] == [
        ("create", "alice", None, "A"),
        ("rename", "bob", "A", "B"),
        ("delete", "carol", "B", None),
        ("restore", "dave", None, "B"),
    ]
    times = [h["at"] for h in history]
    assert times == sorted(times) and len(set(times)) == 4
    assert set(history[0]) == {"action", "actor", "at", "old_title", "new_title"}
    assert [h["action"] for h in repo.history(other)] == ["create"]  # чужої історії немає
    assert repo.history(404) == []


def test_audit_failure_rolls_back_create(repo, conn):
    with pytest.raises(sqlite3.IntegrityError):
        repo.create("ghost", None)  # actor NOT NULL порушено в audit
    assert conn.execute("SELECT COUNT(*) FROM docs").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0] == 0


def test_audit_failure_rolls_back_rename_delete_restore(repo, conn):
    doc_id = repo.create("keep", "alice")
    with pytest.raises(sqlite3.IntegrityError):
        repo.rename(doc_id, "changed", None)
    assert repo.get(doc_id)["title"] == "keep"
    with pytest.raises(sqlite3.IntegrityError):
        repo.delete(doc_id, None)
    assert repo.get(doc_id) is not None  # не видалено
    repo.delete(doc_id, "alice")
    with pytest.raises(sqlite3.IntegrityError):
        repo.restore(doc_id, None)
    assert repo.get(doc_id) is None  # залишається видаленим
    assert [h["action"] for h in repo.history(doc_id)] == ["create", "delete"]


def test_changes_are_committed(tmp_path):
    path = tmp_path / "db.sqlite"
    c1 = sqlite3.connect(path)
    c1.executescript(SCHEMA)
    repo = DocRepo(c1, clock=Clock())
    doc_id = repo.create("persisted", "a")
    repo.rename(doc_id, "persisted-2", "a")
    repo.delete(doc_id, "a")
    c2 = sqlite3.connect(path)  # інше з'єднання бачить лише закомічене
    assert c2.execute("SELECT title, deleted_at IS NOT NULL FROM docs").fetchall() == [("persisted-2", 1)]
    assert c2.execute("SELECT COUNT(*) FROM audit").fetchone()[0] == 3
    c1.close()
    c2.close()
