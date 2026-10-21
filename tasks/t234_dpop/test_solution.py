import base64
import hashlib
import json

import pytest

from solution import DPoPError, DPoPVerifier, jwk_thumbprint

KEY_A = {"kty": "OKP", "crv": "Ed25519", "x": "alice-public-key"}
KEY_B = {"kty": "OKP", "crv": "Ed25519", "x": "mallory-public-key"}
URL = "https://api.example.com/v1/items"
METHOD = "POST"
TOKEN = "access-token-123"
NOW = 10_000


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def jb(obj) -> str:
    return b64(json.dumps(obj).encode())


def sha_b64(text: str) -> str:
    return b64(hashlib.sha256(text.encode()).digest())


def fake_sign(jwk, data: bytes) -> bytes:
    """Підроблений «асиметричний» підпис: детермінований, залежить від ключа й даних."""
    return hashlib.sha256(b"sig|" + jwk["x"].encode() + b"|" + data).digest()


def make_proof(key=KEY_A, header=None, payload=None, sign_with=None, now=NOW, ath=None, tamper_payload=None):
    h = {"typ": "dpop+jwt", "alg": "EdDSA", "jwk": key}
    h.update(header or {})
    p = {"jti": "jti-1", "htm": METHOD, "htu": URL, "iat": now}
    if ath is not None:
        p["ath"] = ath
    p.update(payload or {})
    for k in [k for k, v in list(h.items()) if v is ...]:
        del h[k]
    for k in [k for k, v in list(p.items()) if v is ...]:
        del p[k]
    h_b, p_b = jb(h), jb(p)
    sig = fake_sign(sign_with or key, (h_b + "." + p_b).encode())
    if tamper_payload is not None:
        p_b = jb({**p, **tamper_payload})
    return f"{h_b}.{p_b}.{b64(sig)}"


class Env:
    def __init__(self, **kw):
        self.t = NOW
        self.calls = []
        self.verifier = DPoPVerifier(self.verify, lambda: self.t, **kw)

    def verify(self, jwk, data, sig):
        self.calls.append((jwk, data, sig))
        return sig == fake_sign(jwk, data)

    def check(self, proof, method=METHOD, url=URL, **kw):
        return self.verifier.check(proof, method, url, **kw)


@pytest.fixture
def env():
    return Env()


def reason(proof, env=None, **kw):
    env = env or Env()
    with pytest.raises(DPoPError) as e:
        env.check(proof, **kw)
    return e.value.reason


# --- jwk_thumbprint ----------------------------------------------------------------------------

RFC_N = ("0vx7agoebGcQSuuPiLJXZptN9nndrQmbXEps2aiAFbWhM78LhWx4cbbfAAtVT86zwu1RK7aPFFxuhDR1L6tSoc_BJECPebWKRXjBZCiF"
         "V4n3oknjhMstn64tZ_2W-5JsGY4Hc5n9yBXArwl93lqt7_RN5w6Cf0h4QyQ5v-65YGjQR0_FDW2QvzqY368QQMicAtaSqzs8KJZgnYb9c7d0"
         "zgdAZHzu6qMQvRL5hajrn1n91CbOpbISD08qNLyrdkt-bFTWhAI4vMQFh6WeZu0fM4lFd2NcRwr3XPksINHaQ-G_xBniIqbw0Ls1jF44-csF"
         "Cur-kEgU8awapJzKnqDKgw")


def test_thumbprint_rfc7638_vector():
    jwk = {"kty": "RSA", "n": RFC_N, "e": "AQAB", "alg": "RS256", "kid": "2011-04-29"}
    assert jwk_thumbprint(jwk) == "NzbLsXh8uDCcd-6MNwXF4W_7noWXFZAfHkxZsRGC9Xs"


def test_thumbprint_canonical_form_for_okp_and_ec():
    okp = {"x": "abc", "kty": "OKP", "crv": "Ed25519", "kid": "ignored", "use": "sig"}
    assert jwk_thumbprint(okp) == sha_b64('{"crv":"Ed25519","kty":"OKP","x":"abc"}')
    ec = {"y": "yy", "x": "xx", "crv": "P-256", "kty": "EC"}
    assert jwk_thumbprint(ec) == sha_b64('{"crv":"P-256","kty":"EC","x":"xx","y":"yy"}')


def test_thumbprint_ignores_extra_members_and_key_order():
    base = jwk_thumbprint(KEY_A)
    assert jwk_thumbprint({**KEY_A, "kid": "k1", "alg": "EdDSA"}) == base
    assert jwk_thumbprint(dict(reversed(list(KEY_A.items())))) == base
    assert jwk_thumbprint(KEY_B) != base


@pytest.mark.parametrize("bad", [
    {"kty": "oct", "k": "secret"}, {"kty": "OKP", "crv": "Ed25519"}, {"kty": "EC", "crv": "P-256", "x": "1"},
    {"kty": "RSA", "n": "1"}, {}, {"crv": "Ed25519", "x": "1"}, None, "string",
])
def test_thumbprint_rejects_unusable_keys(bad):
    with pytest.raises(ValueError):
        jwk_thumbprint(bad)


# --- щасливі шляхи -----------------------------------------------------------------------------

def test_token_endpoint_request_without_access_token(env):
    result = env.check(make_proof())
    assert result == {"jkt": jwk_thumbprint(KEY_A), "jti": "jti-1"}


def test_resource_request_bound_token_accepted(env):
    proof = make_proof(ath=sha_b64(TOKEN))
    result = env.check(proof, access_token=TOKEN, token_cnf_jkt=jwk_thumbprint(KEY_A))
    assert result["jkt"] == jwk_thumbprint(KEY_A)


def test_token_endpoint_with_cnf_check_and_ath_ignored_without_access_token(env):
    proof = make_proof(ath="whatever")
    assert env.check(proof, token_cnf_jkt=jwk_thumbprint(KEY_A))["jti"] == "jti-1"


def test_verify_receives_header_key_signing_input_and_decoded_signature(env):
    proof = make_proof()
    h_b, p_b, s_b = proof.split(".")
    env.check(proof)
    assert env.calls == [(KEY_A, (h_b + "." + p_b).encode(), fake_sign(KEY_A, (h_b + "." + p_b).encode()))]


# --- структура proof ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [
    None, 123, b"a.b.c", "", "a", "a.b", "a.b.c.d", "!!!.!!!.!!!", f"{jb([])}.{jb({})}.AAAA", f"{jb({})}.{jb([])}.AAAA",
    f"{jb({})}.{jb(None)}.AAAA", f"{b64(b'not json')}.{jb({})}.AAAA", f"{jb({})}.{b64(b'{broken')}.AAAA",
    "é.é.é",
])
def test_malformed(bad):
    assert reason(bad) == "malformed"


@pytest.mark.parametrize("typ", ["JWT", "DPOP+JWT", "dpop+jwt ", "dpop", None, ..., 5])
def test_bad_typ(typ):
    assert reason(make_proof(header={"typ": typ})) == "bad_typ"


@pytest.mark.parametrize("alg", ["none", "None", "HS256", "HS384", "HS512", "es256", "", None, ..., "RS1"])
def test_bad_alg(alg):
    assert reason(make_proof(header={"alg": alg})) == "bad_alg"


@pytest.mark.parametrize("alg", ["ES256", "ES384", "EdDSA", "PS256", "RS256"])
def test_allowed_algs(alg):
    assert Env().check(make_proof(header={"alg": alg}))["jti"] == "jti-1"


@pytest.mark.parametrize("jwk", [
    ..., None, "key", [KEY_A], {"kty": "oct", "k": "s"}, {"kty": "OKP", "crv": "Ed25519"},
    {**KEY_A, "d": "private-part"}, {**KEY_A, "k": "sym"}, {**KEY_A, "p": "1"}, {"kty": "RSA", "n": "1", "e": "AQAB", "qi": "1"},
])
def test_bad_jwk(jwk):
    assert reason(make_proof(header={"jwk": jwk})) == "bad_jwk"


# --- підпис ------------------------------------------------------------------------------------

def test_signature_by_another_key_is_rejected():
    assert reason(make_proof(key=KEY_A, sign_with=KEY_B)) == "bad_signature"


def test_tampered_payload_after_signing_is_rejected_before_claims_are_trusted():
    proof = make_proof(tamper_payload={"htu": "https://api.example.com/v1/admin", "htm": "DELETE"})
    assert reason(proof, method="DELETE", url="https://api.example.com/v1/admin") == "bad_signature"


@pytest.mark.parametrize("answer", [False, None, 0, 1, "ok", [True], ...])
def test_only_exactly_true_counts_as_valid_signature(answer):
    e = Env()
    if answer is ...:
        def verify(*a):
            raise RuntimeError("crypto backend crashed")
    else:
        def verify(*a):
            return answer
    e.verifier = DPoPVerifier(verify, lambda: NOW)
    assert reason(make_proof(), env=e) == "bad_signature"


def test_unsigned_proof_is_rejected():
    h_b, p_b, _ = make_proof().split(".")
    assert reason(f"{h_b}.{p_b}.") == "bad_signature"


# --- claims ------------------------------------------------------------------------------------

@pytest.mark.parametrize("claim, value", [
    ("jti", ...), ("jti", ""), ("jti", 123), ("jti", None), ("htm", ...), ("htm", None), ("htm", 5),
    ("htu", ...), ("htu", 5), ("htu", None), ("iat", ...), ("iat", "10000"), ("iat", None), ("iat", True), ("iat", [NOW]),
])
def test_bad_claims(claim, value):
    assert reason(make_proof(payload={claim: value})) == "bad_claims"


@pytest.mark.parametrize("method", ["post", "GET", "Post", "", "POST "])
def test_htm_must_match_exactly(method):
    assert reason(make_proof(), method=method) == "htm_mismatch"


@pytest.mark.parametrize("htu, request_url", [
    (URL, URL), (URL, URL + "?page=2&sort=asc"), (URL, URL + "#frag"), (URL, URL + "?a=1#b"),
    ("https://api.example.com/v1/items", "HTTPS://API.Example.COM/v1/items"),
    ("https://api.example.com/v1/items", "https://api.example.com:443/v1/items"),
    ("https://api.example.com:443/v1/items", "https://api.example.com/v1/items"),
    ("http://api.example.com/v1/items", "http://api.example.com:80/v1/items"),
    ("https://api.example.com", "https://api.example.com/"), ("https://api.example.com/", "https://api.example.com"),
    ("https://api.example.com:8443/x", "https://api.example.com:8443/x?q=1"),
])
def test_htu_accepts_equivalent_urls(htu, request_url):
    assert Env().check(make_proof(payload={"htu": htu}), url=request_url)["jti"] == "jti-1"


@pytest.mark.parametrize("htu, request_url", [
    (URL + "?page=2", URL + "?page=2"),  # htu не повинен містити query
    (URL + "#f", URL), (URL + "?", URL),
    (URL, "https://api.example.com/v1/items/"), ("https://api.example.com/v1/items/", URL),
    (URL, "https://api.example.com/V1/items"), (URL, "http://api.example.com/v1/items"),
    (URL, "https://api.example.com:8443/v1/items"), (URL, "https://evil.example.com/v1/items"),
    (URL, "https://api.example.com.evil.com/v1/items"), ("https://api.example.com:80/v1/items", "https://api.example.com/v1/items"),
    (URL, "https://api.example.com/v1/other"), ("http://api.example.com:443/x", "http://api.example.com/x"),
])
def test_htu_mismatch(htu, request_url):
    assert reason(make_proof(payload={"htu": htu}), url=request_url) == "htu_mismatch"


@pytest.mark.parametrize("delta, ok", [(0, True), (-60, True), (60, True), (-61, False), (61, False), (-3600, False),
                                       (3600, False), (-59.5, True), (60.5, False)])
def test_iat_window_is_symmetric_and_inclusive(delta, ok):
    proof = make_proof(payload={"iat": NOW + delta})
    if ok:
        assert Env().check(proof)["jti"] == "jti-1"
    else:
        assert reason(proof) == "expired"


def test_custom_window():
    e = Env(iat_window=5)
    assert e.check(make_proof(payload={"iat": NOW - 5}))["jti"] == "jti-1"
    assert reason(make_proof(payload={"iat": NOW - 6, "jti": "j2"}), env=e) == "expired"


# --- привʼязка до access-токена ----------------------------------------------------------------

def test_ath_must_match_token_hash(env):
    cnf = jwk_thumbprint(KEY_A)
    assert reason(make_proof(ath=sha_b64("other-token")), env=env, access_token=TOKEN, token_cnf_jkt=cnf) == "bad_ath"
    assert reason(make_proof(), env=Env(), access_token=TOKEN, token_cnf_jkt=cnf) == "bad_ath"
    assert reason(make_proof(ath=TOKEN), env=Env(), access_token=TOKEN, token_cnf_jkt=cnf) == "bad_ath"
    assert reason(make_proof(payload={"ath": 5}), env=Env(), access_token=TOKEN, token_cnf_jkt=cnf) == "bad_ath"


def test_token_without_cnf_is_not_accepted_with_dpop(env):
    assert reason(make_proof(ath=sha_b64(TOKEN)), env=env, access_token=TOKEN, token_cnf_jkt=None) == "unbound_token"


def test_proof_from_another_key_does_not_work_with_stolen_token():
    stolen_cnf = jwk_thumbprint(KEY_A)
    attacker_proof = make_proof(key=KEY_B, ath=sha_b64(TOKEN))  # власний ключ, валідний підпис, чужий токен
    assert reason(attacker_proof, access_token=TOKEN, token_cnf_jkt=stolen_cnf) == "key_mismatch"


def test_key_mismatch_also_at_token_endpoint():
    assert reason(make_proof(key=KEY_B), token_cnf_jkt=jwk_thumbprint(KEY_A)) == "key_mismatch"


def test_same_key_with_extra_jwk_members_matches_cnf():
    cnf = jwk_thumbprint(KEY_A)
    proof = make_proof(key={**KEY_A, "kid": "k-77", "use": "sig"})
    assert Env().check(proof, token_cnf_jkt=cnf)["jkt"] == cnf


# --- повтори -----------------------------------------------------------------------------------

def test_same_proof_twice_is_replay(env):
    proof = make_proof()
    env.check(proof)
    assert reason(proof, env=env) == "replay"


def test_replay_of_captured_proof_for_other_endpoint_is_htu_mismatch(env):
    proof = make_proof()
    env.check(proof)
    assert reason(proof, env=env, url="https://api.example.com/v1/admin") == "htu_mismatch"


def test_same_jti_from_another_key_is_not_replay(env):
    env.check(make_proof(key=KEY_A))
    assert env.check(make_proof(key=KEY_B))["jkt"] == jwk_thumbprint(KEY_B)


def test_different_jti_is_fine(env):
    env.check(make_proof(payload={"jti": "a"}))
    env.check(make_proof(payload={"jti": "b"}))


def test_rejected_proof_does_not_burn_jti(env):
    assert reason(make_proof(), env=env, method="GET") == "htm_mismatch"
    assert reason(make_proof(), env=env, access_token=TOKEN, token_cnf_jkt=jwk_thumbprint(KEY_B)) == "bad_ath"
    assert env.check(make_proof())["jti"] == "jti-1"


def test_replay_after_window_is_expired_not_accepted(env):
    proof = make_proof()
    env.check(proof)
    env.t += 61
    assert reason(proof, env=env) == "expired"


def test_replay_inside_window_after_time_passes(env):
    proof = make_proof()
    env.check(proof)
    env.t += 30
    assert reason(proof, env=env) == "replay"


def test_many_unique_proofs_over_time_keep_working(env):
    for i in range(300):
        env.t = NOW + i * 7
        assert env.check(make_proof(now=env.t, payload={"jti": f"j{i}"}))["jti"] == f"j{i}"
