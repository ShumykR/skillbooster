import itertools
import re

import pytest

from solution import SessionStore


class Clock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def clock():
    return Clock()


def make(clock, idle=60, absolute=600, **kw):
    counter = itertools.count(1)
    kw.setdefault("token_fn", lambda: f"sid{next(counter)}")
    return SessionStore(clock, idle, absolute, **kw)


# --- створення й читання -------------------------------------------------------------------------

def test_create_and_get(clock):
    s = make(clock)
    sid = s.create("ann", {"theme": "dark"})
    assert s.get(sid) == {"user_id": "ann", "created_at": 1000.0, "last_seen": 1000.0, "data": {"theme": "dark"}}


def test_default_token_is_random_and_long():
    import time
    store = SessionStore(time.time, 60, 600)
    ids = {store.create(f"u{i}") for i in range(50)}
    assert len(ids) == 50
    assert all(re.fullmatch(r"[A-Za-z0-9_-]{43,}", i) for i in ids)


def test_data_is_copied_in_and_out(clock):
    s = make(clock)
    payload = {"cart": [1]}
    sid = s.create("ann", payload)
    payload["hack"] = True
    got = s.get(sid)
    got["data"]["x"] = 1
    got["user_id"] = "root"
    again = s.get(sid)
    assert again["data"] == {"cart": [1]} and again["user_id"] == "ann"


@pytest.mark.parametrize("bad", [None, 5, b"sid1", "", "nope", ["sid1"], {"a": 1}])
def test_unknown_or_non_str_ids(clock, bad):
    s = make(clock)
    s.create("ann")
    assert s.get(bad) is None
    assert s.rotate(bad) is None
    assert s.revoke(bad) is False


def test_get_refreshes_last_seen(clock):
    s = make(clock)
    sid = s.create("ann")
    clock.advance(30)
    assert s.get(sid)["last_seen"] == 1030.0
    clock.advance(30)
    assert s.get(sid)["last_seen"] == 1060.0


# --- прострочення ------------------------------------------------------------------------------------

def test_idle_timeout(clock):
    s = make(clock, idle=60)
    sid = s.create("ann")
    clock.advance(59.9)
    assert s.get(sid) is not None
    clock.advance(59.9)
    assert s.get(sid) is not None  # активність відсунула межу
    clock.advance(60)  # рівно idle_ttl від останньої активності: вже прострочена
    assert s.get(sid) is None


def test_idle_boundary_is_exclusive(clock):
    s = make(clock, idle=60)
    sid = s.create("ann")
    clock.advance(60)
    assert s.get(sid) is None


def test_absolute_timeout_cannot_be_extended_by_activity(clock):
    s = make(clock, idle=60, absolute=300)
    sid = s.create("ann")
    for _ in range(5):
        clock.advance(50)
        assert s.get(sid) is not None  # 250 с від створення, активність триває
    clock.advance(50)  # 300 від створення: абсолютний ліміт
    assert s.get(sid) is None


def test_expired_session_is_gone_for_good(clock):
    s = make(clock, idle=10)
    sid = s.create("ann")
    clock.advance(10)
    assert s.get(sid) is None
    clock.now = 1000.0  # «час назад» не воскрешає видалену сесію
    assert s.get(sid) is None


def test_expired_sessions_are_not_counted_and_cannot_be_revoked(clock):
    s = make(clock, idle=10)
    sid = s.create("ann")
    clock.advance(10)
    assert s.active_count("ann") == 0
    assert s.revoke(sid) is False


def test_active_count_does_not_touch_last_seen(clock):
    s = make(clock, idle=60)
    sid = s.create("ann")
    clock.advance(40)
    assert s.active_count("ann") == 1
    clock.advance(30)  # 70 с від створення; якби active_count оновив last_seen, сесія ще жила б
    assert s.get(sid) is None


# --- ротація (session fixation) -----------------------------------------------------------------------------

def test_rotate_issues_new_id_and_kills_the_old_one(clock):
    s = make(clock)
    old = s.create("ann", {"cart": 1})
    new = s.rotate(old)
    assert new and new != old
    assert s.get(old) is None
    assert s.get(new)["data"] == {"cart": 1}
    assert s.active_count("ann") == 1


def test_rotate_keeps_created_at_so_absolute_limit_still_applies(clock):
    s = make(clock, idle=200, absolute=200)
    old = s.create("ann")
    clock.advance(150)
    new = s.rotate(old)
    assert s.get(new)["created_at"] == 1000.0
    clock.advance(60)  # 210 від створення
    assert s.get(new) is None


def test_rotate_refreshes_idle_timer(clock):
    s = make(clock, idle=100, absolute=1000)
    old = s.create("ann")
    clock.advance(90)
    new = s.rotate(old)
    clock.advance(90)
    assert s.get(new) is not None


def test_rotate_of_expired_session_does_not_create_anything(clock):
    s = make(clock, idle=10)
    old = s.create("ann")
    clock.advance(10)
    assert s.rotate(old) is None
    assert s.active_count("ann") == 0


def test_rotate_twice_with_the_same_old_id_fails_the_second_time(clock):
    s = make(clock)
    old = s.create("ann")
    assert s.rotate(old)
    assert s.rotate(old) is None
    assert s.active_count("ann") == 1


def test_rotate_does_not_count_against_the_limit(clock):
    s = make(clock, max_per_user=2)
    a = s.create("ann")
    b = s.create("ann")
    a2 = s.rotate(a)
    assert s.get(a2) and s.get(b)


# --- відкликання ---------------------------------------------------------------------------------------------

def test_revoke(clock):
    s = make(clock)
    sid = s.create("ann")
    assert s.revoke(sid) is True
    assert s.get(sid) is None
    assert s.revoke(sid) is False


def test_revoke_user_logs_out_everywhere_and_only_that_user(clock):
    s = make(clock)
    a1, a2 = s.create("ann"), s.create("ann")
    b1 = s.create("bob")
    assert s.revoke_user("ann") == 2
    assert s.get(a1) is None and s.get(a2) is None and s.get(b1) is not None
    assert s.revoke_user("ann") == 0
    assert s.revoke_user("nobody") == 0


def test_revoke_user_does_not_count_expired(clock):
    s = make(clock, idle=10, absolute=1000)
    s.create("ann")
    clock.advance(10)
    s.create("ann")
    assert s.revoke_user("ann") == 1
    assert s.active_count("ann") == 0


# --- ліміт сесій ------------------------------------------------------------------------------------------------

def test_oldest_session_is_evicted_over_the_limit(clock):
    s = make(clock, max_per_user=3)
    ids = []
    for _ in range(3):
        ids.append(s.create("ann"))
        clock.advance(1)
    ids.append(s.create("ann"))
    assert s.get(ids[0]) is None
    assert all(s.get(i) is not None for i in ids[1:])
    assert s.active_count("ann") == 3


def test_eviction_is_by_creation_time_not_by_activity(clock):
    s = make(clock, max_per_user=2, idle=1000, absolute=5000)
    first = s.create("ann")
    clock.advance(1)
    second = s.create("ann")
    clock.advance(1)
    s.get(first)  # перша найстаріша, хай і найсвіжіша за активністю
    clock.advance(1)
    third = s.create("ann")
    assert s.get(first) is None
    assert s.get(second) and s.get(third)


def test_expired_sessions_do_not_block_new_ones_or_cause_evictions(clock):
    s = make(clock, max_per_user=2, idle=10, absolute=1000)
    s.create("ann")
    s.create("ann")
    clock.advance(5)
    keeper = s.create("ann")  # евікція найстарішої, бо дві чинні
    clock.advance(6)  # перші дві вже прострочені (11 с), keeper ще ні
    fresh = s.create("ann")
    assert s.get(keeper) and s.get(fresh)


def test_limits_are_per_user(clock):
    s = make(clock, max_per_user=1)
    a, b = s.create("ann"), s.create("bob")
    assert s.get(a) and s.get(b)


# --- колізії id та параметри ------------------------------------------------------------------------------------

def test_token_collision_never_overwrites_another_session(clock):
    ids = iter(["same", "same", "same", "other"])
    s = SessionStore(clock, 60, 600, token_fn=lambda: next(ids))
    first = s.create("ann", {"who": "ann"})
    second = s.create("bob", {"who": "bob"})
    assert (first, second) == ("same", "other")
    assert s.get("same")["data"] == {"who": "ann"}


def test_persistent_collision_raises(clock):
    s = SessionStore(clock, 60, 600, token_fn=lambda: "same")
    s.create("ann")
    with pytest.raises(RuntimeError):
        s.create("bob")
    assert s.get("same")["user_id"] == "ann"


def test_collision_on_rotate_keeps_the_session(clock):
    ids = iter(["a", "a", "b"])
    s = SessionStore(clock, 60, 600, token_fn=lambda: next(ids))
    sid = s.create("ann")
    new = s.rotate(sid)
    assert new == "b" and s.get("a") is None and s.get("b")["user_id"] == "ann"


@pytest.mark.parametrize("idle, absolute", [(0, 10), (-1, 10), (20, 10)])
def test_ttl_validation(clock, idle, absolute):
    with pytest.raises(ValueError):
        SessionStore(clock, idle, absolute)


@pytest.mark.parametrize("bad", [0, -1, 1.5, True, None])
def test_max_per_user_validation(clock, bad):
    with pytest.raises(ValueError):
        SessionStore(clock, 10, 100, max_per_user=bad)
