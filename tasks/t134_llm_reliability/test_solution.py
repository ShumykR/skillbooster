import pytest

from solution import AllProvidersFailed, DeadlineExceeded, ProviderRouter, RequestRejected


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds

    sleeps: list


class HttpError(Exception):
    def __init__(self, status, retry_after=None):
        super().__init__(f"HTTP {status}")
        self.status, self.retry_after = status, retry_after


class Script:
    """Провайдер, що віддає заздалегідь заготовлені результати по черзі (останній повторюється)."""

    def __init__(self, clock, *outcomes, latency=0.0):
        self.clock, self.outcomes, self.latency, self.calls = clock, list(outcomes), latency, 0

    def __call__(self, request):
        outcome = self.outcomes[min(self.calls, len(self.outcomes) - 1)]
        self.calls += 1
        self.clock.now += self.latency
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture
def clock():
    c = Clock()
    c.sleeps = []
    return c


def router(clock, *providers, **kw):
    return ProviderRouter(list(providers), clock=clock, sleep=clock.sleep, **kw)


# ---------- retries -----------------------------------------------------------------------------------------------------


def test_first_provider_answers(clock):
    a = Script(clock, "hello")
    r = router(clock, ("a", a), ("b", Script(clock, "never")))
    assert r.call({"q": 1}) == {"provider": "a", "response": "hello", "attempts": [("a", "ok")]}
    assert clock.sleeps == []


def test_transient_error_is_retried_with_backoff(clock):
    r = router(clock, ("a", Script(clock, HttpError(503), "ok")))
    assert r.call({})["attempts"] == [("a", "503"), ("a", "ok")]
    assert clock.sleeps == [0.5]


def test_backoff_doubles_between_attempts(clock):
    r = router(clock, ("a", Script(clock, HttpError(500), HttpError(500), HttpError(500), "ok")), max_attempts=4, base_delay=1.0, breaker_threshold=99)
    r.call({})
    assert clock.sleeps == [1.0, 2.0, 4.0]


def test_after_the_last_attempt_it_moves_to_the_next_provider_without_sleeping(clock):
    r = router(clock, ("a", Script(clock, HttpError(500))), ("b", Script(clock, "from b")))
    res = r.call({})
    assert res["provider"] == "b" and res["attempts"] == [("a", "500"), ("a", "500"), ("b", "ok")]
    assert clock.sleeps == [0.5]


@pytest.mark.parametrize("exc, label", [
    (TimeoutError(), "timeout"), (ConnectionError(), "connection"), (ConnectionResetError(), "connection"),
    (HttpError(429), "429"), (HttpError(500), "500"), (HttpError(529), "529")])
def test_retryable_errors(clock, exc, label):
    r = router(clock, ("a", Script(clock, exc, "ok")))
    assert r.call({})["attempts"] == [("a", label), ("a", "ok")]


def test_retry_after_replaces_the_backoff(clock):
    r = router(clock, ("a", Script(clock, HttpError(429, retry_after=3), "ok")))
    r.call({})
    assert clock.sleeps == [3]
    clock.sleeps.clear()
    r = router(clock, ("a", Script(clock, HttpError(429, retry_after=0), "ok")))
    r.call({})
    assert clock.sleeps == [0], "Retry-After 0 це не None"


# ---------- permanent errors ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("status", [400, 404, 413, 422, 418])
def test_bad_requests_are_not_retried_or_sent_elsewhere(clock, status):
    b = Script(clock, "never")
    r = router(clock, ("a", Script(clock, HttpError(status))), ("b", b), breaker_threshold=1)
    with pytest.raises(RequestRejected) as info:
        r.call({})
    assert info.value.original.status == status and b.calls == 0 and clock.sleeps == []
    assert r.breaker_state("a") == "closed"


@pytest.mark.parametrize("status", [401, 403])
def test_auth_errors_skip_to_the_next_provider_without_retrying(clock, status):
    a = Script(clock, HttpError(status))
    r = router(clock, ("a", a), ("b", Script(clock, "ok")))
    res = r.call({})
    assert res["attempts"] == [("a", str(status)), ("b", "ok")] and a.calls == 1 and clock.sleeps == []


def test_unknown_exceptions_are_bugs_and_propagate(clock):
    r = router(clock, ("a", Script(clock, ValueError("bug"))), ("b", Script(clock, "ok")))
    with pytest.raises(ValueError):
        r.call({})


def test_everything_failed(clock):
    r = router(clock, ("a", Script(clock, HttpError(500))), ("b", Script(clock, TimeoutError())))
    with pytest.raises(AllProvidersFailed) as info:
        r.call({})
    assert info.value.attempts == [("a", "500"), ("a", "500"), ("b", "timeout"), ("b", "timeout")]
    assert not isinstance(info.value, DeadlineExceeded)


# ---------- deadline ----------------------------------------------------------------------------------------------------------------


def test_too_long_retry_after_moves_on_instead_of_waiting(clock):
    r = router(clock, ("a", Script(clock, HttpError(429, retry_after=20))), ("b", Script(clock, "ok")), deadline=10)
    res = r.call({})
    assert res["provider"] == "b" and clock.sleeps == [] and res["attempts"] == [("a", "429"), ("b", "ok")]


def test_wait_that_reaches_the_deadline_exactly_is_skipped(clock):
    r = router(clock, ("a", Script(clock, HttpError(500), "ok")), ("b", Script(clock, "from b")), deadline=0.5, base_delay=0.5)
    assert r.call({})["provider"] == "b" and clock.sleeps == []
    r2 = router(clock, ("a", Script(clock, HttpError(500), "ok")), ("b", Script(clock, "from b")), deadline=0.51, base_delay=0.5)
    assert r2.call({})["provider"] == "a" and clock.sleeps == [0.5]


def test_deadline_exceeded_before_a_new_attempt(clock):
    slow = Script(clock, TimeoutError(), latency=20.0)
    r = router(clock, ("a", slow), ("b", Script(clock, "never")), max_attempts=3, base_delay=1.0, deadline=30.0, breaker_threshold=99)
    with pytest.raises(DeadlineExceeded) as info:
        r.call({})
    assert info.value.attempts == [("a", "timeout"), ("a", "timeout")] and clock.sleeps == [1.0]
    assert isinstance(info.value, AllProvidersFailed)


def test_deadline_is_measured_per_call(clock):
    r = router(clock, ("a", Script(clock, "ok")), deadline=5)
    clock.now += 100
    assert r.call({})["provider"] == "a"


# ---------- circuit breaker -------------------------------------------------------------------------------------------------------------------


def test_breaker_opens_after_consecutive_failures_and_is_skipped(clock):
    a, b = Script(clock, HttpError(500)), Script(clock, "from b")
    r = router(clock, ("a", a), ("b", b))
    assert r.call({})["attempts"] == [("a", "500"), ("a", "500"), ("b", "ok")]
    assert r.breaker_state("a") == "closed"
    assert r.call({})["attempts"] == [("a", "500"), ("b", "ok")], "третя помилка відкрила breaker: другої спроби немає"
    assert r.breaker_state("a") == "open"
    calls = a.calls
    assert r.call({})["attempts"] == [("a", "open"), ("b", "ok")]
    assert a.calls == calls


def test_half_open_probe_success_closes_the_breaker(clock):
    a = Script(clock, HttpError(500), HttpError(500), HttpError(500), "recovered")
    r = router(clock, ("a", a), ("b", Script(clock, "from b")))
    r.call({})
    r.call({})
    assert r.breaker_state("a") == "open"
    clock.now += 59.99
    assert r.breaker_state("a") == "open"
    clock.now += 0.01
    assert r.breaker_state("a") == "half-open"
    res = r.call({})
    assert res["attempts"] == [("a", "ok")] and r.breaker_state("a") == "closed"


def test_half_open_probe_failure_reopens_for_a_full_period(clock):
    a = Script(clock, HttpError(500))
    r = router(clock, ("a", a), ("b", Script(clock, "from b")))
    r.call({})
    r.call({})
    clock.now += 60
    res = r.call({})
    assert res["attempts"] == [("a", "500"), ("b", "ok")], "проба одна: без повторів"
    assert r.breaker_state("a") == "open"
    clock.now += 59.9
    assert r.breaker_state("a") == "open"
    clock.now += 0.1
    assert r.breaker_state("a") == "half-open"


def test_success_resets_the_failure_streak(clock):
    a = Script(clock, HttpError(500), "ok", HttpError(500), "ok", HttpError(500), "ok")
    r = router(clock, ("a", a), breaker_threshold=2)
    for _ in range(3):
        assert r.call({})["provider"] == "a"
    assert r.breaker_state("a") == "closed"


def test_auth_failures_also_count_for_the_breaker(clock):
    a = Script(clock, HttpError(401))
    r = router(clock, ("a", a), ("b", Script(clock, "ok")), breaker_threshold=2)
    r.call({})
    r.call({})
    assert r.breaker_state("a") == "open" and a.calls == 2


def test_breakers_are_per_provider(clock):
    r = router(clock, ("a", Script(clock, HttpError(500))), ("b", Script(clock, "ok")), breaker_threshold=1)
    r.call({})
    assert r.breaker_state("a") == "open" and r.breaker_state("b") == "closed"
    assert r.call({})["attempts"] == [("a", "open"), ("b", "ok")]


def test_all_breakers_open_means_failure_without_calls(clock):
    a, b = Script(clock, HttpError(500)), Script(clock, HttpError(500))
    r = router(clock, ("a", a), ("b", b), breaker_threshold=1, max_attempts=1)
    with pytest.raises(AllProvidersFailed):
        r.call({})
    calls = (a.calls, b.calls)
    with pytest.raises(AllProvidersFailed) as info:
        r.call({})
    assert info.value.attempts == [("a", "open"), ("b", "open")] and (a.calls, b.calls) == calls
