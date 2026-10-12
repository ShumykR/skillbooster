import pytest

from solution import ResilientCache


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class Backend:
    """Redis, у якого можна «вбити» get/set і додати затримку."""

    def __init__(self):
        self.data = {}
        self.fail_get = False
        self.fail_set = False
        self.latency = 0.0
        self.calls = []

    def _enter(self, op, key, timeout):
        self.calls.append((op, key, timeout))
        if self.latency and (timeout is None or self.latency > timeout):
            raise TimeoutError("redis timeout")

    def get(self, key, timeout=None):
        self._enter("get", key, timeout)
        if self.fail_get:
            raise ConnectionError("redis down")
        return self.data.get(key)

    def set(self, key, value, ttl=None, timeout=None):
        self._enter("set", key, timeout)
        if self.fail_set:
            raise ConnectionError("redis down")
        self.data[key] = value


class Db:
    def __init__(self):
        self.calls = []

    def __call__(self, key):
        self.calls.append(key)
        return None if key == "missing" else f"db:{key}"


@pytest.fixture
def env():
    clock, backend, db = Clock(), Backend(), Db()
    cache = ResilientCache(backend, db, clock=clock, ttl=60, timeout=0.1, failure_threshold=3, reset_timeout=30)
    return clock, backend, db, cache


def kill(backend):
    backend.fail_get = backend.fail_set = True


def revive(backend):
    backend.fail_get = backend.fail_set = False


# ---------- normal operation -----------------------------------------------------


def test_miss_loads_from_the_source_and_fills_the_cache(env):
    clock, backend, db, cache = env
    assert cache.get("a") == "db:a"
    assert cache.get("a") == "db:a"
    assert db.calls == ["a"]
    assert backend.data == {"a": "db:a"}
    assert cache.metrics == {"hits": 1, "misses": 1, "errors": 0, "fallbacks": 0, "short_circuited": 0}
    assert cache.state == "closed"


def test_every_backend_call_gets_a_timeout_and_set_gets_ttl(env):
    _, backend, _, cache = env
    cache.get("a")
    cache.get("a")
    assert backend.calls == [("get", "a", 0.1), ("set", "a", 0.1), ("get", "a", 0.1)]
    other_backend = Backend()
    custom = ResilientCache(other_backend, Db(), clock=Clock(), ttl=5, timeout=0.25)
    custom.get("k")
    assert [c[2] for c in other_backend.calls] == [0.25, 0.25]


def test_ttl_is_passed_to_set():
    seen = {}

    class B(Backend):
        def set(self, key, value, ttl=None, timeout=None):
            seen["ttl"] = ttl
            super().set(key, value, ttl, timeout)

    ResilientCache(B(), Db(), clock=Clock(), ttl=123).get("k")
    assert seen["ttl"] == 123


def test_none_from_the_loader_is_not_cached(env):
    _, backend, db, cache = env
    assert cache.get("missing") is None
    assert cache.get("missing") is None
    assert db.calls == ["missing", "missing"] and backend.data == {}


def test_loader_errors_are_not_swallowed(env):
    clock, backend, _, _ = env

    def boom(key):
        raise RuntimeError("db is down")

    cache = ResilientCache(backend, boom, clock=clock)
    with pytest.raises(RuntimeError):
        cache.get("a")
    kill(backend)
    with pytest.raises(RuntimeError):
        cache.get("a")


def test_unexpected_backend_exceptions_are_bugs_and_propagate(env):
    clock, backend, db, cache = env

    def bad_get(key, timeout=None):
        raise ValueError("serialization bug")

    backend.get = bad_get
    with pytest.raises(ValueError):
        cache.get("a")
    assert cache.metrics["errors"] == 0 and cache.state == "closed"


# ---------- Redis is killed ------------------------------------------------------


def test_requests_keep_working_when_the_backend_is_down(env):
    _, backend, db, cache = env
    kill(backend)
    assert [cache.get(k) for k in ("a", "b")] == ["db:a", "db:b"]
    assert cache.metrics == {"hits": 0, "misses": 0, "errors": 2, "fallbacks": 2, "short_circuited": 0}
    assert cache.state == "closed", "поки помилок менше за поріг"


def test_breaker_opens_after_threshold_and_stops_calling_the_backend(env):
    clock, backend, db, cache = env
    kill(backend)
    for _ in range(3):
        cache.get("a")
    assert cache.state == "open"
    calls_before = len(backend.calls)
    assert [cache.get("a") for _ in range(5)] == ["db:a"] * 5
    assert len(backend.calls) == calls_before, "у стані open Redis не чіпаємо"
    assert len(db.calls) == 8
    assert cache.metrics["short_circuited"] == 5 and cache.metrics["fallbacks"] == 3 and cache.metrics["errors"] == 3


def test_success_resets_the_failure_streak(env):
    _, backend, _, cache = env
    for _ in range(2):
        backend.fail_get = True
        cache.get("a")
        cache.get("a")
        backend.fail_get = False
        cache.get("a")  # успіх: серія обнуляється
    assert cache.state == "closed"
    assert cache.metrics["errors"] == 4


def test_custom_threshold(env):
    clock, backend, db, _ = env
    cache = ResilientCache(backend, db, clock=clock, failure_threshold=1)
    kill(backend)
    cache.get("a")
    assert cache.state == "open"


def test_timeouts_count_as_failures_but_fast_enough_calls_do_not(env):
    _, backend, _, cache = env
    backend.latency = 0.1
    cache.get("a")
    assert cache.metrics["errors"] == 0, "рівно timeout: ще встигає"
    backend.latency = 0.5
    assert cache.get("b") == "db:b"
    assert cache.metrics["errors"] == 1 and cache.metrics["fallbacks"] == 1


def test_set_failure_does_not_break_the_request(env):
    _, backend, db, cache = env
    backend.fail_set = True
    assert cache.get("a") == "db:a"
    assert cache.metrics == {"hits": 0, "misses": 1, "errors": 1, "fallbacks": 0, "short_circuited": 0}
    assert "a" not in backend.data


# ---------- recovery ---------------------------------------------------------------


def open_breaker(env):
    clock, backend, db, cache = env
    kill(backend)
    for _ in range(3):
        cache.get("a")
    assert cache.state == "open"


def test_open_until_reset_timeout_then_half_open(env):
    clock, *_ = env
    cache = env[3]
    open_breaker(env)
    clock.now += 29.99
    assert cache.state == "open"
    clock.now += 0.01
    assert cache.state == "half-open", "рівно reset_timeout: пробний запит дозволений"


def test_half_open_success_closes_the_breaker(env):
    clock, backend, db, cache = env
    open_breaker(env)
    revive(backend)
    clock.now += 30
    assert cache.get("a") == "db:a"
    assert cache.state == "closed"
    assert cache.get("a") == "db:a"
    assert cache.metrics["hits"] == 1
    # серія почалась заново: два нових збої не відкривають breaker
    kill(backend)
    cache.get("x")
    cache.get("y")
    assert cache.state == "closed"


def test_half_open_failure_reopens_for_a_full_timeout(env):
    clock, backend, db, cache = env
    open_breaker(env)
    clock.now += 30
    cache.get("a")  # Redis досі мертвий
    assert cache.state == "open"
    clock.now += 29.9
    assert cache.state == "open", "відлік reset_timeout почався заново"
    calls = len(backend.calls)
    cache.get("a")
    assert len(backend.calls) == calls
    clock.now += 0.1
    assert cache.state == "half-open"


def test_half_open_probe_hits_the_backend_once_per_call(env):
    clock, backend, db, cache = env
    open_breaker(env)
    clock.now += 30
    calls = len(backend.calls)
    cache.get("a")
    assert len(backend.calls) == calls + 1


def test_half_open_get_success_closes_even_if_the_following_set_fails(env):
    clock, backend, db, cache = env
    open_breaker(env)
    revive(backend)
    backend.fail_set = True
    clock.now += 30
    assert cache.get("zzz") == "db:zzz"  # get ок (промах) закрив breaker, set впав: це перша помилка нової серії
    assert cache.state == "closed"
    assert cache.metrics["errors"] == 4


def test_full_chaos_scenario(env):
    clock, backend, db, cache = env
    assert cache.get("a") == "db:a"          # прогріли кеш
    kill(backend)
    results = [cache.get("a") for _ in range(10)]
    assert results == ["db:a"] * 10, "жодної помилки для користувача"
    assert cache.state == "open"
    assert len([c for c in backend.calls if c[0] == "get"]) == 1 + 3, "після відкриття Redis не мучимо"
    revive(backend)
    clock.now += 31
    assert cache.get("a") == "db:a" and cache.state == "closed"
    assert cache.get("a") == "db:a"
    assert cache.metrics["hits"] >= 1
