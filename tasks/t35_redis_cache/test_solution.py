import json

import pytest

from solution import CacheError, UserService


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class FakeCache:
    """Поводиться як Redis: лише рядки, TTL, може «впасти»."""

    def __init__(self, clock, calls):
        self.clock = clock
        self.calls = calls
        self.store = {}  # key -> (value, expires_at)
        self.down = False
        self.last_ttl = {}

    def _check(self):
        if self.down:
            raise CacheError("redis is down")

    def get(self, key):
        self.calls.append(("cache.get", key))
        self._check()
        item = self.store.get(key)
        if item is None:
            return None
        value, expires = item
        if self.clock() >= expires:
            del self.store[key]
            return None
        return value

    def set(self, key, value, ttl):
        self.calls.append(("cache.set", key))
        self._check()
        assert isinstance(value, str), "Redis зберігає лише рядки: серіалізуй у JSON"
        assert isinstance(ttl, int) and ttl > 0, "потрібен додатний цілий TTL у секундах"
        self.store[key] = (value, self.clock() + ttl)
        self.last_ttl[key] = ttl

    def delete(self, key):
        self.calls.append(("cache.delete", key))
        self._check()
        self.store.pop(key, None)


class FakeDB:
    def __init__(self, calls):
        self.calls = calls
        self.rows = {}
        self.loads = 0

    def load(self, user_id):
        self.calls.append(("db.load", user_id))
        self.loads += 1
        row = self.rows.get(user_id)
        return dict(row) if row is not None else None

    def save(self, user_id, data):
        self.calls.append(("db.save", user_id))
        self.rows[user_id] = dict(data)


@pytest.fixture
def env():
    clock = Clock()
    calls = []
    db = FakeDB(calls)
    cache = FakeCache(clock, calls)
    db.rows["u1"] = {"name": "Оксана", "plan": "pro"}
    return UserService(db, cache, ttl=60, negative_ttl=5), db, cache, clock, calls


def test_miss_loads_from_db_and_fills_cache(env):
    svc, db, cache, *_ = env
    assert svc.get_user("u1") == {"name": "Оксана", "plan": "pro"}
    assert db.loads == 1
    assert json.loads(cache.store["user:u1"][0]) == {"name": "Оксана", "plan": "pro"}
    assert cache.last_ttl["user:u1"] == 60


def test_hit_does_not_touch_db(env):
    svc, db, *_ = env
    svc.get_user("u1")
    for _ in range(5):
        assert svc.get_user("u1") == {"name": "Оксана", "plan": "pro"}
    assert db.loads == 1


def test_ttl_expiry_reloads_from_db(env):
    svc, db, cache, clock, _ = env
    svc.get_user("u1")
    clock.now = 59.9
    svc.get_user("u1")
    assert db.loads == 1
    db.rows["u1"]["plan"] = "free"  # змінили в обхід сервісу
    clock.now = 60.0
    assert svc.get_user("u1")["plan"] == "free"
    assert db.loads == 2


def test_cached_value_is_json_string_not_python_object(env):
    svc, _, cache, *_ = env
    svc.get_user("u1")
    raw = cache.store["user:u1"][0]
    assert isinstance(raw, str) and json.loads(raw)["name"] == "Оксана"


def test_returned_dict_from_cache_is_independent_copy(env):
    svc, *_ = env
    first = svc.get_user("u1")
    first["plan"] = "hacked"
    assert svc.get_user("u1")["plan"] == "pro"


def test_negative_caching_for_unknown_user(env):
    svc, db, cache, clock, _ = env
    assert svc.get_user("ghost") is None
    assert svc.get_user("ghost") is None
    assert svc.get_user("ghost") is None
    assert db.loads == 1
    assert cache.last_ttl["user:ghost"] == 5
    clock.now = 5.0
    assert svc.get_user("ghost") is None
    assert db.loads == 2


def test_negative_entry_does_not_hide_a_user_created_later(env):
    svc, db, cache, clock, _ = env
    assert svc.get_user("new") is None
    db.rows["new"] = {"name": "Новий"}
    clock.now = 5.0
    assert svc.get_user("new") == {"name": "Новий"}


def test_update_saves_then_invalidates_in_that_order(env):
    svc, db, cache, clock, calls = env
    svc.get_user("u1")
    calls.clear()
    svc.update_user("u1", {"name": "Оксана", "plan": "free"})
    assert calls == [("db.save", "u1"), ("cache.delete", "user:u1")]


def test_update_never_writes_the_cache(env):
    svc, db, cache, _, calls = env
    svc.update_user("u1", {"name": "X"})
    assert not any(c[0] == "cache.set" for c in calls)
    assert "user:u1" not in cache.store


def test_read_after_update_sees_new_data(env):
    svc, db, *_ = env
    svc.get_user("u1")
    svc.update_user("u1", {"name": "Оксана", "plan": "free"})
    assert svc.get_user("u1") == {"name": "Оксана", "plan": "free"}
    assert db.loads == 2


def test_update_also_clears_negative_entry(env):
    svc, db, *_ = env
    assert svc.get_user("fresh") is None
    svc.update_user("fresh", {"name": "Just created"})
    assert svc.get_user("fresh") == {"name": "Just created"}


def test_keys_are_per_user(env):
    svc, db, *_ = env
    db.rows["u2"] = {"name": "Іван"}
    assert svc.get_user("u1")["name"] == "Оксана"
    assert svc.get_user("u2")["name"] == "Іван"
    svc.update_user("u2", {"name": "Іван Новий"})
    assert svc.get_user("u1")["name"] == "Оксана"
    assert db.loads == 2  # u1 лишився в кеші


def test_cache_down_reads_fall_back_to_db(env):
    svc, db, cache, *_ = env
    cache.down = True
    assert svc.get_user("u1") == {"name": "Оксана", "plan": "pro"}
    assert svc.get_user("u1") == {"name": "Оксана", "plan": "pro"}
    assert db.loads == 2
    assert svc.get_user("ghost") is None


def test_cache_down_update_still_saves(env):
    svc, db, cache, *_ = env
    cache.down = True
    svc.update_user("u1", {"name": "Z"})  # без винятку
    assert db.rows["u1"] == {"name": "Z"}


def test_cache_recovers_after_outage(env):
    svc, db, cache, *_ = env
    cache.down = True
    svc.get_user("u1")
    cache.down = False
    svc.get_user("u1")
    svc.get_user("u1")
    assert db.loads == 2  # після відновлення кеш знову заповнився
    assert "user:u1" in cache.store


def test_non_cache_errors_are_not_swallowed(env):
    svc, db, *_ = env

    def broken_load(user_id):
        raise ValueError("db exploded")

    db.load = broken_load
    with pytest.raises(ValueError):
        svc.get_user("u1")


def test_unicode_and_nested_data_roundtrip(env):
    svc, db, *_ = env
    payload = {"name": "Їжак", "tags": ["a", "б"], "address": {"city": "Київ", "zip": None}}
    db.rows["u9"] = payload
    assert svc.get_user("u9") == payload
    assert svc.get_user("u9") == payload
    assert db.loads == 1
