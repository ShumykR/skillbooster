import pytest

from solution import ReadRouter


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class Node:
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return f"Node({self.name})"


@pytest.fixture
def env():
    clock = Clock()
    primary, replica = Node("primary"), Node("replica")
    healthy = {"ok": True}
    router = ReadRouter(primary, replica, stick_seconds=5.0, clock=clock, replica_ok=lambda: healthy["ok"])
    return router, primary, replica, clock, healthy


def test_default_read_goes_to_replica(env):
    router, primary, replica, *_ = env
    assert router.for_read() is replica
    assert router.for_read("alice") is replica


def test_write_goes_to_primary(env):
    router, primary, *_ = env
    assert router.for_write("alice") is primary


def test_read_after_own_write_goes_to_primary(env):
    router, primary, replica, clock, _ = env
    router.for_write("alice")
    assert router.for_read("alice") is primary
    clock.advance(4.9)
    assert router.for_read("alice") is primary


def test_stickiness_ends_exactly_at_stick_seconds(env):
    router, primary, replica, clock, _ = env
    router.for_write("alice")
    clock.advance(5.0)
    assert router.for_read("alice") is replica


def test_other_users_are_not_affected(env):
    router, primary, replica, *_ = env
    router.for_write("alice")
    assert router.for_read("bob") is replica
    assert router.for_read() is replica


def test_new_write_extends_the_window(env):
    router, primary, replica, clock, _ = env
    router.for_write("alice")
    clock.advance(4.0)
    router.for_write("alice")
    clock.advance(4.0)  # від першого запису 8с, від другого 4с
    assert router.for_read("alice") is primary
    clock.advance(1.0)
    assert router.for_read("alice") is replica


def test_force_primary(env):
    router, primary, *_ = env
    assert router.for_read("nobody", force_primary=True) is primary
    assert router.for_read(force_primary=True) is primary


def test_unhealthy_replica_fails_over_to_primary(env):
    router, primary, replica, clock, healthy = env
    healthy["ok"] = False
    assert router.for_read("alice") is primary
    assert router.for_read() is primary
    healthy["ok"] = True
    assert router.for_read("alice") is replica


def test_tracked_users_counts_only_active_windows(env):
    router, _, _, clock, _ = env
    assert router.tracked_users() == 0
    router.for_write("a")
    clock.advance(3.0)
    router.for_write("b")
    assert router.tracked_users() == 2
    clock.advance(2.0)  # a: 5с (минуло), b: 2с
    assert router.tracked_users() == 1
    clock.advance(10.0)
    assert router.tracked_users() == 0


def test_expired_entries_do_not_accumulate(env):
    router, _, _, clock, _ = env
    for i in range(1000):
        router.for_write(f"user-{i}")
        clock.advance(6.0)  # кожен запис одразу простроюється
    assert router.tracked_users() == 0
    router.for_write("last")
    assert router.tracked_users() == 1


# --- інтеграційний сценарій з відстаючою реплікою ------------------------------------------

class LaggyDB:
    """primary + replica, що застосовує записи з затримкою `lag` секунд."""

    def __init__(self, clock, lag):
        self.clock = clock
        self.lag = lag
        self.primary_data = {}
        self.log = []  # (час запису, ключ, значення)

    def write(self, key, value):
        self.primary_data[key] = value
        self.log.append((self.clock(), key, value))

    def replica_get(self, key):
        visible = None
        for t, k, v in self.log:
            if k == key and self.clock() - t >= self.lag:
                visible = v
        return visible


def test_read_your_writes_with_a_lagging_replica():
    clock = Clock()
    db = LaggyDB(clock, lag=2.0)
    primary, replica = Node("primary"), Node("replica")
    router = ReadRouter(primary, replica, stick_seconds=5.0, clock=clock)

    def read(user, key):
        node = router.for_read(user)
        return db.primary_data.get(key) if node is primary else db.replica_get(key)

    router.for_write("alice")
    db.write("alice:name", "Alice v2")
    # одразу: alice бачить свій запис, інші ще можуть бачити старе (репліка відстає)
    assert read("alice", "alice:name") == "Alice v2"
    assert read("bob", "alice:name") is None
    clock.advance(2.0)
    assert read("bob", "alice:name") == "Alice v2"  # репліка наздогнала
    clock.advance(10.0)
    assert read("alice", "alice:name") == "Alice v2"  # alice вже читає з replica і теж бачить
    assert router.for_read("alice") is replica


def test_stick_window_shorter_than_lag_would_be_a_bug():
    # демонстрація: якщо stick_seconds менший за lag, користувач бачить застарілі дані
    clock = Clock()
    db = LaggyDB(clock, lag=4.0)
    primary, replica = Node("primary"), Node("replica")
    router = ReadRouter(primary, replica, stick_seconds=1.0, clock=clock)
    router.for_write("alice")
    db.write("k", "new")
    clock.advance(1.0)
    node = router.for_read("alice")
    assert node is replica and db.replica_get("k") is None
