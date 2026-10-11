import pytest

from solution import LoginThrottle


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def clock():
    return Clock()


def make(clock, **kw):
    kw.setdefault("max_failures", 3)
    kw.setdefault("window", 60.0)
    kw.setdefault("lockout", 300.0)
    return LoginThrottle(clock=clock, **kw)


def test_fresh_key_is_allowed(clock):
    assert make(clock).check("alice") == (True, 0.0)


def test_locks_after_max_failures(clock):
    t = make(clock)
    for _ in range(2):
        t.record_failure("alice")
        assert t.check("alice")[0] is True
    t.record_failure("alice")
    allowed, retry = t.check("alice")
    assert allowed is False
    assert retry == pytest.approx(300.0)


def test_retry_after_counts_down_and_unlocks_exactly_at_the_end(clock):
    t = make(clock)
    for _ in range(3):
        t.record_failure("a")
    clock.advance(100)
    allowed, retry = t.check("a")
    assert not allowed and retry == pytest.approx(200.0)
    clock.advance(199.9)
    assert t.check("a")[0] is False
    clock.advance(0.1)
    assert t.check("a") == (True, 0.0)


def test_counter_resets_after_lockout(clock):
    t = make(clock)
    for _ in range(3):
        t.record_failure("a")
    clock.advance(300)
    t.record_failure("a")
    t.record_failure("a")
    assert t.check("a")[0] is True  # лише 2 нові невдачі, а не 3
    t.record_failure("a")
    assert t.check("a")[0] is False


def test_old_failures_leave_the_window(clock):
    t = make(clock)
    t.record_failure("a")
    t.record_failure("a")
    clock.advance(61)
    t.record_failure("a")
    assert t.check("a")[0] is True
    t.record_failure("a")
    t.record_failure("a")
    assert t.check("a")[0] is False


def test_failure_exactly_at_window_edge_is_expired(clock):
    t = make(clock)
    t.record_failure("a")
    t.record_failure("a")
    clock.advance(60)
    t.record_failure("a")
    assert t.check("a")[0] is True


def test_success_resets_failures(clock):
    t = make(clock)
    t.record_failure("a")
    t.record_failure("a")
    t.record_success("a")
    t.record_failure("a")
    t.record_failure("a")
    assert t.check("a")[0] is True


def test_success_during_lockout_does_not_unlock(clock):
    t = make(clock)
    for _ in range(3):
        t.record_failure("a")
    t.record_success("a")
    assert t.check("a")[0] is False


def test_failures_during_lockout_do_not_extend_it(clock):
    t = make(clock)
    for _ in range(3):
        t.record_failure("a")
    clock.advance(100)
    for _ in range(10):
        t.record_failure("a")
    allowed, retry = t.check("a")
    assert not allowed and retry == pytest.approx(200.0)
    clock.advance(200)
    assert t.check("a")[0] is True
    t.record_failure("a")
    t.record_failure("a")
    assert t.check("a")[0] is True  # невдачі під час локауту не накопичились


def test_keys_are_independent(clock):
    t = make(clock)
    for _ in range(3):
        t.record_failure("alice")
    assert t.check("alice")[0] is False
    assert t.check("bob") == (True, 0.0)
    t.record_failure("bob")
    t.record_success("alice")  # alice у локауті, нічого не мінялось
    assert t.check("bob")[0] is True


def test_default_parameters():
    t = LoginThrottle(clock=Clock())
    for _ in range(4):
        t.record_failure("x")
    assert t.check("x")[0] is True
    t.record_failure("x")
    assert t.check("x") == (False, pytest.approx(900.0))
