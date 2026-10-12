import hashlib
import hmac
import json

import pytest

from solution import Response, deliver

EVENT = {"id": "evt_1", "type": "order.paid", "data": {"amount": 100, "note": "Київ"}}
SECRET = "whsec_test"


class Clock:
    def __init__(self, now=1_700_000_000.0):
        self.now = now
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class Receiver:
    """Мок-приймач: віддає заготовлені відповіді по черзі; Exception підіймається."""

    def __init__(self, *script):
        self.script = list(script)
        self.calls = []

    def __call__(self, url, body, headers, timeout):
        self.calls.append({"url": url, "body": body, "headers": dict(headers), "timeout": timeout})
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step if isinstance(step, Response) else Response(step)


def run(receiver, clock=None, **kw):
    clock = clock or Clock()
    result = deliver(EVENT, "https://client.example/hook", SECRET, receiver, clock=clock, sleep=clock.sleep, **kw)
    return result, clock


def test_delivered_on_first_try():
    rx = Receiver(200)
    result, clock = run(rx)
    assert (result.status, result.attempts) == ("delivered", 1)
    assert result.log == [{"attempt": 1, "at": 1_700_000_000.0, "outcome": "200"}]
    assert clock.sleeps == []


def test_body_and_headers_and_signature():
    rx = Receiver(204)
    run(rx, timeout=3.0)
    call = rx.calls[0]
    assert call["url"] == "https://client.example/hook"
    assert call["timeout"] == 3.0
    assert call["body"] == json.dumps(EVENT, separators=(",", ":"), sort_keys=True).encode("utf-8")
    h = call["headers"]
    assert h["Content-Type"] == "application/json"
    assert h["X-Webhook-Id"] == "evt_1"
    assert h["X-Webhook-Timestamp"] == "1700000000"
    expected = hmac.new(SECRET.encode(), b"1700000000." + call["body"], hashlib.sha256).hexdigest()
    assert h["X-Webhook-Signature"] == f"v1={expected}"


def test_retries_5xx_with_exponential_backoff_then_succeeds():
    rx = Receiver(500, 502, 503, 200)
    result, clock = run(rx)
    assert (result.status, result.attempts) == ("delivered", 4)
    assert clock.sleeps == [1.0, 2.0, 4.0]
    assert [e["outcome"] for e in result.log] == ["500", "502", "503", "200"]


def test_same_event_id_and_body_but_fresh_timestamp_and_signature_each_attempt():
    rx = Receiver(500, 500, 200)
    run(rx)
    ids = {c["headers"]["X-Webhook-Id"] for c in rx.calls}
    bodies = {c["body"] for c in rx.calls}
    stamps = [c["headers"]["X-Webhook-Timestamp"] for c in rx.calls]
    sigs = {c["headers"]["X-Webhook-Signature"] for c in rx.calls}
    assert ids == {"evt_1"} and len(bodies) == 1
    assert stamps == ["1700000000", "1700000001", "1700000003"]
    assert len(sigs) == 3
    for c in rx.calls:  # кожен підпис валідний для свого timestamp
        t = c["headers"]["X-Webhook-Timestamp"].encode()
        good = hmac.new(SECRET.encode(), t + b"." + c["body"], hashlib.sha256).hexdigest()
        assert c["headers"]["X-Webhook-Signature"] == f"v1={good}"


def test_log_records_time_of_each_attempt():
    rx = Receiver(500, 500, 200)
    result, _ = run(rx)
    assert [e["at"] for e in result.log] == [1_700_000_000.0, 1_700_000_001.0, 1_700_000_003.0]
    assert [e["attempt"] for e in result.log] == [1, 2, 3]


@pytest.mark.parametrize("exc, name", [(TimeoutError(), "TimeoutError"), (ConnectionError(), "ConnectionError")])
def test_network_errors_are_retried(exc, name):
    rx = Receiver(exc, 200)
    result, _ = run(rx)
    assert (result.status, result.attempts) == ("delivered", 2)
    assert result.log[0]["outcome"] == f"error:{name}"


def test_gives_up_after_max_attempts_without_final_sleep():
    rx = Receiver(500, 500, 500)
    result, clock = run(rx, max_attempts=3)
    assert (result.status, result.attempts) == ("failed", 3)
    assert clock.sleeps == [1.0, 2.0], "після останньої спроби спати не треба"
    assert len(rx.calls) == 3


@pytest.mark.parametrize("status", [400, 401, 403, 404, 410, 422, 301, 302])
def test_permanent_rejection_is_not_retried(status):
    rx = Receiver(status, 200)
    result, clock = run(rx)
    assert (result.status, result.attempts) == ("rejected", 1)
    assert len(rx.calls) == 1 and clock.sleeps == []
    assert result.log[0]["outcome"] == str(status)


@pytest.mark.parametrize("status", [408, 425, 429, 500, 503, 504])
def test_retryable_statuses(status):
    result, _ = run(Receiver(status, 200))
    assert (result.status, result.attempts) == ("delivered", 2)


def test_retry_after_extends_the_pause_but_never_shortens_it():
    rx = Receiver(Response(429, {"Retry-After": "30"}), Response(503, {"Retry-After": "0"}), 200)
    _, clock = run(rx)
    assert clock.sleeps == [30.0, 2.0]


def test_retry_after_is_capped_by_max_delay():
    rx = Receiver(Response(429, {"Retry-After": "3600"}), 200)
    _, clock = run(rx, max_delay=60.0)
    assert clock.sleeps == [60.0]


def test_backoff_is_capped_by_max_delay():
    rx = Receiver(*([500] * 7 + [200]))
    _, clock = run(rx, max_attempts=8, base_delay=10.0, max_delay=60.0)
    assert clock.sleeps == [10.0, 20.0, 40.0, 60.0, 60.0, 60.0, 60.0]


def test_retry_after_header_name_is_case_insensitive():
    rx = Receiver(Response(429, {"retry-after": "7"}), 200)
    _, clock = run(rx)
    assert clock.sleeps == [7.0]


def test_garbage_retry_after_falls_back_to_backoff():
    rx = Receiver(Response(503, {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}), 200)
    _, clock = run(rx)
    assert clock.sleeps == [1.0]
