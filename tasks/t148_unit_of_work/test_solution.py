import sqlite3

import pytest

from solution import InsufficientFunds, UnitOfWork, transfer


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "bank.db")
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE accounts (id TEXT PRIMARY KEY, owner TEXT NOT NULL, balance INTEGER NOT NULL)")
    c.execute("CREATE TABLE audit (id INTEGER PRIMARY KEY AUTOINCREMENT, message TEXT NOT NULL)")
    c.executemany("INSERT INTO accounts VALUES (?, ?, ?)", [("A", "Ann", 100), ("B", "Bob", 50)])
    c.commit()
    c.close()

    opened = []

    def connect():
        conn = sqlite3.connect(path)
        opened.append(conn)
        return conn

    connect.path = path
    connect.opened = opened
    return connect


def snapshot(db):
    """Стан, який бачить НЕЗАЛЕЖНЕ з'єднання (тобто лише зафіксоване)."""
    c = sqlite3.connect(db.path)
    try:
        return (
            dict(c.execute("SELECT id, balance FROM accounts").fetchall()),
            [r[0] for r in c.execute("SELECT message FROM audit ORDER BY id")],
        )
    finally:
        c.close()


class Boom(Exception):
    pass


# --- UnitOfWork -------------------------------------------------------------------------------

def test_commit_persists_changes_of_both_repositories(db):
    with UnitOfWork(db) as uow:
        uow.accounts.add("C", "Cid", 10)
        uow.audit.add("created C")
        uow.commit()
    balances, audit = snapshot(db)
    assert balances["C"] == 10
    assert audit == ["created C"]


def test_leaving_without_commit_rolls_back(db):
    with UnitOfWork(db) as uow:
        uow.accounts.add("C", "Cid", 10)
        uow.audit.add("created C")
    assert snapshot(db) == ({"A": 100, "B": 50}, [])


def test_exception_rolls_back_and_propagates(db):
    with pytest.raises(Boom):
        with UnitOfWork(db) as uow:
            uow.accounts.set_balance("A", 1)
            uow.commit()  # навіть після commit пізніший виняток не відкочує вже зафіксоване
            uow.accounts.set_balance("B", 2)
            raise Boom()
    assert snapshot(db)[0] == {"A": 1, "B": 50}


def test_explicit_rollback_discards_pending_changes(db):
    with UnitOfWork(db) as uow:
        uow.accounts.set_balance("A", 7)
        uow.rollback()
        uow.audit.add("after rollback")
        uow.commit()
    assert snapshot(db) == ({"A": 100, "B": 50}, ["after rollback"])


def test_uncommitted_changes_are_visible_inside_but_not_outside(db):
    with UnitOfWork(db) as uow:
        uow.accounts.set_balance("A", 5)
        assert uow.accounts.get("A")["balance"] == 5
        assert snapshot(db)[0]["A"] == 100
        uow.commit()
    assert snapshot(db)[0]["A"] == 5


def test_repositories_share_one_connection_and_one_transaction(db):
    with UnitOfWork(db) as uow:
        assert uow.accounts.conn is uow.audit.conn
        assert len(db.opened) == 1


def test_connection_is_closed_after_exit(db):
    with UnitOfWork(db) as uow:
        uow.commit()
    with pytest.raises(sqlite3.ProgrammingError):
        db.opened[0].execute("SELECT 1")


def test_connection_is_closed_even_on_exception(db):
    with pytest.raises(Boom):
        with UnitOfWork(db):
            raise Boom()
    with pytest.raises(sqlite3.ProgrammingError):
        db.opened[0].execute("SELECT 1")


def test_repositories_are_unavailable_outside_with(db):
    uow = UnitOfWork(db)
    with pytest.raises(RuntimeError):
        uow.accounts
    with pytest.raises(RuntimeError):
        uow.audit
    with uow:
        uow.accounts
    with pytest.raises(RuntimeError):
        uow.accounts


def test_object_can_be_reused_as_a_fresh_unit(db):
    uow = UnitOfWork(db)
    with uow:
        uow.accounts.set_balance("A", 1)
        uow.commit()
    with uow:
        assert uow.accounts.get("A")["balance"] == 1
        uow.accounts.set_balance("A", 2)
    assert snapshot(db)[0]["A"] == 1
    assert len(db.opened) == 2


# --- репозиторії -----------------------------------------------------------------------------

def test_account_repo_get(db):
    with UnitOfWork(db) as uow:
        assert uow.accounts.get("A") == {"id": "A", "owner": "Ann", "balance": 100}
        assert uow.accounts.get("nope") is None


def test_set_balance_of_missing_account(db):
    with UnitOfWork(db) as uow:
        with pytest.raises(LookupError):
            uow.accounts.set_balance("nope", 1)


def test_audit_keeps_insertion_order(db):
    with UnitOfWork(db) as uow:
        for m in ["one", "two", "three"]:
            uow.audit.add(m)
        assert uow.audit.all() == ["one", "two", "three"]


def test_values_are_parameters_not_sql(db):
    with UnitOfWork(db) as uow:
        uow.audit.add("x'); DROP TABLE accounts; --")
        uow.accounts.add("D", "O'Neil", 1)
        uow.commit()
    balances, audit = snapshot(db)
    assert "D" in balances and audit == ["x'); DROP TABLE accounts; --"]


# --- transfer --------------------------------------------------------------------------------

def test_transfer_moves_money_and_writes_audit(db):
    transfer(db, "A", "B", 30)
    balances, audit = snapshot(db)
    assert balances == {"A": 70, "B": 80}
    assert len(audit) == 1 and audit[0]


def test_transfer_whole_balance_is_allowed(db):
    transfer(db, "A", "B", 100)
    assert snapshot(db)[0] == {"A": 0, "B": 150}


def test_insufficient_funds_leaves_no_trace(db):
    with pytest.raises(InsufficientFunds):
        transfer(db, "A", "B", 101)
    assert snapshot(db) == ({"A": 100, "B": 50}, [])


def test_missing_destination_rolls_back_the_debit(db):
    with pytest.raises(LookupError):
        transfer(db, "A", "ghost", 10)
    assert snapshot(db) == ({"A": 100, "B": 50}, [])


def test_missing_source(db):
    with pytest.raises(LookupError):
        transfer(db, "ghost", "B", 10)
    assert snapshot(db) == ({"A": 100, "B": 50}, [])


@pytest.mark.parametrize("amount", [0, -5, 1.5, "10", None, True])
def test_invalid_amount(db, amount):
    with pytest.raises(ValueError):
        transfer(db, "A", "B", amount)
    assert snapshot(db) == ({"A": 100, "B": 50}, [])


def test_transfer_to_self_changes_nothing(db):
    try:
        transfer(db, "A", "A", 10)
    except ValueError:
        pass
    assert snapshot(db)[0] == {"A": 100, "B": 50}


def test_failure_after_debit_is_atomic_with_audit(db):
    # зламаний аудит (таблицю прибрано) не повинен лишити «списання без запису»
    c = sqlite3.connect(db.path)
    c.execute("DROP TABLE audit")
    c.commit()
    c.close()
    with pytest.raises(sqlite3.Error):
        transfer(db, "A", "B", 10)
    c = sqlite3.connect(db.path)
    assert dict(c.execute("SELECT id, balance FROM accounts").fetchall()) == {"A": 100, "B": 50}
    c.close()
