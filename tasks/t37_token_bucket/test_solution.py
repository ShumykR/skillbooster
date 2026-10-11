import threading

import pytest

from solution import TokenBucket


class FakeClock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


def test_burst_then_deny():
    clock = FakeClock()
    tb = TokenBucket(capacity=3, refill_per_sec=1, clock=clock)
    assert [tb.allow("u") for _ in range(4)] == [True, True, True, False]


def test_refill_over_time():
    clock = FakeClock()
    tb = TokenBucket(3, 1, clock=clock)
    for _ in range(3):
        tb.allow("u")
    assert not tb.allow("u")
    clock.advance(1)
    assert tb.allow("u")
    assert not tb.allow("u")


def test_refill_is_capped_at_capacity():
    clock = FakeClock()
    tb = TokenBucket(2, 1, clock=clock)
    clock.advance(1000)
    assert [tb.allow("u") for _ in range(3)] == [True, True, False]


def test_keys_are_independent():
    tb = TokenBucket(1, 1, clock=FakeClock())
    assert tb.allow("a")
    assert not tb.allow("a")
    assert tb.allow("b")


def test_cost_and_fractional_refill():
    clock = FakeClock()
    tb = TokenBucket(10, 2, clock=clock)
    assert tb.allow("u", cost=10)
    assert not tb.allow("u", cost=1)
    clock.advance(0.25)  # +0.5 токена
    assert not tb.allow("u")
    clock.advance(0.25)  # разом 1 токен
    assert tb.allow("u")


def test_retry_after():
    clock = FakeClock()
    tb = TokenBucket(2, 4, clock=clock)
    tb.allow("u", 2)
    assert tb.retry_after("u") == pytest.approx(0.25)
    assert tb.retry_after("u", cost=2) == pytest.approx(0.5)
    clock.advance(1)
    assert tb.retry_after("u") == 0.0


def test_denied_request_does_not_consume_tokens():
    clock = FakeClock()
    tb = TokenBucket(2, 1, clock=clock)
    tb.allow("u", 2)
    assert not tb.allow("u", 2)
    clock.advance(1)
    assert tb.allow("u", 1)


def test_cost_above_capacity_never_allowed():
    tb = TokenBucket(2, 1, clock=FakeClock())
    assert not tb.allow("u", cost=3)
    assert tb.retry_after("u", cost=3) == float("inf")


def test_thread_safety_under_contention():
    tb = TokenBucket(capacity=10, refill_per_sec=0, clock=FakeClock())
    results = []
    barrier = threading.Barrier(50)

    def worker():
        barrier.wait()
        for _ in range(20):
            results.append(tb.allow("shared"))

    threads = [threading.Thread(target=worker) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(results) == 10
