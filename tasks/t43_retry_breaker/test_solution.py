import pytest

from solution import CircuitBreaker, CircuitOpenError, retry


class Flaky:
    def __init__(self, fail_times, exc=ConnectionError):
        self.fail_times = fail_times
        self.exc = exc
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise self.exc(f"fail {self.calls}")
        return "ok"


# ---------- retry ----------

def test_retry_succeeds_after_failures_with_exponential_delays():
    sleeps = []
    fn = Flaky(3)
    assert retry(fn, attempts=4, base_delay=0.1, sleep=sleeps.append, jitter=lambda: 1.0) == "ok"
    assert fn.calls == 4
    assert sleeps == pytest.approx([0.1, 0.2, 0.4])


def test_retry_caps_delay_and_applies_jitter():
    sleeps = []
    fn = Flaky(4)
    retry(fn, attempts=5, base_delay=1, max_delay=3, sleep=sleeps.append, jitter=lambda: 0.5)
    assert sleeps == pytest.approx([0.5, 1.0, 1.5, 1.5])


def test_retry_raises_last_exception_after_exhaustion():
    sleeps = []
    fn = Flaky(10)
    with pytest.raises(ConnectionError, match="fail 3"):
        retry(fn, attempts=3, sleep=sleeps.append, jitter=lambda: 1.0)
    assert fn.calls == 3
    assert len(sleeps) == 2, "після останньої спроби спати не треба"


def test_retry_does_not_retry_unlisted_exceptions():
    sleeps = []
    fn = Flaky(5, exc=ValueError)
    with pytest.raises(ValueError):
        retry(fn, retry_on=(ConnectionError,), sleep=sleeps.append)
    assert fn.calls == 1
    assert sleeps == []


def test_retry_first_try_success_no_sleep():
    sleeps = []
    assert retry(Flaky(0), sleep=sleeps.append) == "ok"
    assert sleeps == []


# ---------- circuit breaker ----------

class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def failing():
    raise ConnectionError("down")


def test_breaker_opens_after_threshold_and_short_circuits():
    clock = FakeClock()
    cb = CircuitBreaker(failure_threshold=3, reset_timeout=10, clock=clock)
    for _ in range(3):
        with pytest.raises(ConnectionError):
            cb.call(failing)
    assert cb.state == "open"
    probe = Flaky(0)
    with pytest.raises(CircuitOpenError):
        cb.call(probe)
    assert probe.calls == 0, "у стані open функцію викликати не можна"


def test_success_resets_failure_counter():
    cb = CircuitBreaker(failure_threshold=3, clock=FakeClock())
    for _ in range(2):
        with pytest.raises(ConnectionError):
            cb.call(failing)
    assert cb.call(lambda: "ok") == "ok"
    for _ in range(2):
        with pytest.raises(ConnectionError):
            cb.call(failing)
    assert cb.state == "closed"


def test_half_open_success_closes():
    clock = FakeClock()
    cb = CircuitBreaker(failure_threshold=2, reset_timeout=10, clock=clock)
    for _ in range(2):
        with pytest.raises(ConnectionError):
            cb.call(failing)
    clock.t = 9.9
    assert cb.state == "open"
    clock.t = 10
    assert cb.state == "half_open"
    assert cb.call(lambda: "ok") == "ok"
    assert cb.state == "closed"


def test_half_open_failure_reopens_and_restarts_timer():
    clock = FakeClock()
    cb = CircuitBreaker(failure_threshold=2, reset_timeout=10, clock=clock)
    for _ in range(2):
        with pytest.raises(ConnectionError):
            cb.call(failing)
    clock.t = 10
    with pytest.raises(ConnectionError):
        cb.call(failing)
    assert cb.state == "open"
    clock.t = 19.9
    assert cb.state == "open"
    clock.t = 20
    assert cb.state == "half_open"
