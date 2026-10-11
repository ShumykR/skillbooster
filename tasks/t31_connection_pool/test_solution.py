import pytest

from solution import Pool, PoolExhausted


class Conn:
    def __init__(self, n):
        self.n = n
        self.closed = False

    def close(self):
        assert not self.closed, "close() викликано двічі"
        self.closed = True


class Factory:
    def __init__(self):
        self.made = []

    def __call__(self):
        c = Conn(len(self.made) + 1)
        self.made.append(c)
        return c


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


@pytest.fixture
def factory():
    return Factory()


@pytest.fixture
def clock():
    return Clock()


def make(factory, clock, **kw):
    kw.setdefault("max_size", 2)
    kw.setdefault("max_age", 100.0)
    return Pool(factory, clock=clock, **kw)


def test_acquire_creates_connections_lazily(factory, clock):
    pool = make(factory, clock)
    assert factory.made == []
    c1 = pool.acquire()
    assert c1 is factory.made[0] and len(factory.made) == 1
    assert pool.stats() == {"in_use": 1, "idle": 0, "created": 1}


def test_release_then_acquire_reuses_connection(factory, clock):
    pool = make(factory, clock)
    c = pool.acquire()
    pool.release(c)
    assert pool.stats() == {"in_use": 0, "idle": 1, "created": 1}
    assert pool.acquire() is c
    assert len(factory.made) == 1


def test_lifo_most_recently_released_first(factory, clock):
    pool = make(factory, clock, max_size=3)
    a, b, c = pool.acquire(), pool.acquire(), pool.acquire()
    for conn in (a, b, c):
        pool.release(conn)
    assert pool.acquire() is c
    assert pool.acquire() is b


def test_exhausted_when_all_in_use(factory, clock):
    pool = make(factory, clock)
    pool.acquire()
    pool.acquire()
    with pytest.raises(PoolExhausted):
        pool.acquire()
    assert len(factory.made) == 2  # зайвого не створено


def test_release_frees_a_slot(factory, clock):
    pool = make(factory, clock)
    a = pool.acquire()
    pool.acquire()
    pool.release(a)
    assert pool.acquire() is a


def test_expired_idle_connection_is_closed_and_replaced(factory, clock):
    pool = make(factory, clock)
    old = pool.acquire()
    pool.release(old)
    clock.now = 100.0  # вік рівно max_age вважається простроченим
    fresh = pool.acquire()
    assert old.closed is True
    assert fresh is not old and fresh is factory.made[1]
    assert pool.stats() == {"in_use": 1, "idle": 0, "created": 2}


def test_not_expired_just_before_max_age(factory, clock):
    pool = make(factory, clock)
    c = pool.acquire()
    pool.release(c)
    clock.now = 99.9
    assert pool.acquire() is c
    assert c.closed is False


def test_age_counts_from_creation_not_last_use(factory, clock):
    pool = make(factory, clock)
    c = pool.acquire()
    clock.now = 60.0
    pool.release(c)
    clock.now = 70.0
    assert pool.acquire() is c  # створено на 0, вік 70
    pool.release(c)
    clock.now = 110.0
    assert pool.acquire() is not c  # вік 110 >= 100
    assert c.closed is True


def test_expired_connections_are_skipped_until_a_fresh_one_is_found(factory, clock):
    pool = make(factory, clock, max_size=3)
    old1 = pool.acquire()
    old2 = pool.acquire()
    clock.now = 90.0
    young = pool.acquire()
    for conn in (young, old1, old2):  # LIFO: першим вийде old2, потім old1, потім young
        pool.release(conn)
    clock.now = 120.0  # old1, old2 прострочені (120 >= 100), young ні (30)
    got = pool.acquire()
    assert got is young
    assert old1.closed and old2.closed and not young.closed
    assert pool.stats()["idle"] == 0


def test_expired_connection_does_not_count_against_capacity(factory, clock):
    pool = make(factory, clock)
    a, b = pool.acquire(), pool.acquire()
    pool.release(a)
    pool.release(b)
    clock.now = 500.0
    pool.acquire()
    pool.acquire()  # обидва старі закриті, створено два нові; пул не вважає себе повним
    assert pool.stats() == {"in_use": 2, "idle": 0, "created": 4}


def test_broken_release_discards_and_frees_slot(factory, clock):
    pool = make(factory, clock)
    a = pool.acquire()
    b = pool.acquire()
    pool.release(a, broken=True)
    assert a.closed is True
    assert pool.stats() == {"in_use": 1, "idle": 0, "created": 2}
    c = pool.acquire()
    assert c is not a and c is not b


def test_release_unknown_or_twice_is_value_error(factory, clock):
    pool = make(factory, clock)
    c = pool.acquire()
    pool.release(c)
    with pytest.raises(ValueError):
        pool.release(c)
    with pytest.raises(ValueError):
        pool.release(Conn(99))


def test_context_manager_releases_on_success(factory, clock):
    pool = make(factory, clock)
    with pool.connection() as conn:
        assert pool.stats()["in_use"] == 1
    assert pool.stats() == {"in_use": 0, "idle": 1, "created": 1}
    assert conn.closed is False


def test_context_manager_releases_on_ordinary_error_and_keeps_connection(factory, clock):
    pool = make(factory, clock)
    with pytest.raises(KeyError):
        with pool.connection() as conn:
            raise KeyError("boom")
    assert pool.stats() == {"in_use": 0, "idle": 1, "created": 1}
    assert conn.closed is False


def test_context_manager_discards_connection_after_connection_error(factory, clock):
    pool = make(factory, clock)
    with pytest.raises(ConnectionError):
        with pool.connection() as conn:
            raise ConnectionError("db went away")
    assert conn.closed is True
    assert pool.stats() == {"in_use": 0, "idle": 0, "created": 1}


def test_context_manager_does_not_leak_under_repeated_errors(factory, clock):
    pool = make(factory, clock)
    for _ in range(20):
        with pytest.raises(RuntimeError):
            with pool.connection():
                raise RuntimeError
    assert pool.stats()["in_use"] == 0
    assert len(factory.made) == 1


def test_close_closes_idle_and_blocks_acquire(factory, clock):
    pool = make(factory, clock)
    a, b = pool.acquire(), pool.acquire()
    pool.release(a)
    pool.close()
    assert a.closed is True and b.closed is False
    with pytest.raises(RuntimeError):
        pool.acquire()
    pool.release(b)  # зайняте закривається при поверненні
    assert b.closed is True
    assert pool.stats() == {"in_use": 0, "idle": 0, "created": 2}


def test_many_cycles_stay_within_max_size(factory, clock):
    pool = make(factory, clock, max_size=3)
    for i in range(100):
        with pool.connection():
            with pool.connection():
                pass
        clock.now += 1.0
    assert len(factory.made) <= 3 + 1  # одне оновлення після max_age=100 допускається
    assert pool.stats()["in_use"] == 0
