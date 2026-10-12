import pytest

from solution import FixedWindow, SlidingWindowLog, TokenBucket, check_all, client_key, guarded_allow, rate_limit_headers


def tb(**kw):
    return TokenBucket(kw.get("rate", 2), kw.get("capacity", 5), kw.get("store"))


# ---------- TokenBucket ----------------------------------------------------------


def test_bucket_drains_then_denies_with_retry_after():
    b = tb()
    got = [b.allow("u", 0) for _ in range(5)]
    assert [d["remaining"] for d in got] == [4, 3, 2, 1, 0]
    assert [d["reset"] for d in got] == [0.5, 1.0, 1.5, 2.0, 2.5]
    assert all(d["allowed"] and d["retry_after"] == 0.0 and d["limit"] == 5 for d in got)
    denied = b.allow("u", 0)
    assert denied == {"allowed": False, "remaining": 0, "retry_after": 0.5, "limit": 5, "reset": 2.5}


def test_bucket_refills_over_time():
    b = tb()
    for _ in range(5):
        b.allow("u", 0)
    assert b.allow("u", 0.25)["allowed"] is False
    d = b.allow("u", 0.5)
    assert d["allowed"] is True and d["remaining"] == 0
    assert b.allow("u", 0.5)["allowed"] is False
    assert b.allow("u", 1.0)["allowed"] is True


def test_bucket_never_exceeds_capacity():
    b = tb()
    for _ in range(5):
        b.allow("u", 0)
    d = b.allow("u", 100)
    assert d["remaining"] == 4 and d["reset"] == 0.5


def test_bucket_cost():
    b = tb()
    assert b.allow("u", 0, cost=3)["remaining"] == 2
    d = b.allow("u", 0, cost=3)
    assert d == {"allowed": False, "remaining": 2, "retry_after": 0.5, "limit": 5, "reset": 1.5}
    assert b.allow("u", 0.5, cost=3)["allowed"] is True


def test_cost_above_capacity_never_passes():
    d = tb().allow("u", 0, cost=6)
    assert d["allowed"] is False and d["retry_after"] is None
    assert "Retry-After" not in rate_limit_headers(d)


def test_keys_are_independent_and_state_can_be_shared():
    store = {}
    a, b = tb(store=store), tb(store=store)
    for _ in range(5):
        a.allow("u", 0)
    assert b.allow("u", 0)["allowed"] is False, "другий інстанс бачить спільний стан"
    assert b.allow("other", 0)["remaining"] == 4


def test_peek_does_not_consume():
    b = tb()
    assert [b.peek("u", 0)["remaining"] for _ in range(3)] == [4, 4, 4]
    assert b.allow("u", 0)["remaining"] == 4
    for _ in range(4):
        b.allow("u", 0)
    before = dict(b.store)
    assert b.peek("u", 0)["allowed"] is False
    assert b.store == before


def test_clock_going_backwards_does_not_mint_tokens():
    b = tb()
    b.allow("u", 10)
    assert b.allow("u", 5)["remaining"] == 3


@pytest.mark.parametrize("kwargs", [dict(rate=0), dict(rate=-1), dict(capacity=0)])
def test_bucket_validation(kwargs):
    with pytest.raises(ValueError):
        tb(**kwargs)
    with pytest.raises(ValueError):
        tb().allow("u", 0, cost=0)
    with pytest.raises(ValueError):
        tb().peek("u", 0, cost=-1)


# ---------- FixedWindow and SlidingWindowLog ------------------------------------------


def test_fixed_window_counts_per_window():
    w = FixedWindow(3, 10)
    got = [w.allow("u", t) for t in (0, 1, 2)]
    assert [d["remaining"] for d in got] == [2, 1, 0] and [d["reset"] for d in got] == [10, 9, 8]
    assert w.allow("u", 3) == {"allowed": False, "remaining": 0, "retry_after": 7, "limit": 3, "reset": 7}
    d = w.allow("u", 10)
    assert d["allowed"] and d["remaining"] == 2 and d["reset"] == 10


def test_fixed_window_allows_a_double_burst_at_the_boundary():
    w = FixedWindow(3, 10)
    assert all(w.allow("u", 9)["allowed"] for _ in range(3))
    assert all(w.allow("u", 10)["allowed"] for _ in range(3)), "6 запитів за 1 секунду: слабкість фіксованого вікна"


def test_sliding_log_has_no_boundary_burst():
    w = SlidingWindowLog(3, 10)
    assert all(w.allow("u", 9)["allowed"] for _ in range(3))
    d = w.allow("u", 10)
    assert d == {"allowed": False, "remaining": 0, "retry_after": 9, "limit": 3, "reset": 9}
    assert w.allow("u", 18.999)["allowed"] is False
    after = w.allow("u", 19)
    assert after["allowed"] is True and after["remaining"] == 2, "відмова не записується в журнал; запис ts=9 уже застарів"


def test_sliding_log_retry_after_and_reset():
    w = SlidingWindowLog(2, 10)
    assert w.allow("u", 0)["reset"] == 10
    assert w.allow("u", 4)["reset"] == 10 - 4
    d = w.allow("u", 5)
    assert d["allowed"] is False and d["retry_after"] == 5 and d["reset"] == 5
    assert w.allow("u", 10)["allowed"] is True, "запис ts=0 вийшов із вікна рівно в момент 10"


def test_windows_peek_does_not_consume():
    for w in (FixedWindow(2, 10), SlidingWindowLog(2, 10)):
        assert w.peek("u", 0)["remaining"] == 1
        assert w.peek("u", 0)["remaining"] == 1
        w.allow("u", 0)
        w.allow("u", 0)
        assert w.peek("u", 0)["allowed"] is False
        assert w.allow("u", 0)["allowed"] is False


def test_windows_are_per_key():
    for w in (FixedWindow(1, 10), SlidingWindowLog(1, 10)):
        assert w.allow("a", 0)["allowed"] and w.allow("b", 0)["allowed"] and not w.allow("a", 1)["allowed"]


# ---------- headers --------------------------------------------------------------


def test_headers_for_allowed_and_denied():
    b = tb()
    assert rate_limit_headers(b.allow("u", 0)) == {"RateLimit-Limit": "5", "RateLimit-Remaining": "4", "RateLimit-Reset": "1"}
    for _ in range(4):
        b.allow("u", 0)
    h = rate_limit_headers(b.allow("u", 0))
    assert h == {"RateLimit-Limit": "5", "RateLimit-Remaining": "0", "RateLimit-Reset": "3", "Retry-After": "1"}


def test_retry_after_is_rounded_up():
    d = {"allowed": False, "remaining": 0, "retry_after": 2.2, "limit": 10, "reset": 2.2}
    assert rate_limit_headers(d)["Retry-After"] == "3"
    d["retry_after"] = 2.0
    assert rate_limit_headers(d)["Retry-After"] == "2"


# ---------- guarded_allow --------------------------------------------------------


class Broken:
    def __init__(self, exc):
        self.exc = exc

    def allow(self, key, now):
        raise self.exc


def test_fail_open_and_fail_closed():
    for exc in (ConnectionError("redis"), TimeoutError()):
        open_ = guarded_allow(Broken(exc), "u", 0)
        assert open_ == {"allowed": True, "remaining": 0, "retry_after": 0.0, "limit": None, "reset": 0.0, "degraded": True}
        closed = guarded_allow(Broken(exc), "u", 0, fail_open=False)
        assert closed["allowed"] is False and closed["retry_after"] == 1.0 and closed["degraded"] is True


def test_guard_passes_normal_decisions_and_other_errors_through():
    d = guarded_allow(FixedWindow(1, 10), "u", 0)
    assert d["allowed"] is True and "degraded" not in d
    with pytest.raises(ValueError):
        guarded_allow(Broken(ValueError("bug")), "u", 0)


# ---------- check_all ------------------------------------------------------------


def test_check_all_is_atomic():
    user = TokenBucket(1, 2)
    ip = FixedWindow(1, 10)
    first = check_all([(user, "u1"), (ip, "1.2.3.4")], 0)
    assert first["allowed"] is True and first["limit"] == 1, "повертається рішення з найменшим залишком"
    second = check_all([(user, "u1"), (ip, "1.2.3.4")], 0)
    assert second["allowed"] is False and second["retry_after"] == 10
    assert user.allow("u1", 0)["remaining"] == 0, "відмова ip не списала токен користувача: списано лише перший запит"
    assert user.allow("u1", 0)["allowed"] is False


def test_check_all_returns_the_worst_denial():
    user, ip = TokenBucket(1, 1), FixedWindow(1, 10)
    user.allow("u", 0)
    ip.allow("i", 0)
    d = check_all([(user, "u"), (ip, "i")], 0)
    assert d["allowed"] is False and d["retry_after"] == 10


def test_check_all_picks_the_smallest_remaining_with_first_on_tie():
    a, b = TokenBucket(1, 5), FixedWindow(5, 10)
    d = check_all([(a, "k"), (b, "k")], 0)
    assert d["remaining"] == 4 and d["limit"] == 5 and d["reset"] == 1.0, "перший при рівності: токени"
    d = check_all([(b, "k"), (a, "k")], 0)
    assert d["remaining"] == 3 and d["reset"] == 10, "знову рівність: першим стоїть вікно"


def test_check_all_empty():
    with pytest.raises(ValueError):
        check_all([], 0)


# ---------- client_key -----------------------------------------------------------

TRUSTED = {"10.0.0.1", "10.0.0.2"}


@pytest.mark.parametrize("headers, remote, expected", [
    ({"X-Forwarded-For": "1.2.3.4"}, "10.0.0.1", "1.2.3.4"),
    ({"x-forwarded-for": "1.2.3.4"}, "10.0.0.1", "1.2.3.4"),
    ({"X-Forwarded-For": "6.6.6.6, 1.2.3.4"}, "10.0.0.1", "1.2.3.4"),
    ({"X-Forwarded-For": "1.2.3.4, 10.0.0.2"}, "10.0.0.1", "1.2.3.4"),
    ({"X-Forwarded-For": "1.2.3.4"}, "9.9.9.9", "9.9.9.9"),
    ({}, "10.0.0.1", "10.0.0.1"),
    ({}, "9.9.9.9", "9.9.9.9"),
    ({"X-Forwarded-For": "10.0.0.2"}, "10.0.0.1", "10.0.0.2"),
    ({"X-Forwarded-For": " 1.2.3.4 ,, "}, "10.0.0.1", "1.2.3.4"),
    ({"X-Forwarded-For": "6.6.6.6, 7.7.7.7, 1.2.3.4"}, "10.0.0.1", "1.2.3.4"),
])
def test_client_key(headers, remote, expected):
    assert client_key(headers, remote, TRUSTED) == expected
