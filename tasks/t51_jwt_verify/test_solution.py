import base64
import hashlib
import hmac
import json

import pytest

import solution
from solution import InvalidToken, verify

SECRET = "s3cret"
NOW = 1_700_000_000


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def make(claims, secret=SECRET, header=None, sign=True):
    h = header if header is not None else {"alg": "HS256", "typ": "JWT"}
    head = b64(json.dumps(h).encode())
    body = b64(json.dumps(claims).encode())
    sig = b64(hmac.new(secret.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest()) if sign else ""
    return f"{head}.{body}.{sig}"


def ok_claims(**extra):
    return {"sub": "42", "exp": NOW + 60, **extra}


def test_valid_token_returns_claims():
    assert verify(make(ok_claims()), SECRET, now=NOW)["sub"] == "42"


def test_wrong_secret():
    with pytest.raises(InvalidToken):
        verify(make(ok_claims(), secret="other"), SECRET, now=NOW)


def test_tampered_payload():
    head, body, sig = make(ok_claims()).split(".")
    evil = b64(json.dumps({"sub": "1", "exp": NOW + 60}).encode())
    with pytest.raises(InvalidToken):
        verify(f"{head}.{evil}.{sig}", SECRET, now=NOW)


def test_alg_none_attack_rejected():
    token = make(ok_claims(), header={"alg": "none", "typ": "JWT"}, sign=False)
    with pytest.raises(InvalidToken):
        verify(token, SECRET, now=NOW)


@pytest.mark.parametrize("alg", ["HS512", "RS256", "hs256", "None", ""])
def test_other_algorithms_rejected_even_with_valid_hmac(alg):
    with pytest.raises(InvalidToken):
        verify(make(ok_claims(), header={"alg": alg}), SECRET, now=NOW)


def test_missing_alg_rejected():
    with pytest.raises(InvalidToken):
        verify(make(ok_claims(), header={"typ": "JWT"}), SECRET, now=NOW)


def test_expired():
    with pytest.raises(InvalidToken):
        verify(make({"exp": NOW - 1}), SECRET, now=NOW)


def test_leeway_allows_slightly_expired():
    verify(make({"exp": NOW - 5}), SECRET, now=NOW, leeway=10)
    with pytest.raises(InvalidToken):
        verify(make({"exp": NOW - 11}), SECRET, now=NOW, leeway=10)


def test_exp_is_required_and_must_be_number():
    with pytest.raises(InvalidToken):
        verify(make({"sub": "42"}), SECRET, now=NOW)
    with pytest.raises(InvalidToken):
        verify(make({"exp": "tomorrow"}), SECRET, now=NOW)


def test_not_before():
    with pytest.raises(InvalidToken):
        verify(make(ok_claims(nbf=NOW + 30)), SECRET, now=NOW)
    verify(make(ok_claims(nbf=NOW + 30)), SECRET, now=NOW, leeway=30)


def test_audience():
    verify(make(ok_claims(aud="api")), SECRET, now=NOW, audience="api")
    verify(make(ok_claims(aud=["web", "api"])), SECRET, now=NOW, audience="api")
    with pytest.raises(InvalidToken):
        verify(make(ok_claims(aud="other")), SECRET, now=NOW, audience="api")
    with pytest.raises(InvalidToken):
        verify(make(ok_claims()), SECRET, now=NOW, audience="api")


@pytest.mark.parametrize(
    "bad",
    ["", "a.b", "a.b.c.d", "!!!.???.***", "e30.e30.", f"{b64(b'not json')}.{b64(b'{}')}.x"],
)
def test_malformed_tokens_raise_only_invalid_token(bad):
    with pytest.raises(InvalidToken):
        verify(bad, SECRET, now=NOW)


def test_uses_constant_time_comparison(monkeypatch):
    calls = []
    real = hmac.compare_digest
    monkeypatch.setattr(solution.hmac, "compare_digest", lambda a, b: (calls.append(1), real(a, b))[1])
    verify(make(ok_claims()), SECRET, now=NOW)
    assert calls, "порівнюй підписи через hmac.compare_digest"
