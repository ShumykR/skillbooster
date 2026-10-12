import base64
import hashlib
import inspect
import json
import re
from urllib.parse import parse_qs, urlparse

import pytest

import solution
from solution import OAuthClient, OAuthError, code_challenge, new_verifier

CLIENT_ID = "my-app"
REDIRECT = "https://app.example/callback"
ISSUER = "https://idp.example"
AUTHORIZE = "https://idp.example/authorize"


def b64(data: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


def make_jwt(claims: dict) -> str:
    return f"{b64({'alg': 'RS256'})}.{b64(claims)}.sig"


class Clock:
    def __init__(self, now=1_700_000_000.0):
        self.now = now

    def __call__(self):
        return self.now


class Entropy:
    """Детермінована «випадковість»: кожен виклик дає інші байти."""

    def __init__(self):
        self.n = 0

    def __call__(self, size):
        self.n += 1
        return bytes((self.n * 31 + i * 7) % 256 for i in range(size))


class Provider:
    """Мок-провайдер: сам перевіряє PKCE, redirect_uri та одноразовість коду, як справжній."""

    def __init__(self, clock):
        self.clock = clock
        self.codes = {}
        self.exchanges = 0
        self.tweak = {}  # зіпсувати відповідь: {"aud": "other"} тощо
        self.raise_on_exchange = None

    def authorize(self, url, user="user-1"):
        q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        assert urlparse(url).geturl().startswith(AUTHORIZE)
        assert q["response_type"] == "code" and q["client_id"] == CLIENT_ID and q["redirect_uri"] == REDIRECT
        assert q["code_challenge_method"] == "S256", "PKCE має бути S256, не plain"
        assert set(q["scope"].split(" ")) == {"openid", "email"}
        code = f"code-{len(self.codes) + 1}"
        self.codes[code] = {"challenge": q["code_challenge"], "redirect_uri": q["redirect_uri"], "nonce": q["nonce"], "user": user}
        return {"code": code, "state": q["state"]}

    def exchange(self, *, code, code_verifier, redirect_uri, client_id):
        self.exchanges += 1
        if self.raise_on_exchange:
            raise self.raise_on_exchange
        entry = self.codes.pop(code, None)
        if entry is None:
            raise RuntimeError("invalid_grant: unknown or reused code")
        expected = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode("ascii")).digest()).rstrip(b"=").decode()
        if expected != entry["challenge"]:
            raise RuntimeError("invalid_grant: PKCE verification failed")
        if redirect_uri != entry["redirect_uri"] or client_id != CLIENT_ID:
            raise RuntimeError("invalid_grant: redirect_uri/client mismatch")
        claims = {"iss": ISSUER, "aud": CLIENT_ID, "sub": entry["user"], "email": f"{entry['user']}@example.com",
                  "exp": self.clock.now + 3600, "nonce": entry["nonce"]}
        claims.update({k: v for k, v in self.tweak.items() if k not in ("token_type", "access_token", "id_token", "drop_id_token")})
        response = {"access_token": "at-123", "token_type": "Bearer", "expires_in": 3600, "id_token": make_jwt(claims)}
        for k in ("token_type", "access_token"):
            if k in self.tweak:
                response[k] = self.tweak[k]
        if self.tweak.get("drop_id_token"):
            del response["id_token"]
        return response


@pytest.fixture
def env():
    clock = Clock()
    provider = Provider(clock)
    client = OAuthClient(CLIENT_ID, REDIRECT, AUTHORIZE, ISSUER, provider.exchange, Entropy(), clock)
    return client, provider, clock, {}


# ---------- PKCE ---------------------------------------------------------------


def test_code_challenge_matches_rfc7636_vector():
    assert code_challenge("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk") == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_verifier_shape_and_uniqueness():
    ent = Entropy()
    a, b = new_verifier(ent), new_verifier(ent)
    assert a != b
    for v in (a, b):
        assert 43 <= len(v) <= 128 and re.fullmatch(r"[A-Za-z0-9\-._~]+", v)


# ---------- start --------------------------------------------------------------


def test_start_builds_authorization_url_and_remembers_secrets_in_session(env):
    client, _, _, session = env
    url = client.start(session)
    q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
    assert url.startswith(AUTHORIZE + "?")
    assert (q["response_type"], q["client_id"], q["redirect_uri"]) == ("code", CLIENT_ID, REDIRECT)
    assert q["scope"] == "openid email" and q["code_challenge_method"] == "S256"
    saved = session["oauth"]
    assert q["state"] == saved["state"] and q["nonce"] == saved["nonce"]
    assert q["code_challenge"] == code_challenge(saved["verifier"])
    assert saved["verifier"] not in url, "verifier ніколи не йде у браузер"
    assert len({saved["state"], saved["nonce"], saved["verifier"]}) == 3
    assert saved["created_at"] == 1_700_000_000.0


def test_each_login_attempt_gets_fresh_state(env):
    client, _, _, _ = env
    s1, s2 = {}, {}
    client.start(s1)
    client.start(s2)
    assert s1["oauth"]["state"] != s2["oauth"]["state"]
    assert s1["oauth"]["verifier"] != s2["oauth"]["verifier"]


# ---------- callback: успіх ----------------------------------------------------


def test_full_login_flow(env):
    client, provider, clock, session = env
    params = provider.authorize(client.start(session), user="alice")
    clock.now += 30
    login = client.callback(session, params)
    assert (login.subject, login.email, login.access_token) == ("alice", "alice@example.com", "at-123")
    assert login.expires_at == clock.now + 3600
    assert "oauth" not in session


def test_two_logins_in_parallel_sessions_do_not_interfere(env):
    client, provider, _, _ = env
    sa, sb = {}, {}
    pa = provider.authorize(client.start(sa), user="alice")
    pb = provider.authorize(client.start(sb), user="bob")
    assert client.callback(sb, pb).subject == "bob"
    assert client.callback(sa, pa).subject == "alice"


# ---------- callback: захист --------------------------------------------------


def test_state_mismatch_is_rejected_before_any_exchange(env):
    client, provider, _, session = env
    params = provider.authorize(client.start(session))
    with pytest.raises(OAuthError):
        client.callback(session, {**params, "state": "forged"})
    assert provider.exchanges == 0


def test_login_cross_session_code_is_rejected(env):
    # атакувальник підсовує жертві СВІЙ code+state: state не збігається зі станом сесії жертви
    client, provider, _, victim = env
    client.start(victim)
    attacker_params = provider.authorize(client.start({}), user="attacker")
    with pytest.raises(OAuthError):
        client.callback(victim, attacker_params)
    assert provider.exchanges == 0


@pytest.mark.parametrize("drop", ["state", "code"])
def test_missing_state_or_code_is_rejected(env, drop):
    client, provider, _, session = env
    params = provider.authorize(client.start(session))
    params.pop(drop)
    with pytest.raises(OAuthError):
        client.callback(session, params)


def test_callback_is_single_use(env):
    client, provider, _, session = env
    params = provider.authorize(client.start(session))
    client.callback(session, params)
    with pytest.raises(OAuthError):
        client.callback(session, params)
    assert provider.exchanges == 1


def test_failed_attempt_also_consumes_the_pending_login(env):
    client, provider, _, session = env
    params = provider.authorize(client.start(session))
    with pytest.raises(OAuthError):
        client.callback(session, {**params, "state": "bad"})
    with pytest.raises(OAuthError):
        client.callback(session, params)  # правильні параметри вже не допоможуть
    assert provider.exchanges == 0


def test_provider_error_is_surfaced_without_exchange(env):
    client, provider, _, session = env
    client.start(session)
    with pytest.raises(OAuthError, match="access_denied"):
        client.callback(session, {"error": "access_denied", "state": session["oauth"]["state"]})
    assert provider.exchanges == 0


def test_pending_login_expires_after_600_seconds(env):
    client, provider, clock, session = env
    params = provider.authorize(client.start(session))
    clock.now += 601
    with pytest.raises(OAuthError):
        client.callback(session, params)
    assert provider.exchanges == 0


def test_login_at_exactly_600_seconds_still_works(env):
    client, provider, clock, session = env
    params = provider.authorize(client.start(session))
    clock.now += 600
    assert client.callback(session, params).subject == "user-1"


def test_callback_without_start_is_rejected(env):
    client, _, _, session = env
    with pytest.raises(OAuthError):
        client.callback(session, {"code": "x", "state": "y"})


def test_exchange_failure_becomes_oauth_error(env):
    client, provider, _, session = env
    params = provider.authorize(client.start(session))
    provider.raise_on_exchange = TimeoutError("idp down")
    with pytest.raises(OAuthError):
        client.callback(session, params)


# ---------- callback: перевірка відповіді провайдера ---------------------------


@pytest.mark.parametrize("tweak", [
    {"iss": "https://evil.example"},
    {"aud": "someone-else"},
    {"aud": ["a", "b"]},
    {"exp": 1_700_000_000.0 - 1},
    {"nonce": "replayed-nonce"},
    {"token_type": "MAC"},
    {"access_token": ""},
    {"drop_id_token": True},
])
def test_bad_provider_response_is_rejected(env, tweak):
    client, provider, _, session = env
    provider.tweak = tweak
    params = provider.authorize(client.start(session))
    with pytest.raises(OAuthError):
        client.callback(session, params)


def test_audience_list_containing_client_id_is_accepted(env):
    client, provider, _, session = env
    provider.tweak = {"aud": ["other", CLIENT_ID]}
    assert client.callback(session, provider.authorize(client.start(session))).subject == "user-1"


def test_bearer_token_type_is_case_insensitive(env):
    client, provider, _, session = env
    provider.tweak = {"token_type": "bearer"}
    assert client.callback(session, provider.authorize(client.start(session))).access_token == "at-123"


def test_state_comparison_is_constant_time():
    source = inspect.getsource(solution.OAuthClient)
    assert "compare_digest" in source, "state порівнюється через hmac.compare_digest"
