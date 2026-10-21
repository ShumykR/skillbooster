import base64
import hashlib
from urllib.parse import parse_qs, urlparse

import pytest

from solution import AuthorizationServer, OAuthError

CB = "https://app.example.com/cb"
LOOP = "http://127.0.0.1/cb"
VERIFIER = "v" * 43 + "-._~" + "A1"  # 49 символів, усі дозволені


def challenge_of(verifier):
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")


class Env:
    def __init__(self, **kw):
        self.t = 1000
        self.n = 0
        clients = {
            "spa": {"redirect_uris": [CB, LOOP], "scopes": ["read", "write", "profile"]},
            "other": {"redirect_uris": ["https://other.example.org/cb"], "scopes": ["read"]},
        }
        self.server = AuthorizationServer(clients, clock=lambda: self.t, token_factory=self.new_token, **kw)

    def new_token(self):
        self.n += 1
        return f"tok-{self.n:04d}"

    def authorize(self, **over):
        args = dict(client_id="spa", redirect_uri=CB, response_type="code", code_challenge=challenge_of(VERIFIER),
                    code_challenge_method="S256", scope="read", user_id="u1", state=None)
        args.update(over)
        return self.server.authorize(**args)

    def code(self, **over):
        return parse_qs(urlparse(self.authorize(**over)).query)["code"][0]

    def exchange(self, code, **over):
        args = dict(client_id="spa", code=code, redirect_uri=CB, code_verifier=VERIFIER)
        args.update(over)
        return self.server.token("authorization_code", **args)

    def login(self, **over):
        return self.exchange(self.code(**over.pop("auth", {})), **over)

    def refresh(self, rt, **over):
        args = dict(client_id="spa", refresh_token=rt)
        args.update(over)
        return self.server.token("refresh_token", **args)


@pytest.fixture
def env():
    return Env()


def err(exc_info):
    return exc_info.value.error


# --- реєстрація клієнтів -----------------------------------------------------------------------

@pytest.mark.parametrize("uri", [
    "https://*.example.com/cb", "https://app.example.com/*", "http://app.example.com/cb",
    "https://app.example.com/cb#frag", "ftp://app.example.com/cb", "myapp://cb", "//app.example.com/cb",
])
def test_registration_rejects_unsafe_redirect_uris(uri):
    with pytest.raises(ValueError):
        AuthorizationServer({"c": {"redirect_uris": [uri], "scopes": []}}, lambda: 0, lambda: "x")


@pytest.mark.parametrize("uris", [[], None, "https://app.example.com/cb"])
def test_registration_requires_list_of_uris(uris):
    with pytest.raises(ValueError):
        AuthorizationServer({"c": {"redirect_uris": uris, "scopes": []}}, lambda: 0, lambda: "x")


def test_registration_allows_https_and_loopback():
    AuthorizationServer({"c": {"redirect_uris": [CB, "http://127.0.0.1:8080/cb", "http://localhost/cb"],
                               "scopes": []}}, lambda: 0, lambda: "x")


# --- authorize ---------------------------------------------------------------------------------

def test_authorize_returns_redirect_with_code_and_state(env):
    url = env.authorize(state="xyz 1&2")
    parsed = urlparse(url)
    assert url.startswith(CB + "?")
    qs = parse_qs(parsed.query)
    assert qs["code"] == ["tok-0001"]
    assert qs["state"] == ["xyz 1&2"]
    assert "state=xyz+1%262" in url or "state=xyz%201%262" in url


def test_authorize_without_state_has_no_state(env):
    qs = parse_qs(urlparse(env.authorize()).query)
    assert "state" not in qs and "code" in qs


def test_authorize_appends_with_ampersand_when_uri_has_query():
    e = Env()
    e.server = AuthorizationServer({"spa": {"redirect_uris": ["https://app.example.com/cb?tenant=a"],
                                            "scopes": ["read"]}}, lambda: 0, e.new_token)
    url = e.authorize(redirect_uri="https://app.example.com/cb?tenant=a", state="s")
    qs = parse_qs(urlparse(url).query)
    assert qs["tenant"] == ["a"] and qs["code"] and qs["state"] == ["s"]


def test_unknown_client(env):
    with pytest.raises(OAuthError) as e:
        env.authorize(client_id="ghost")
    assert err(e) == "invalid_client"


@pytest.mark.parametrize("uri", [
    "https://app.example.com/cb/", "https://app.example.com/cb?x=1", "https://app.example.com/cb#f",
    "https://app.example.com/c", "https://app.example.com/cb/extra", "https://app.example.com.evil.com/cb",
    "https://evil.com/?https://app.example.com/cb", "https://app.example.com/cb/../x", "HTTPS://app.example.com/cb",
    "https://APP.example.com/cb", " https://app.example.com/cb", "https://app.example.com/cb ",
    "https://app.example.com:443/cb", "http://app.example.com/cb", "https://app.example.com", "", None,
    "https://other.example.org/cb", "http://127.0.0.1:9999/cb", "https://app.example.com/CB",
])
def test_redirect_uri_must_match_exactly(env, uri):
    with pytest.raises(OAuthError) as e:
        env.authorize(redirect_uri=uri)
    assert err(e) == "invalid_request"
    assert env.n == 0  # код не видано


def test_second_registered_uri_works(env):
    assert env.authorize(redirect_uri=LOOP).startswith(LOOP + "?code=")


@pytest.mark.parametrize("rt", ["token", "id_token", "code token", "CODE", "", None])
def test_only_code_response_type(env, rt):
    with pytest.raises(OAuthError) as e:
        env.authorize(response_type=rt)
    assert err(e) == "unsupported_response_type"


@pytest.mark.parametrize("ch, method", [
    (None, "S256"), ("", "S256"), (challenge_of(VERIFIER), "plain"), (challenge_of(VERIFIER), None),
    (challenge_of(VERIFIER), "s256"), (challenge_of(VERIFIER), ""), (challenge_of(VERIFIER)[:42], "S256"),
    (challenge_of(VERIFIER) + "A", "S256"), ("!" * 43, "S256"), (challenge_of(VERIFIER) + "=", "S256"),
    (123, "S256"),
])
def test_pkce_s256_is_mandatory(env, ch, method):
    with pytest.raises(OAuthError) as e:
        env.authorize(code_challenge=ch, code_challenge_method=method)
    assert err(e) == "invalid_request"
    assert env.n == 0


def test_scope_must_be_subset_and_is_normalized(env):
    with pytest.raises(OAuthError) as e:
        env.authorize(scope="read admin")
    assert err(e) == "invalid_scope"
    tokens = env.login(auth={"scope": "write read read"})
    assert tokens["scope"] == "read write"
    assert env.login(auth={"scope": None})["scope"] == ""


# --- обмін коду --------------------------------------------------------------------------------

def test_successful_exchange_and_introspection(env):
    tokens = env.login(auth={"scope": "read profile"})
    assert tokens["token_type"] == "Bearer"
    assert tokens["expires_in"] == 300
    assert tokens["scope"] == "profile read"
    assert tokens["access_token"] != tokens["refresh_token"]
    info = env.server.introspect(tokens["access_token"])
    assert info == {"active": True, "client_id": "spa", "user_id": "u1", "scope": "profile read", "exp": 1300}


def test_rfc7636_known_answer():
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    assert challenge_of(verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    e = Env()
    code = e.code(code_challenge="E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM")
    assert e.exchange(code, code_verifier=verifier)["token_type"] == "Bearer"


@pytest.mark.parametrize("verifier", [
    "w" * 49, VERIFIER[:-1], VERIFIER + "x", "", None, "short", "v" * 129, "v" * 42 + "!" * 7, 12345,
    challenge_of(VERIFIER),
])
def test_wrong_or_malformed_verifier(env, verifier):
    code = env.code()
    with pytest.raises(OAuthError) as e:
        env.exchange(code, code_verifier=verifier)
    assert err(e) == "invalid_grant"


def test_failed_attempt_burns_the_code(env):
    code = env.code()
    with pytest.raises(OAuthError):
        env.exchange(code, code_verifier="w" * 49)
    with pytest.raises(OAuthError) as e:
        env.exchange(code)
    assert err(e) == "invalid_grant"


@pytest.mark.parametrize("uri", [None, "", CB + "/", "https://app.example.com/other", LOOP])
def test_redirect_uri_must_match_authorize_request(env, uri):
    code = env.code()
    with pytest.raises(OAuthError) as e:
        env.exchange(code, redirect_uri=uri)
    assert err(e) == "invalid_grant"


def test_unknown_code(env):
    with pytest.raises(OAuthError) as e:
        env.exchange("nope")
    assert err(e) == "invalid_grant"
    with pytest.raises(OAuthError) as e:
        env.server.token("authorization_code", client_id="spa", redirect_uri=CB, code_verifier=VERIFIER)
    assert err(e) == "invalid_grant"


def test_code_of_other_client_is_refused_and_not_burned(env):
    code = env.code()
    with pytest.raises(OAuthError) as e:
        env.exchange(code, client_id="other")
    assert err(e) == "invalid_grant"
    assert env.exchange(code)["token_type"] == "Bearer"  # законний власник ще може обміняти


def test_code_expiry_boundary(env):
    code = env.code()
    env.t += 59
    assert env.exchange(code)["token_type"] == "Bearer"
    code = env.code()
    env.t += 60
    with pytest.raises(OAuthError) as e:
        env.exchange(code)
    assert err(e) == "invalid_grant"


def test_custom_code_ttl():
    e = Env(code_ttl=5)
    code = e.code()
    e.t += 5
    with pytest.raises(OAuthError):
        e.exchange(code)


def test_code_is_single_use_and_replay_revokes_issued_tokens(env):
    code = env.code()
    tokens = env.exchange(code)
    assert env.server.introspect(tokens["access_token"])["active"] is True
    with pytest.raises(OAuthError) as e:
        env.exchange(code)
    assert err(e) == "invalid_grant"
    assert env.server.introspect(tokens["access_token"]) == {"active": False}
    with pytest.raises(OAuthError) as e:
        env.refresh(tokens["refresh_token"])
    assert err(e) == "invalid_grant"


def test_code_replay_does_not_touch_other_sessions(env):
    other = env.login()
    code = env.code()
    env.exchange(code)
    with pytest.raises(OAuthError):
        env.exchange(code)
    assert env.server.introspect(other["access_token"])["active"] is True
    assert env.refresh(other["refresh_token"])["token_type"] == "Bearer"


@pytest.mark.parametrize("grant", ["password", "implicit", "client_credentials", "token", "", None,
                                   "urn:ietf:params:oauth:grant-type:device_code", "AUTHORIZATION_CODE"])
def test_unsupported_grant_types(env, grant):
    with pytest.raises(OAuthError) as e:
        env.server.token(grant, client_id="spa", username="alice", password="pw", scope="read")
    assert err(e) == "unsupported_grant_type"


# --- refresh-токени ----------------------------------------------------------------------------

def test_refresh_rotates_both_tokens(env):
    first = env.login()
    second = env.refresh(first["refresh_token"])
    assert second["refresh_token"] != first["refresh_token"]
    assert second["access_token"] != first["access_token"]
    assert second["scope"] == "read" and second["token_type"] == "Bearer" and second["expires_in"] == 300
    assert env.server.introspect(second["access_token"])["user_id"] == "u1"


def test_reuse_of_rotated_refresh_token_revokes_whole_family(env):
    first = env.login()
    second = env.refresh(first["refresh_token"])
    third = env.refresh(second["refresh_token"])
    with pytest.raises(OAuthError) as e:
        env.refresh(first["refresh_token"])  # зловмисник пред'являє найстарший токен
    assert err(e) == "invalid_grant"
    for tokens in (first, second, third):
        assert env.server.introspect(tokens["access_token"]) == {"active": False}
    with pytest.raises(OAuthError) as e:
        env.refresh(third["refresh_token"])  # чесний клієнт теж втратив доступ: має увійти знову
    assert err(e) == "invalid_grant"


def test_family_revocation_leaves_other_families(env):
    mine = env.login()
    other = env.login()
    env.refresh(mine["refresh_token"])
    with pytest.raises(OAuthError):
        env.refresh(mine["refresh_token"])
    assert env.server.introspect(other["access_token"])["active"] is True
    assert env.refresh(other["refresh_token"])["token_type"] == "Bearer"


def test_refresh_expiry_boundary_and_sliding_chain(env):
    first = env.login()
    env.t += 86399
    second = env.refresh(first["refresh_token"])
    env.t += 86399  # від другого токена ще не минула доба, хоч від першого минуло майже дві
    third = env.refresh(second["refresh_token"])
    env.t += 86400
    with pytest.raises(OAuthError) as e:
        env.refresh(third["refresh_token"])
    assert err(e) == "invalid_grant"


def test_expired_refresh_with_custom_ttl():
    e = Env(refresh_ttl=100)
    tokens = e.login()
    e.t += 100
    with pytest.raises(OAuthError):
        e.refresh(tokens["refresh_token"])


def test_unknown_refresh_token(env):
    for rt in ("nope", None, ""):
        with pytest.raises(OAuthError) as e:
            env.refresh(rt)
        assert err(e) == "invalid_grant"


def test_refresh_by_other_client_is_refused_without_side_effects(env):
    tokens = env.login()
    with pytest.raises(OAuthError) as e:
        env.refresh(tokens["refresh_token"], client_id="other")
    assert err(e) == "invalid_grant"
    assert env.server.introspect(tokens["access_token"])["active"] is True
    assert env.refresh(tokens["refresh_token"])["token_type"] == "Bearer"
    # і повтор уже використаного токена чужим клієнтом не відкликає родину
    a = env.login()
    b = env.refresh(a["refresh_token"])
    with pytest.raises(OAuthError):
        env.refresh(a["refresh_token"], client_id="other")
    assert env.server.introspect(b["access_token"])["active"] is True


def test_refresh_scope_can_only_narrow(env):
    tokens = env.login(auth={"scope": "read write"})
    with pytest.raises(OAuthError) as e:
        env.refresh(tokens["refresh_token"], scope="read write profile")
    assert err(e) == "invalid_scope"
    narrowed = env.refresh(tokens["refresh_token"], scope="write")  # токен не витрачено невдалою спробою
    assert narrowed["scope"] == "write"
    assert env.server.introspect(narrowed["access_token"])["scope"] == "write"
    with pytest.raises(OAuthError) as e:
        env.refresh(narrowed["refresh_token"], scope="read")  # вже звужений: розширити не можна
    assert err(e) == "invalid_scope"
    assert env.refresh(narrowed["refresh_token"])["scope"] == "write"


# --- access-токени -----------------------------------------------------------------------------

def test_access_token_expiry_boundary(env):
    tokens = env.login()
    env.t += 299
    assert env.server.introspect(tokens["access_token"])["active"] is True
    env.t += 1
    assert env.server.introspect(tokens["access_token"]) == {"active": False}


def test_introspect_unknown_token(env):
    for t in ("nope", None, ""):
        assert env.server.introspect(t) == {"active": False}


def test_custom_access_ttl_is_reported():
    e = Env(access_ttl=60)
    tokens = e.login()
    assert tokens["expires_in"] == 60
    assert e.server.introspect(tokens["access_token"])["exp"] == 1060
