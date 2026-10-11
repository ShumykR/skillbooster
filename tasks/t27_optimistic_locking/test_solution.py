import sqlite3
import threading

import pytest

from solution import StaleDataError, update_title


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "docs.db")
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE docs (id INTEGER PRIMARY KEY, title TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1)")
    c.execute("INSERT INTO docs(id, title) VALUES (1, 'draft')")
    c.commit()
    c.close()
    return path


def connect(path):
    return sqlite3.connect(path, timeout=10)


def row(path):
    c = connect(path)
    try:
        return c.execute("SELECT title, version FROM docs WHERE id=1").fetchone()
    finally:
        c.close()


def test_update_increments_version(db):
    c = connect(db)
    assert update_title(c, 1, "v2", expected_version=1) == 2
    assert update_title(c, 1, "v3", expected_version=2) == 3
    assert row(db) == ("v3", 3)


def test_stale_update_is_rejected_and_data_kept(db):
    a, b = connect(db), connect(db)
    update_title(a, 1, "from A", expected_version=1)
    with pytest.raises(StaleDataError):
        update_title(b, 1, "from B", expected_version=1)
    assert row(db) == ("from A", 2)


def test_missing_document(db):
    with pytest.raises(LookupError):
        update_title(connect(db), 999, "x", expected_version=1)


def test_stale_is_not_lookup_error(db):
    update_title(connect(db), 1, "x", expected_version=1)
    with pytest.raises(StaleDataError):
        update_title(connect(db), 1, "y", expected_version=1)


def test_concurrent_writers_only_one_wins(db):
    outcomes = []
    barrier = threading.Barrier(10)

    def worker(i):
        c = connect(db)
        barrier.wait()
        try:
            update_title(c, 1, f"writer-{i}", expected_version=1)
            outcomes.append("ok")
        except StaleDataError:
            outcomes.append("stale")
        finally:
            c.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert outcomes.count("ok") == 1, outcomes
    assert outcomes.count("stale") == 9, outcomes
    assert row(db)[1] == 2
