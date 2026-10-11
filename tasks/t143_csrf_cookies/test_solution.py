import pytest

import solution
from solution import CsrfGuard, audit_set_cookie

# --- audit_set_cookie --------------------------------------------------------------------------

GOOD = "sid=abc123; Path=/; Secure; HttpOnly; SameSite=Lax"


def test_good_cookie_is_clean():
    assert audit_set_cookie(GOOD) == []


@pytest.mark.parametrize(
    "header, expected",
    [
        ("sid=a; Path=/; HttpOnly; SameSite=Lax", ["missing_secure"]),
        ("sid=a; Path=/; Secure; SameSite=Lax", ["missing_httponly"]),
        ("sid=a; Path=/; Secure; HttpOnly", ["missing_samesite"]),
        ("sid=a; Path=/; Secure; HttpOnly; SameSite=Bogus", ["missing_samesite"]),
        ("sid=a; Path=/; Secure; HttpOnly; SameSite=", ["missing_samesite"]),
        ("sid=a", ["missing_httponly", "missing_samesite", "missing_secure"]),
    ],
)
def test_missing_flags(header, expected):
    assert audit_set_cookie(header) == expected


def test_attribute_names_and_values_are_case_insensitive_and_whitespace_tolerant():
    assert audit_set_cookie("sid=a;secure;HTTPONLY;samesite=STRICT") == []
    assert audit_set_cookie("sid=a ;  Secure ; HttpOnly ;  SameSite = lax ") == []


@pytest.mark.parametrize("value", ["Lax", "Strict", "None", "lax", "NONE"])
def test_valid_samesite_values(value):
    header = f"sid=a; Path=/; Secure; HttpOnly; SameSite={value}"
    assert audit_set_cookie(header) == []


def test_samesite_none_requires_secure():
    assert audit_set_cookie("sid=a; HttpOnly; SameSite=None") == ["missing_secure", "samesite_none_insecure"]


def test_domain_attribute_is_flagged():
    assert audit_set_cookie(GOOD + "; Domain=example.com") == ["broad_domain"]


@pytest.mark.parametrize(
    "max_age, flagged",
    [("3600", False), ("2592000", False), ("2592001", True), ("31536000", True), ("abc", False), ("0", False)],
)
def test_long_lived(max_age, flagged):
    result = audit_set_cookie(GOOD + f"; Max-Age={max_age}")
    assert result == (["long_lived"] if flagged else [])


def test_host_prefix_rules():
    assert audit_set_cookie("__Host-sid=a; Path=/; Secure; HttpOnly; SameSite=Strict") == []
    assert audit_set_cookie("__Host-sid=a; Path=/app; Secure; HttpOnly; SameSite=Lax") == ["bad_host_prefix"]
    assert audit_set_cookie("__Host-sid=a; Secure; HttpOnly; SameSite=Lax") == ["bad_host_prefix"]  # без Path
    assert audit_set_cookie("__Host-sid=a; Path=/; HttpOnly; SameSite=Lax") == ["bad_host_prefix", "missing_secure"]
    assert audit_set_cookie("__Host-sid=a; Path=/; Secure; HttpOnly; SameSite=Lax; Domain=example.com") == [
        "bad_host_prefix", "broad_domain",
    ]


def test_secure_prefix_rule():
    assert audit_set_cookie("__Secure-sid=a; Path=/; Secure; HttpOnly; SameSite=Lax") == []
    assert audit_set_cookie("__Secure-sid=a; Path=/; HttpOnly; SameSite=Lax") == ["bad_secure_prefix", "missing_secure"]


def test_prefix_is_case_sensitive_on_name_only_for_exact_prefix():
    # звичайне ім'я, що лише містить Host: префіксних правил немає
    assert audit_set_cookie("my__Host-sid=a; Path=/x; Secure; HttpOnly; SameSite=Lax") == []


@pytest.mark.parametrize("bad", ["", "   ", "Secure; HttpOnly", "=value; Secure", ";"])
def test_not_a_set_cookie_value(bad):
    with pytest.raises(ValueError):
        audit_set_cookie(bad)


def test_results_sorted_and_unique():
    result = audit_set_cookie("sid=a; Domain=x.com; Max-Age=99999999; Max-Age=99999999")
    assert result == sorted(set(result))
    assert result == ["broad_domain", "long_lived", "missing_httponly", "missing_samesite", "missing_secure"]


# --- CsrfGuard ---------------------------------------------------------------------------------

ORIGIN = "https://app.example.com"
SECRET = b"unit-test-secret"


class Clock:
    def __init__(self, now=1_700_000_000):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def guard(clock):
    return CsrfGuard(SECRET, {ORIGIN}, clock=clock, max_age=3600)


def post(guard, token, *, session="sess-1", headers=None, method="POST"):
    return guard.check(method, headers if headers is not None else {"Origin": ORIGIN}, session, token)


def test_token_format(guard, clock):
    token = guard.issue("sess-1")
    ts, dot, sig = token.partition(".")
    assert dot == "." and ts == str(clock.now)
    assert len(sig) == 64 and int(sig, 16) >= 0


def test_valid_post_passes(guard):
    assert post(guard, guard.issue("sess-1")) is True


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS", "get", "Options"])
def test_safe_methods_need_nothing(guard, method):
    assert guard.check(method, {}, "", None) is True
    assert guard.check(method, {"Origin": "https://evil.example"}, "s", "garbage") is True


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "post", "put"])
def test_unsafe_methods_are_protected(guard, method):
    assert post(guard, None, method=method) is False
    assert post(guard, guard.issue("sess-1"), method=method) is True


def test_missing_or_empty_token_and_session(guard):
    assert post(guard, None) is False
    assert post(guard, "") is False
    assert guard.check("POST", {"Origin": ORIGIN}, "", guard.issue("")) is False
    assert guard.check("POST", {"Origin": ORIGIN}, None, guard.issue("x")) is False


def test_token_is_bound_to_the_session(guard):
    attacker_token = guard.issue("attacker-session")
    assert post(guard, attacker_token, session="victim-session") is False


def test_tampered_signature_and_timestamp(guard, clock):
    token = guard.issue("sess-1")
    ts, _, sig = token.partition(".")
    flipped = sig[:-1] + ("0" if sig[-1] != "0" else "1")
    assert post(guard, f"{ts}.{flipped}") is False
    assert post(guard, f"{int(ts) + 100}.{sig}") is False  # інший час, підпис не підходить
    assert post(guard, f"{int(ts) - 100}.{sig}") is False


def test_token_signed_with_other_secret_is_rejected(clock):
    other = CsrfGuard(b"another-secret", {ORIGIN}, clock=clock)
    mine = CsrfGuard(SECRET, {ORIGIN}, clock=clock)
    assert post(mine, other.issue("sess-1")) is False


def test_expiry_boundaries(guard, clock):
    token = guard.issue("sess-1")
    clock.now += 3600
    assert post(guard, token) is True  # рівно max_age ще дійсний
    clock.now += 1
    assert post(guard, token) is False


def test_token_from_the_future_is_rejected(clock):
    issuer = CsrfGuard(SECRET, {ORIGIN}, clock=Clock(clock.now + 500))
    checker = CsrfGuard(SECRET, {ORIGIN}, clock=clock)
    assert post(checker, issuer.issue("sess-1")) is False


@pytest.mark.parametrize("token", ["garbage", "abc.def", "1.2.3", ".", "x.", ".y", "-5.abcdef", "1e9.aa", " 1.aa", "١٢٣.aa"])
def test_malformed_tokens_return_false_not_raise(guard, token):
    assert post(guard, token) is False


def test_non_string_token_returns_false(guard):
    assert post(guard, 12345) is False
    assert post(guard, b"123.abc") is False


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "https://evil.example"},
        {"Origin": "null"},
        {"Origin": "https://app.example.com.evil.example"},
        {"Origin": "http://app.example.com"},
        {"Origin": "https://app.example.com:8443"},
        {},
        {"Referer": "https://evil.example/page"},
        {"Referer": "https://app.example.com.evil.example/"},
        {"Referer": ""},
    ],
)
def test_bad_or_missing_origin_is_rejected(guard, headers):
    assert post(guard, guard.issue("sess-1"), headers=headers) is False


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": ORIGIN},
        {"origin": ORIGIN},
        {"ORIGIN": "HTTPS://APP.EXAMPLE.COM"},
        {"Referer": "https://app.example.com/settings?tab=1"},
        {"referer": "https://app.example.com/"},
    ],
)
def test_good_origin_or_referer_is_accepted(guard, headers):
    assert post(guard, guard.issue("sess-1"), headers=headers) is True


def test_origin_wins_over_referer(guard):
    headers = {"Origin": "https://evil.example", "Referer": "https://app.example.com/"}
    assert post(guard, guard.issue("sess-1"), headers=headers) is False


def test_multiple_allowed_origins():
    g = CsrfGuard(SECRET, ["https://a.example", "https://b.example"], clock=Clock())
    t = g.issue("s")
    assert g.check("POST", {"Origin": "https://b.example"}, "s", t) is True
    assert g.check("POST", {"Origin": "https://c.example"}, "s", t) is False


def test_signature_compared_with_compare_digest(guard, monkeypatch):
    calls = []
    real = solution.hmac.compare_digest

    def spy(a, b):
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr(solution.hmac, "compare_digest", spy)
    assert post(guard, guard.issue("sess-1")) is True
    assert calls, "підпис треба порівнювати через hmac.compare_digest"


def test_tokens_differ_between_sessions_and_times(guard, clock):
    a = guard.issue("s1")
    b = guard.issue("s2")
    clock.now += 1
    c = guard.issue("s1")
    assert len({a, b, c}) == 3
