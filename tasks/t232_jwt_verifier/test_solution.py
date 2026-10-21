import base64
import hashlib
import hmac
import importlib
import json

import pytest

import solution

NOW = 1_800_000_000
ISS = "https://auth.example.com"
AUD = "api://orders"
SECRET = b"s" * 32
RSA_PUB = b"-----BEGIN PUBLIC KEY----- fake rsa -----END PUBLIC KEY-----"
DELETE = object()


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def enc(obj) -> str:
    return b64(json.dumps(obj, separators=(",", ":")).encode())


def hs256(secret: bytes, signing_input: str) -> bytes:
    return hmac.new(secret, signing_input.encode(), hashlib.sha256).digest()


def fake_rs_sign(public_key: bytes, data: bytes) -> bytes:
    # «приватний ключ» у тесті виводиться з публічного: підпис підробити неможливо без секрету `priv-of-`
    return hmac.new(b"priv-of-" + public_key, data, hashlib.sha256).digest()


def make(header=None, payload=None, secret=SECRET, sig=None):
    h = {"alg": "HS256", "typ": "at+jwt", "kid": "k1", **(header or {})}
    p = {"iss": ISS, "aud": AUD, "exp": NOW + 600, "nbf": NOW - 10, "sub": "u1", **(payload or {})}
    h = {k: v for k, v in h.items() if v is not DELETE}
    p = {k: v for k, v in p.items() if v is not DELETE}
    signing_input = enc(h) + "." + enc(p)
    if sig is None:
        sig = hs256(secret, signing_input)
    return signing_input + "." + b64(sig)


class Jwks:
    def __init__(self, keys=None):
        self.keys = keys if keys is not None else [
            {"kid": "k1", "kty": "oct", "alg": "HS256", "key": SECRET},
            {"kid": "rsa1", "kty": "RSA", "alg": "RS256", "key": RSA_PUB},
        ]
        self.calls = 0
        self.fail = False

    def __call__(self):
        self.calls += 1
        if self.fail:
            raise ConnectionError("jwks endpoint down")
        return {"keys": list(self.keys)}


class Clock:
    def __init__(self, t=NOW):
        self.t = t

    def __call__(self):
        return self.t


class Recorder:
    def __init__(self, result=True):
        self.calls = []
        self.result = result

    def __call__(self, key, data, sig):
        self.calls.append((key, data, sig))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def verifier(jwks=None, clock=None, algorithms=("HS256", "RS256"), verify=None, **kw):
    jwks = jwks or Jwks()
    clock = clock or Clock()
    if verify is None:
        verify = lambda key, data, sig: hmac.compare_digest(fake_rs_sign(key, data), sig)  # noqa: E731
    params = dict(issuer=ISS, audience=AUD, algorithms=algorithms, clock=clock, verify=verify)
    params.update(kw)
    return solution.JwtVerifier(jwks, **params), jwks, clock


def code_of(v, token):
    with pytest.raises(solution.JwtError) as ei:
        v.verify_token(token)
    return ei.value.code


# --- успішний шлях -----------------------------------------------------------------------------

def test_valid_hs256_returns_claims():
    v, _, _ = verifier()
    claims = v.verify_token(make())
    assert claims["sub"] == "u1" and claims["iss"] == ISS and claims["exp"] == NOW + 600


def test_valid_rs256_calls_verify_with_key_material_signing_input_and_signature():
    rec = Recorder(True)
    v, _, _ = verifier(verify=rec)
    h = {"alg": "RS256", "kid": "rsa1"}
    raw_sig = b"\x01\x02\xfa\xfb" * 8
    token = make(h, sig=raw_sig)
    assert v.verify_token(token)["sub"] == "u1"
    assert rec.calls == [(RSA_PUB, token.rsplit(".", 1)[0].encode("ascii"), raw_sig)]


def test_rs256_with_real_looking_signature_flow():
    v, _, _ = verifier()
    h = {"alg": "RS256", "kid": "rsa1"}
    signing_input = enc({"alg": "RS256", "typ": "at+jwt", "kid": "rsa1"}) + "." + enc(
        {"iss": ISS, "aud": AUD, "exp": NOW + 5})
    token = signing_input + "." + b64(fake_rs_sign(RSA_PUB, signing_input.encode()))
    assert v.verify_token(token)["iss"] == ISS
    assert code_of(v, make(h, sig=b"forged")) == "bad_signature"


@pytest.mark.parametrize("result", [False, None, 1, "yes", ValueError("boom")])
def test_verify_result_must_be_strictly_true_and_exceptions_fail_closed(result):
    v, _, _ = verifier(verify=Recorder(result))
    assert code_of(v, make({"alg": "RS256", "kid": "rsa1"}, sig=b"x")) == "bad_signature"


def test_constructor_validation():
    with pytest.raises(ValueError):
        solution.JwtVerifier(Jwks(), issuer=ISS, audience=AUD, algorithms=["none"], clock=Clock(), verify=lambda *a: True)
    with pytest.raises(ValueError):
        solution.JwtVerifier(Jwks(), issuer=ISS, audience=AUD, algorithms=["HS256", "HS512"], clock=Clock())
    with pytest.raises(ValueError):
        solution.JwtVerifier(Jwks(), issuer=ISS, audience=AUD, algorithms=["RS256"], clock=Clock())  # без verify
    solution.JwtVerifier(Jwks(), issuer=ISS, audience=AUD, algorithms=["HS256"], clock=Clock())


# --- malformed ---------------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [
    None, 123, b"a.b.c", "", "a", "a.b", "a.b.c.d", "..", "a..c",
    "###." + enc({}) + ".sig", enc({"alg": "HS256"}) + "." + "%%%" + ".sig",
    enc({"alg": "HS256"}) + "=." + enc({}) + ".sig",
    b64(b"not json") + "." + enc({}) + ".sig",
    enc([1, 2]) + "." + enc({}) + ".sig",
    enc({"alg": "HS256"}) + "." + enc([1]) + ".sig",
    enc({"alg": "HS256"}) + "." + b64(b'"str"') + ".sig",
    b64(b"\xff\xfe") + "." + enc({}) + ".sig",
    enc({"alg": "HS256"}) + "." + enc({}) + ".a",  # довжина base64 %4 == 1
])
def test_malformed_tokens(bad):
    v, _, _ = verifier()
    assert code_of(v, bad) == "malformed"


# --- alg ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("alg", ["none", "None", "NONE", "nOnE"])
def test_alg_none_is_rejected_even_with_empty_signature(alg):
    v, _, _ = verifier()
    signing_input = enc({"alg": alg, "typ": "at+jwt", "kid": "k1"}) + "." + enc({"iss": ISS, "aud": AUD, "exp": NOW + 9})
    assert code_of(v, signing_input + ".") == "alg_not_allowed"


@pytest.mark.parametrize("alg", ["HS512", "hs256", "RS256 ", "ES256", None, 5, ["HS256"], DELETE])
def test_alg_outside_allowlist(alg):
    v, _, _ = verifier(algorithms=("HS256",))
    assert code_of(v, make({"alg": alg})) == "alg_not_allowed"


def test_alg_confusion_hs256_with_rsa_public_key_as_secret():
    v, _, _ = verifier(algorithms=("HS256", "RS256"))
    forged = make({"alg": "HS256", "kid": "rsa1"}, secret=RSA_PUB)  # підписано HMAC'ом з публічним ключем
    assert code_of(v, forged) == "key_mismatch"


def test_key_alg_must_equal_token_alg():
    jwks = Jwks([{"kid": "k1", "kty": "oct", "alg": "HS256", "key": SECRET}])
    v, _, _ = verifier(jwks=jwks)
    assert code_of(v, make({"alg": "RS256"}, sig=b"x")) == "key_mismatch"


def test_key_kty_must_fit_algorithm_even_if_alg_label_lies():
    jwks = Jwks([{"kid": "k1", "kty": "RSA", "alg": "HS256", "key": RSA_PUB}])
    v, _, _ = verifier(jwks=jwks)
    assert code_of(v, make(secret=RSA_PUB)) == "key_mismatch"


def test_hs256_key_must_be_bytes():
    jwks = Jwks([{"kid": "k1", "kty": "oct", "alg": "HS256", "key": "not-bytes"}])
    v, _, _ = verifier(jwks=jwks)
    assert code_of(v, make()) == "key_mismatch"


# --- підпис ------------------------------------------------------------------------------------

def test_tampered_payload_and_wrong_secret():
    v, _, _ = verifier()
    token = make()
    h, _, s = token.split(".")
    assert code_of(v, h + "." + enc({"iss": ISS, "aud": AUD, "exp": NOW + 600, "sub": "admin"}) + "." + s) == "bad_signature"
    assert code_of(v, make(secret=b"x" * 32)) == "bad_signature"
    assert code_of(v, make(sig=b"")) == "bad_signature"


def test_signature_is_checked_before_claims():
    v, _, _ = verifier()
    assert code_of(v, make({}, {"exp": NOW - 9999, "iss": "evil", "aud": "x"}, secret=b"x" * 32)) == "bad_signature"


# --- kid і JWKS --------------------------------------------------------------------------------

@pytest.mark.parametrize("kid", [DELETE, "", 7, None])
def test_missing_or_invalid_kid(kid):
    v, jwks, _ = verifier()
    assert code_of(v, make({"kid": kid})) == "unknown_kid"


def test_unknown_kid_triggers_one_refetch_then_unknown():
    v, jwks, _ = verifier()
    assert code_of(v, make({"kid": "ghost"})) == "unknown_kid"
    assert jwks.calls == 1


def test_known_kid_is_served_from_cache_until_ttl():
    v, jwks, clock = verifier(jwks_ttl=300)
    for _ in range(5):
        v.verify_token(make())
    assert jwks.calls == 1
    clock.t = NOW + 299
    v.verify_token(make({}, {"exp": NOW + 9999}))
    assert jwks.calls == 1
    clock.t = NOW + 300
    v.verify_token(make({}, {"exp": NOW + 9999}))
    assert jwks.calls == 2


def test_key_rotation_new_kid_is_picked_up_after_min_interval():
    v, jwks, clock = verifier(min_refetch_interval=30)
    v.verify_token(make())
    jwks.keys.append({"kid": "k2", "kty": "oct", "alg": "HS256", "key": b"n" * 32})
    clock.t = NOW + 30
    token = make({"kid": "k2"}, {"exp": NOW + 9999}, secret=b"n" * 32)
    assert v.verify_token(token)["sub"] == "u1"
    assert jwks.calls == 2


def test_unknown_kid_flood_does_not_hammer_jwks_endpoint():
    v, jwks, clock = verifier(min_refetch_interval=30)
    v.verify_token(make())
    clock.t = NOW + 31
    for i in range(50):
        assert code_of(v, make({"kid": f"rnd{i}"}, {"exp": NOW + 9999})) == "unknown_kid"
    assert jwks.calls == 2  # одне оновлення за інтервал
    clock.t = NOW + 62
    assert code_of(v, make({"kid": "rnd-late"}, {"exp": NOW + 9999})) == "unknown_kid"
    assert jwks.calls == 3


def test_new_kid_within_min_interval_is_not_fetched():
    v, jwks, clock = verifier(min_refetch_interval=30)
    v.verify_token(make())
    jwks.keys.append({"kid": "k2", "kty": "oct", "alg": "HS256", "key": b"n" * 32})
    clock.t = NOW + 10
    assert code_of(v, make({"kid": "k2"}, secret=b"n" * 32)) == "unknown_kid"
    assert jwks.calls == 1


def test_jwks_failure_is_fail_closed_and_rate_limited():
    jwks = Jwks()
    jwks.fail = True
    v, _, clock = verifier(jwks=jwks, min_refetch_interval=30)
    assert code_of(v, make()) == "jwks_unavailable"
    assert code_of(v, make()) == "jwks_unavailable"  # у межах інтервалу: без нового виклику
    assert jwks.calls == 1
    jwks.fail = False
    clock.t = NOW + 30
    assert v.verify_token(make({}, {"exp": NOW + 9999}))["sub"] == "u1"
    assert jwks.calls == 2


def test_failed_refresh_keeps_old_cache_for_known_kids():
    v, jwks, clock = verifier(min_refetch_interval=30, jwks_ttl=300)
    v.verify_token(make())
    jwks.fail = True
    clock.t = NOW + 40
    assert code_of(v, make({"kid": "other"}, {"exp": NOW + 9999})) == "jwks_unavailable"
    assert v.verify_token(make({}, {"exp": NOW + 9999}))["sub"] == "u1"  # k1 ще свіжий


def test_stale_cache_is_not_trusted_when_refetch_is_not_allowed():
    v, jwks, clock = verifier(min_refetch_interval=1000, jwks_ttl=100)
    v.verify_token(make())
    clock.t = NOW + 101
    assert code_of(v, make({}, {"exp": NOW + 9999})) == "jwks_unavailable"
    assert jwks.calls == 1


def test_garbage_jwks_document_is_unavailable():
    v = solution.JwtVerifier(lambda: {"nokeys": []}, issuer=ISS, audience=AUD, algorithms=["HS256"], clock=Clock())
    assert code_of(v, make()) == "jwks_unavailable"


def test_incomplete_and_duplicate_keys_are_ignored():
    jwks = Jwks([
        {"kid": "k1", "kty": "oct", "alg": "HS256"},  # без key
        {"kid": "dup", "kty": "oct", "alg": "HS256", "key": SECRET},
        {"kid": "dup", "kty": "oct", "alg": "HS256", "key": b"o" * 32},
        {"kid": "ok", "kty": "oct", "alg": "HS256", "key": SECRET},
    ])
    v, _, _ = verifier(jwks=jwks)
    assert code_of(v, make({"kid": "k1"})) == "unknown_kid"
    assert code_of(v, make({"kid": "dup"})) == "unknown_kid"
    assert v.verify_token(make({"kid": "ok"}))["sub"] == "u1"


# --- claims ------------------------------------------------------------------------------------

def test_exp_boundary_with_leeway():
    v, _, clock = verifier(leeway=30)
    token = make({}, {"exp": NOW})
    clock.t = NOW + 29
    assert v.verify_token(token)
    clock.t = NOW + 30
    assert code_of(v, token) == "expired"
    clock.t = NOW + 31
    assert code_of(v, token) == "expired"


def test_zero_leeway_exp_is_exclusive():
    v, _, clock = verifier(leeway=0)
    token = make({}, {"exp": NOW})
    clock.t = NOW - 1
    assert v.verify_token(token)
    clock.t = NOW
    assert code_of(v, token) == "expired"


def test_nbf_boundary_with_leeway():
    v, _, clock = verifier(leeway=30)
    token = make({}, {"nbf": NOW + 30})
    assert v.verify_token(token)  # now + leeway == nbf
    token = make({}, {"nbf": NOW + 31})
    assert code_of(v, token) == "not_yet_valid"
    clock.t = NOW + 1
    assert v.verify_token(token)


def test_nbf_is_optional():
    v, _, _ = verifier()
    assert v.verify_token(make({}, {"nbf": DELETE}))


def test_missing_exp_is_rejected():
    v, _, _ = verifier()
    assert code_of(v, make({}, {"exp": DELETE})) == "missing_claim"


@pytest.mark.parametrize("claim, value", [("exp", "9999999999"), ("exp", True), ("exp", None), ("exp", [1]),
                                            ("nbf", "0"), ("nbf", False)])
def test_non_numeric_time_claims(claim, value):
    v, _, _ = verifier()
    assert code_of(v, make({}, {claim: value})) == "malformed"


@pytest.mark.parametrize("iss", ["https://evil.example.com", "https://auth.example.com/", ISS.upper(), "", None, DELETE, 5])
def test_issuer_must_match_exactly(iss):
    v, _, _ = verifier()
    assert code_of(v, make({}, {"iss": iss})) == "bad_issuer"


@pytest.mark.parametrize("aud", ["api://other", "api://orders-v2", "api://order", AUD.upper(), "", [], ["a", "b"],
                                 ["api://orders-v2"], DELETE, None, 7, {"x": AUD}, [[AUD]]])
def test_audience_mismatch(aud):
    v, _, _ = verifier()
    assert code_of(v, make({}, {"aud": aud})) == "bad_audience"


def test_audience_accepts_string_or_list_containing_it():
    v, _, _ = verifier()
    assert v.verify_token(make({}, {"aud": AUD}))
    assert v.verify_token(make({}, {"aud": ["other", AUD]}))


# --- typ, crit ---------------------------------------------------------------------------------

@pytest.mark.parametrize("typ", ["JWT", "id+jwt", "", None, DELETE, 5])
def test_typ_must_match(typ):
    v, _, _ = verifier()
    assert code_of(v, make({"typ": typ})) == "bad_typ"


def test_typ_is_case_insensitive_and_configurable():
    v, _, _ = verifier()
    assert v.verify_token(make({"typ": "AT+JWT"}))
    v2, _, _ = verifier(typ="JWT")
    assert v2.verify_token(make({"typ": "jwt"}))
    assert code_of(v2, make({"typ": "at+jwt"})) == "bad_typ"


def test_crit_unknown_extension_is_rejected():
    v, _, _ = verifier()
    assert code_of(v, make({"crit": ["exp-policy"], "exp-policy": "x"})) == "crit_unsupported"


def test_crit_supported_extension_is_accepted():
    v, _, _ = verifier(supported_crit=("exp-policy",))
    assert v.verify_token(make({"crit": ["exp-policy"], "exp-policy": "x"}))
    assert code_of(v, make({"crit": ["exp-policy", "other"], "exp-policy": "x", "other": 1})) == "crit_unsupported"


@pytest.mark.parametrize("crit", [[], "exp-policy", [1], ["missing-header"], {"a": 1}, None])
def test_crit_malformed(crit):
    v, _, _ = verifier(supported_crit=("exp-policy", "missing-header"))
    assert code_of(v, make({"crit": crit})) == "malformed"


def test_hs256_signature_compared_in_constant_time(monkeypatch):
    calls = []
    real = hmac.compare_digest

    def spy(a, b):
        calls.append(1)
        return real(a, b)

    monkeypatch.setattr(hmac, "compare_digest", spy)
    mod = importlib.reload(solution)
    try:
        v = mod.JwtVerifier(Jwks(), issuer=ISS, audience=AUD, algorithms=["HS256"], clock=Clock())
        assert v.verify_token(make())["sub"] == "u1"
        assert calls
    finally:
        monkeypatch.undo()
        importlib.reload(solution)
