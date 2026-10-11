import hashlib
import hmac

import pytest

import solution
from solution import (
    ExpiredTimestamp,
    InvalidSignature,
    ReplayedEvent,
    WebhookError,
    verify_webhook,
)

SECRET = "whsec_test"
PAYLOAD = b'{"event":"payment.succeeded","id":"evt_1"}'
NOW = 1_700_000_000


def sign(payload=PAYLOAD, ts=NOW, secret=SECRET):
    mac = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return mac


def header(ts=NOW, *sigs):
    return f"t={ts}," + ",".join(f"v1={s}" for s in sigs)


def test_valid_signature_passes():
    verify_webhook(PAYLOAD, header(NOW, sign()), SECRET, now=NOW)


def test_tampered_payload_rejected():
    with pytest.raises(InvalidSignature):
        verify_webhook(PAYLOAD + b" ", header(NOW, sign()), SECRET, now=NOW)


def test_wrong_secret_rejected():
    with pytest.raises(InvalidSignature):
        verify_webhook(PAYLOAD, header(NOW, sign(secret="other")), SECRET, now=NOW)


@pytest.mark.parametrize(
    "bad",
    ["", "garbage", "t=abc,v1=00", "v1=00", f"t={NOW}", f"t={NOW},v1", f"t={NOW},,v1=", "t=1,v1=ff,=,"],
)
def test_malformed_header_rejected(bad):
    with pytest.raises(InvalidSignature):
        verify_webhook(PAYLOAD, bad, SECRET, now=NOW)


def test_old_timestamp_rejected_even_with_valid_signature():
    old = NOW - 301
    with pytest.raises(ExpiredTimestamp):
        verify_webhook(PAYLOAD, header(old, sign(ts=old)), SECRET, now=NOW)


def test_future_timestamp_rejected():
    future = NOW + 301
    with pytest.raises(ExpiredTimestamp):
        verify_webhook(PAYLOAD, header(future, sign(ts=future)), SECRET, now=NOW)


def test_timestamp_inside_tolerance_ok():
    ts = NOW - 300
    verify_webhook(PAYLOAD, header(ts, sign(ts=ts)), SECRET, now=NOW)


def test_any_of_multiple_signatures_may_match():
    # ротація ключів: у заголовку підписи старого й нового секрету
    h = header(NOW, sign(secret="old"), sign())
    verify_webhook(PAYLOAD, h, SECRET, now=NOW)


def test_replay_is_rejected():
    seen = set()
    h = header(NOW, sign())
    verify_webhook(PAYLOAD, h, SECRET, now=NOW, seen=seen)
    with pytest.raises(ReplayedEvent):
        verify_webhook(PAYLOAD, h, SECRET, now=NOW + 1, seen=seen)


def test_invalid_attempt_does_not_poison_seen():
    seen = set()
    with pytest.raises(InvalidSignature):
        verify_webhook(PAYLOAD, header(NOW, "00" * 32), SECRET, now=NOW, seen=seen)
    assert seen == set()
    verify_webhook(PAYLOAD, header(NOW, sign()), SECRET, now=NOW, seen=seen)


def test_all_errors_share_base_class():
    for exc in (InvalidSignature, ExpiredTimestamp, ReplayedEvent):
        assert issubclass(exc, WebhookError)


def test_uses_constant_time_comparison(monkeypatch):
    calls = []
    real = hmac.compare_digest

    def spy(a, b):
        calls.append(1)
        return real(a, b)

    monkeypatch.setattr(solution.hmac, "compare_digest", spy)
    verify_webhook(PAYLOAD, header(NOW, sign()), SECRET, now=NOW)
    assert calls, "порівнюй підписи через hmac.compare_digest, не через =="
