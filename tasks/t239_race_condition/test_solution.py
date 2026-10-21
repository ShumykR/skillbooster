import importlib.util
import itertools
import sqlite3
import threading
from pathlib import Path

import pytest

SOLUTION = Path(__file__).with_name("solution.py")
_counter = itertools.count()


def load_instance():
    """Незалежна копія модуля: імітує окремий воркер (власні глобальні змінні й Lock)."""
    spec = importlib.util.spec_from_file_location(f"solution_worker_{next(_counter)}", SOLUTION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "shop.db")
    conn = sqlite3.connect(path, timeout=10)
    load_instance().init_db(conn)
    conn.execute("INSERT INTO promo VALUES ('SALE', 3, 0)")
    conn.execute("INSERT INTO promo VALUES ('ONE', 1, 0)")
    conn.execute("INSERT INTO accounts VALUES (1, 100)")
    conn.execute("INSERT INTO accounts VALUES (2, 5)")
    conn.commit()
    conn.close()
    return path


def query(path, sql, *args):
    c = sqlite3.connect(path, timeout=10)
    try:
        return c.execute(sql, args).fetchall()
    finally:
        c.close()


def run_concurrently(path, n, call):
    """Запускає n «воркерів»; у `pause` усі чекають один одного (гонка відтворюється щоразу)."""
    barrier = threading.Barrier(n)

    def pause():
        try:
            barrier.wait(timeout=0.3)
        except threading.BrokenBarrierError:
            pass  # рішення із блокуванням: інші потоки чекають на замок, це нормально

    results = [None] * n
    errors = []

    def worker(i):
        try:
            mod = load_instance()
            conn = sqlite3.connect(path, timeout=10)
            try:
                results[i] = call(mod, conn, i, pause)
            finally:
                conn.close()
        except Exception as e:  # noqa: BLE001
            errors.append(repr(e))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not any(t.is_alive() for t in threads), "потік завис"
    assert not errors, errors
    return results


# --- послідовна поведінка ----------------------------------------------------------------------

def test_redeem_basic_sequence(db_path):
    mod = load_instance()
    conn = sqlite3.connect(db_path, timeout=10)
    assert mod.redeem_promo(conn, "SALE", 1) is True
    assert mod.redeem_promo(conn, "SALE", 1) is False  # той самий користувач
    assert mod.redeem_promo(conn, "SALE", 2) is True
    assert mod.redeem_promo(conn, "SALE", 3) is True
    assert mod.redeem_promo(conn, "SALE", 4) is False  # ліміт
    conn.close()
    assert query(db_path, "SELECT used FROM promo WHERE code='SALE'") == [(3,)]
    assert query(db_path, "SELECT COUNT(*) FROM redemptions WHERE code='SALE'") == [(3,)]


def test_redeem_unknown_code(db_path):
    mod = load_instance()
    conn = sqlite3.connect(db_path)
    with pytest.raises(LookupError):
        mod.redeem_promo(conn, "NOPE", 1)
    conn.close()
    assert query(db_path, "SELECT COUNT(*) FROM redemptions") == [(0,)]


def test_charge_basic_sequence(db_path):
    mod = load_instance()
    conn = sqlite3.connect(db_path, timeout=10)
    assert mod.charge(conn, 1, 30) is True
    assert mod.charge(conn, 1, 70) is True
    assert mod.charge(conn, 1, 1) is False
    assert mod.charge(conn, 2, 6) is False
    assert mod.charge(conn, 2, 5) is True
    conn.close()
    assert query(db_path, "SELECT id, balance FROM accounts ORDER BY id") == [(1, 0), (2, 0)]


def test_charge_unknown_account(db_path):
    mod = load_instance()
    conn = sqlite3.connect(db_path)
    with pytest.raises(LookupError):
        mod.charge(conn, 99, 10)
    conn.close()


@pytest.mark.parametrize("amount", [0, -1, -100, 1.5, "10", None, True])
def test_charge_rejects_bad_amount_and_keeps_balance(db_path, amount):
    mod = load_instance()
    conn = sqlite3.connect(db_path)
    with pytest.raises(ValueError):
        mod.charge(conn, 1, amount)
    conn.close()
    assert query(db_path, "SELECT balance FROM accounts WHERE id=1") == [(100,)]


# --- гонки -------------------------------------------------------------------------------------

def test_promo_limit_holds_under_concurrency(db_path):
    n = 12
    results = run_concurrently(db_path, n, lambda mod, conn, i, pause: mod.redeem_promo(conn, "SALE", 100 + i, pause))
    assert sum(1 for r in results if r is True) == 3
    assert sum(1 for r in results if r is False) == n - 3
    assert query(db_path, "SELECT used FROM promo WHERE code='SALE'") == [(3,)]
    assert query(db_path, "SELECT COUNT(*) FROM redemptions WHERE code='SALE'") == [(3,)]


def test_single_use_promo_only_one_winner(db_path):
    results = run_concurrently(db_path, 8, lambda mod, conn, i, pause: mod.redeem_promo(conn, "ONE", i, pause))
    assert results.count(True) == 1
    assert query(db_path, "SELECT used FROM promo WHERE code='ONE'") == [(1,)]
    assert query(db_path, "SELECT COUNT(*) FROM redemptions WHERE code='ONE'") == [(1,)]


def test_same_user_double_click_counts_once(db_path):
    results = run_concurrently(db_path, 6, lambda mod, conn, i, pause: mod.redeem_promo(conn, "SALE", 7, pause))
    assert results.count(True) == 1
    assert query(db_path, "SELECT used FROM promo WHERE code='SALE'") == [(1,)]
    assert query(db_path, "SELECT COUNT(*) FROM redemptions WHERE code='SALE' AND user_id=7") == [(1,)]


def test_balance_never_negative_under_concurrency(db_path):
    results = run_concurrently(db_path, 10, lambda mod, conn, i, pause: mod.charge(conn, 1, 30, pause))
    assert results.count(True) == 3
    assert results.count(False) == 7
    assert query(db_path, "SELECT balance FROM accounts WHERE id=1") == [(10,)]


def test_concurrent_charges_that_all_fit_are_all_applied(db_path):
    results = run_concurrently(db_path, 10, lambda mod, conn, i, pause: mod.charge(conn, 1, 10, pause))
    assert results.count(True) == 10
    assert query(db_path, "SELECT balance FROM accounts WHERE id=1") == [(0,)]


def test_mixed_redeem_and_charge_stay_independent(db_path):
    def call(mod, conn, i, pause):
        if i % 2:
            return ("promo", mod.redeem_promo(conn, "ONE", i, pause))
        return ("charge", mod.charge(conn, 1, 60, pause))

    results = run_concurrently(db_path, 8, call)
    assert [r for k, r in results if k == "promo"].count(True) == 1
    assert [r for k, r in results if k == "charge"].count(True) == 1
    assert query(db_path, "SELECT balance FROM accounts WHERE id=1") == [(40,)]
