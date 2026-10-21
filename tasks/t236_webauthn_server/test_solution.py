import hashlib
import hmac
import itertools
import json

import pytest

import solution
from solution import BE, BS, UP, UV

RP = "example.com"
ORIGIN = "https://example.com"
NOW = 1_800_000_000


class Clock:
    def __init__(self, t=NOW):
        self.t = t

    def __call__(self):
        return self.t


class Verifier:
    """Підроблений перевіряльник: «приватний» ключ збігається з public_key (симетрично), підробка без нього неможлива."""

    def __init__(self):
        self.calls = []
        self.override = None

    def __call__(self, public_key, data, signature):
        self.calls.append((public_key, data, signature))
        if isinstance(self.override, Exception):
            raise self.override
        if self.override is not None:
            return self.override
        return hmac.compare_digest(hmac.new(public_key, data, hashlib.sha256).digest(), signature)


class Authenticator:
    def __init__(self, cred_id="cred-1", secret=b"authn-secret-1", flags=UP | UV, counter=0):
        self.cred_id, self.secret, self.flags, self.counter = cred_id, secret, flags, counter

    @staticmethod
    def auth_data(flags, counter, rp=RP):
        return hashlib.sha256(rp.encode()).digest() + bytes([flags]) + counter.to_bytes(4, "big")

    def _client_data(self, typ, challenge, origin, cross_origin):
        cd = {"type": typ, "challenge": challenge, "origin": origin}
        if cross_origin is not None:
            cd["crossOrigin"] = cross_origin
        return json.dumps(cd).encode()

    def register(self, challenge, *, typ="webauthn.create", origin=ORIGIN, rp=RP, flags=None, counter=None,
                 cross_origin=None):
        flags = self.flags if flags is None else flags
        counter = self.counter if counter is None else counter
        return {"client_data_json": self._client_data(typ, challenge, origin, cross_origin),
                "authenticator_data": self.auth_data(flags, counter, rp),
                "credential_id": self.cred_id, "public_key": self.secret}

    def assertion(self, challenge, *, typ="webauthn.get", origin=ORIGIN, rp=RP, flags=None, counter=None,
                  cross_origin=None, user_handle=None, cred_id=None):
        flags = self.flags if flags is None else flags
        counter = self.counter if counter is None else counter
        cdj = self._client_data(typ, challenge, origin, cross_origin)
        ad = self.auth_data(flags, counter, rp)
        sig = hmac.new(self.secret, ad + hashlib.sha256(cdj).digest(), hashlib.sha256).digest()
        return {"client_data_json": cdj, "authenticator_data": ad, "credential_id": cred_id or self.cred_id,
                "signature": sig, "user_handle": user_handle}


def make_server(**kw):
    clock, verifier = Clock(), Verifier()
    counter = itertools.count(1)
    codes = itertools.count(1)
    params = dict(clock=clock, verify=verifier, new_challenge=lambda: f"chal-{next(counter)}",
                  new_recovery_code=lambda: f"ab12-cd34-{next(codes):04d}")
    params.update(kw)
    return solution.WebAuthnServer(RP, [ORIGIN, "https://login.example.com"], **params), clock, verifier


def code_of(fn, *args):
    with pytest.raises(solution.WebAuthnError) as ei:
        fn(*args)
    return ei.value.code


def registered(server, user="alice", auth=None, **kw):
    auth = auth or Authenticator()
    ch = server.begin_registration(user)["challenge"]
    server.finish_registration(auth.register(ch, **kw))
    return auth


# --- begin_* -----------------------------------------------------------------------------------

def test_begin_registration_and_authentication_shape():
    s, _, _ = make_server()
    r = s.begin_registration("alice")
    assert r["challenge"] == "chal-1" and r["rp_id"] == RP and r["user_verification"] == "required"
    a = s.begin_authentication("alice")
    assert a["challenge"] == "chal-2" and a["allow_credentials"] == [] and a["user_verification"] == "required"
    registered(s, "alice", Authenticator("b-cred", b"k2"))
    registered(s, "alice", Authenticator("a-cred", b"k3"))
    registered(s, "bob", Authenticator("c-cred", b"k4"))
    assert s.begin_authentication("alice")["allow_credentials"] == ["a-cred", "b-cred"]
    assert s.begin_authentication()["allow_credentials"] == []


def test_user_verification_preferred_when_not_required():
    s, _, _ = make_server(require_user_verification=False)
    assert s.begin_registration("a")["user_verification"] == "preferred"
    assert s.begin_authentication()["user_verification"] == "preferred"


# --- реєстрація --------------------------------------------------------------------------------

def test_registration_happy_path():
    s, _, _ = make_server()
    ch = s.begin_registration("alice")["challenge"]
    res = s.finish_registration(Authenticator().register(ch, flags=UP | UV | BE | BS, counter=0))
    assert res == {"credential_id": "cred-1", "user_id": "alice", "backup_eligible": True, "backup_state": True,
                   "sign_count": 0}
    assert s.list_credentials("alice") == ["cred-1"]
    assert s.list_credentials("bob") == []


@pytest.mark.parametrize("override, expected", [
    ({"typ": "webauthn.get"}, "bad_type"),
    ({"typ": "other"}, "bad_type"),
    ({"origin": "https://evil.example.net"}, "bad_origin"),
    ({"origin": "https://example.com/"}, "bad_origin"),
    ({"origin": "http://example.com"}, "bad_origin"),
    ({"origin": "https://sub.example.com"}, "bad_origin"),
    ({"origin": "https://example.com.evil.io"}, "bad_origin"),
    ({"cross_origin": True}, "bad_origin"),
    ({"rp": "evil.com"}, "bad_rp_id"),
    ({"rp": "sub.example.com"}, "bad_rp_id"),
    ({"flags": UV}, "user_not_present"),
    ({"flags": 0}, "user_not_present"),
    ({"flags": UP}, "user_not_verified"),
    ({"flags": UP | UV | BS}, "bad_flags"),
])
def test_registration_checks(override, expected):
    s, _, _ = make_server()
    ch = s.begin_registration("alice")["challenge"]
    assert code_of(s.finish_registration, Authenticator().register(ch, **override)) == expected
    assert s.list_credentials("alice") == []


def test_registration_accepts_second_origin_and_cross_origin_false():
    s, _, _ = make_server()
    ch = s.begin_registration("alice")["challenge"]
    s.finish_registration(Authenticator().register(ch, origin="https://login.example.com", cross_origin=False))
    assert s.list_credentials("alice") == ["cred-1"]


def test_uv_not_required_when_configured_but_up_still_is():
    s, _, _ = make_server(require_user_verification=False)
    ch = s.begin_registration("alice")["challenge"]
    s.finish_registration(Authenticator().register(ch, flags=UP))
    ch = s.begin_registration("alice")["challenge"]
    assert code_of(s.finish_registration, Authenticator("c2", b"k2").register(ch, flags=0)) == "user_not_present"


def test_authenticator_data_longer_than_37_bytes_is_ok():
    s, _, _ = make_server()
    ch = s.begin_registration("alice")["challenge"]
    resp = Authenticator().register(ch)
    resp["authenticator_data"] += b"\xa1extension-bytes"
    s.finish_registration(resp)
    assert s.list_credentials("alice") == ["cred-1"]


def test_duplicate_credential_id_is_rejected_for_anyone():
    s, _, _ = make_server()
    registered(s, "alice")
    ch = s.begin_registration("bob")["challenge"]
    assert code_of(s.finish_registration, Authenticator(secret=b"other").register(ch)) == "duplicate_credential"
    ch = s.begin_registration("alice")["challenge"]
    assert code_of(s.finish_registration, Authenticator().register(ch)) == "duplicate_credential"
    assert s.list_credentials("bob") == []


def test_registration_malformed_inputs():
    s, _, _ = make_server()
    ch = s.begin_registration("alice")["challenge"]
    good = Authenticator().register(ch)

    def with_(**kw):
        return {**good, **kw}

    bad = [
        with_(client_data_json=b"not json"),
        with_(client_data_json=b'["a"]'),
        with_(client_data_json=b'{"type": "webauthn.create", "challenge": 5, "origin": "' + ORIGIN.encode() + b'"}'),
        with_(client_data_json=b'{"type": "webauthn.create", "origin": "' + ORIGIN.encode() + b'"}'),
        with_(authenticator_data=good["authenticator_data"][:36]),
        with_(authenticator_data="text"),
        with_(credential_id=""), with_(credential_id=None), with_(credential_id=5),
        with_(public_key=b""), with_(public_key="str"), with_(public_key=None),
        {k: v for k, v in good.items() if k != "client_data_json"},
        {k: v for k, v in good.items() if k != "authenticator_data"},
        {k: v for k, v in good.items() if k != "public_key"},
    ]
    for resp in bad:
        assert code_of(s.finish_registration, resp) == "malformed", resp
    # malformed не витрачає challenge
    s.finish_registration(good)
    assert s.list_credentials("alice") == ["cred-1"]


# --- challenge ---------------------------------------------------------------------------------

def test_unknown_challenge():
    s, _, _ = make_server()
    assert code_of(s.finish_registration, Authenticator().register("never-issued")) == "unknown_challenge"
    assert code_of(s.finish_authentication, Authenticator().assertion("never-issued")) == "unknown_challenge"


def test_challenge_is_single_use_on_success_and_on_failure():
    s, _, _ = make_server()
    ch = s.begin_registration("alice")["challenge"]
    resp = Authenticator().register(ch)
    s.finish_registration(resp)
    assert code_of(s.finish_registration, resp) == "unknown_challenge"

    ch = s.begin_registration("bob")["challenge"]
    a = Authenticator("c2", b"k2")
    assert code_of(s.finish_registration, a.register(ch, origin="https://evil.example.net")) == "bad_origin"
    assert code_of(s.finish_registration, a.register(ch)) == "unknown_challenge"


def test_challenge_expiry_boundary():
    s, clock, _ = make_server(challenge_ttl=300)
    ch1 = s.begin_registration("alice")["challenge"]
    ch2 = s.begin_registration("alice")["challenge"]
    clock.t = NOW + 299
    s.finish_registration(Authenticator().register(ch1))
    clock.t = NOW + 300
    assert code_of(s.finish_registration, Authenticator("c2", b"k2").register(ch2)) == "challenge_expired"
    assert s.list_credentials("alice") == ["cred-1"]


def test_challenge_purpose_is_enforced():
    s, _, _ = make_server()
    auth = registered(s)
    reg_ch = s.begin_registration("alice")["challenge"]
    assert code_of(s.finish_authentication, auth.assertion(reg_ch)) == "unknown_challenge"
    auth_ch = s.begin_authentication("alice")["challenge"]
    assert code_of(s.finish_registration, Authenticator("c2", b"k2").register(auth_ch)) == "unknown_challenge"


# --- автентифікація ----------------------------------------------------------------------------

def test_authentication_happy_path_and_verify_arguments():
    s, _, verifier = make_server()
    auth = registered(s, "alice", Authenticator(counter=0))
    ch = s.begin_authentication("alice")["challenge"]
    auth.counter = 7
    resp = auth.assertion(ch, user_handle="alice")
    res = s.finish_authentication(resp)
    assert res == {"user_id": "alice", "credential_id": "cred-1", "user_verified": True, "backed_up": False}
    assert verifier.calls[-1] == (b"authn-secret-1",
                                  resp["authenticator_data"] + hashlib.sha256(resp["client_data_json"]).digest(),
                                  resp["signature"])


def test_usernameless_flow_identifies_user_by_credential():
    s, _, _ = make_server()
    auth = registered(s, "alice")
    ch = s.begin_authentication()["challenge"]
    assert s.finish_authentication(auth.assertion(ch))["user_id"] == "alice"


@pytest.mark.parametrize("override, expected", [
    ({"typ": "webauthn.create"}, "bad_type"),
    ({"origin": "https://evil.example.net"}, "bad_origin"),
    ({"origin": "https://example.com/"}, "bad_origin"),
    ({"cross_origin": True}, "bad_origin"),
    ({"rp": "evil.com"}, "bad_rp_id"),
    ({"flags": UV}, "user_not_present"),
    ({"flags": UP}, "user_not_verified"),
    ({"flags": UP | UV | BS}, "bad_flags"),
])
def test_authentication_checks(override, expected):
    s, _, _ = make_server()
    auth = registered(s)
    ch = s.begin_authentication("alice")["challenge"]
    assert code_of(s.finish_authentication, auth.assertion(ch, **override)) == expected


def test_authentication_malformed():
    s, _, _ = make_server()
    auth = registered(s)
    ch = s.begin_authentication("alice")["challenge"]
    resp = auth.assertion(ch)
    assert code_of(s.finish_authentication, {**resp, "client_data_json": b"{"}) == "malformed"
    assert code_of(s.finish_authentication, {**resp, "authenticator_data": b"short"}) == "malformed"
    assert code_of(s.finish_authentication, {}) == "malformed"
    s.finish_authentication(resp)  # challenge не витрачено


def test_authentication_challenge_replay_expiry():
    s, clock, _ = make_server(challenge_ttl=60)
    auth = registered(s)
    ch = s.begin_authentication("alice")["challenge"]
    auth.counter = 1
    resp = auth.assertion(ch)
    s.finish_authentication(resp)
    assert code_of(s.finish_authentication, resp) == "unknown_challenge"
    ch = s.begin_authentication("alice")["challenge"]
    clock.t = NOW + 60
    auth.counter = 2
    assert code_of(s.finish_authentication, auth.assertion(ch)) == "challenge_expired"


def test_unknown_credential():
    s, _, _ = make_server()
    registered(s)
    ch = s.begin_authentication()["challenge"]
    ghost = Authenticator("ghost", b"g")
    assert code_of(s.finish_authentication, ghost.assertion(ch)) == "unknown_credential"


def test_wrong_user_binding():
    s, _, _ = make_server()
    registered(s, "alice")
    mallory = registered(s, "mallory", Authenticator("m-cred", b"mk"))
    ch = s.begin_authentication("alice")["challenge"]
    assert code_of(s.finish_authentication, mallory.assertion(ch)) == "wrong_user"
    ch = s.begin_authentication()["challenge"]
    assert code_of(s.finish_authentication, mallory.assertion(ch, user_handle="alice")) == "wrong_user"
    ch = s.begin_authentication()["challenge"]
    mallory.counter = 1
    assert s.finish_authentication(mallory.assertion(ch, user_handle="mallory"))["user_id"] == "mallory"


def test_bad_signature_variants_and_verify_failures():
    s, _, verifier = make_server()
    auth = registered(s)
    ch = s.begin_authentication("alice")["challenge"]
    resp = auth.assertion(ch)
    tampered = {**resp, "authenticator_data": resp["authenticator_data"][:33] + (99).to_bytes(4, "big")}
    assert code_of(s.finish_authentication, tampered) == "bad_signature"
    for override in (False, 0, 1, "yes", RuntimeError("boom")):
        verifier.override = override
        ch = s.begin_authentication("alice")["challenge"]
        assert code_of(s.finish_authentication, auth.assertion(ch)) == "bad_signature"
    verifier.override = None
    ch = s.begin_authentication("alice")["challenge"]
    assert code_of(s.finish_authentication, {**auth.assertion(ch), "signature": b"\x00" * 32}) == "bad_signature"
    ch = s.begin_authentication("alice")["challenge"]
    assert code_of(s.finish_authentication, {**auth.assertion(ch), "signature": None}) == "bad_signature"


def test_signature_checked_before_counter_so_forgery_does_not_flag_key():
    s, _, _ = make_server()
    auth = registered(s, counter=5)
    ch = s.begin_authentication("alice")["challenge"]
    forged = {**auth.assertion(ch, counter=2), "signature": b"\x01" * 32}
    assert code_of(s.finish_authentication, forged) == "bad_signature"


# --- лічильник і клонування -------------------------------------------------------------------

def test_counter_rules():
    s, _, _ = make_server()
    auth = registered(s, counter=0)

    def login(counter):
        ch = s.begin_authentication("alice")["challenge"]
        return s.finish_authentication(auth.assertion(ch, counter=counter))

    login(0)  # 0 -> 0: автентифікатор не лічить
    login(0)
    login(5)
    login(6)
    assert code_of(login, 6) == "cloned_credential"
    assert code_of(login, 3) == "cloned_credential"
    assert code_of(login, 0) == "cloned_credential"
    login(7)  # невдалі спроби не змінили збережений лічильник


def test_counter_from_registration_is_the_baseline():
    s, _, _ = make_server()
    auth = registered(s, counter=10)
    ch = s.begin_authentication("alice")["challenge"]
    assert code_of(s.finish_authentication, auth.assertion(ch, counter=10)) == "cloned_credential"
    ch = s.begin_authentication("alice")["challenge"]
    assert code_of(s.finish_authentication, auth.assertion(ch, counter=0)) == "cloned_credential"
    ch = s.begin_authentication("alice")["challenge"]
    assert s.finish_authentication(auth.assertion(ch, counter=11))["user_id"] == "alice"


def test_synced_passkey_backup_flags():
    s, _, _ = make_server()
    auth = registered(s, flags=UP | UV | BE, counter=0)
    ch = s.begin_authentication("alice")["challenge"]
    res = s.finish_authentication(auth.assertion(ch, flags=UP | UV | BE | BS, counter=0))
    assert res["backed_up"] is True
    ch = s.begin_authentication("alice")["challenge"]
    assert s.finish_authentication(auth.assertion(ch, flags=UP | UV | BE, counter=0))["backed_up"] is False


def test_backup_eligibility_cannot_change():
    s, _, _ = make_server()
    auth = registered(s, flags=UP | UV | BE)
    ch = s.begin_authentication("alice")["challenge"]
    assert code_of(s.finish_authentication, auth.assertion(ch, flags=UP | UV)) == "backup_eligibility_changed"
    device_bound = registered(s, "bob", Authenticator("d-cred", b"dk"), flags=UP | UV)
    ch = s.begin_authentication("bob")["challenge"]
    assert code_of(s.finish_authentication, device_bound.assertion(ch, flags=UP | UV | BE)) == "backup_eligibility_changed"


def test_failed_authentication_does_not_change_state():
    s, _, verifier = make_server()
    auth = registered(s, counter=3)
    verifier.override = False
    ch = s.begin_authentication("alice")["challenge"]
    code_of(s.finish_authentication, auth.assertion(ch, counter=9))
    verifier.override = None
    ch = s.begin_authentication("alice")["challenge"]
    assert s.finish_authentication(auth.assertion(ch, counter=4))["user_id"] == "alice"


# --- відновлення без SMS -----------------------------------------------------------------------

def test_recovery_codes_are_single_use_and_normalized():
    s, _, _ = make_server()
    codes = s.create_recovery_codes("alice", count=3)
    assert codes == ["ab12-cd34-0001", "ab12-cd34-0002", "ab12-cd34-0003"]
    assert s.use_recovery_code("alice", codes[0]) is True
    assert s.use_recovery_code("alice", codes[0]) is False
    assert s.use_recovery_code("alice", "  AB12 CD34 0002 ") is True
    assert s.use_recovery_code("alice", "ab12cd340003") is True
    assert s.use_recovery_code("alice", "ab12cd340003") is False


@pytest.mark.parametrize("junk", ["", "ab12-cd34-9999", None, 123, b"ab12-cd34-0001", ["ab12-cd34-0001"]])
def test_recovery_garbage_is_false(junk):
    s, _, _ = make_server()
    s.create_recovery_codes("alice", count=2)
    assert s.use_recovery_code("alice", junk) is False


def test_recovery_codes_are_per_user_and_regeneration_revokes_old_ones():
    s, _, _ = make_server()
    old = s.create_recovery_codes("alice", count=2)
    assert s.use_recovery_code("bob", old[0]) is False
    assert s.use_recovery_code("alice", old[0]) is True
    new = s.create_recovery_codes("alice", count=2)
    assert new != old
    assert s.use_recovery_code("alice", old[1]) is False
    assert s.use_recovery_code("alice", new[1]) is True


def test_recovery_codes_are_not_stored_in_plaintext():
    s, _, _ = make_server()
    codes = s.create_recovery_codes("alice", count=3)
    dump = repr(vars(s)).lower()
    for c in codes:
        assert c.lower() not in dump
        assert c.lower().replace("-", "") not in dump


def test_recovery_compare_uses_constant_time_function(monkeypatch):
    import importlib

    calls = []
    real = hmac.compare_digest

    def spy(a, b):
        calls.append(1)
        return real(a, b)

    monkeypatch.setattr(hmac, "compare_digest", spy)
    mod = importlib.reload(solution)
    try:
        s = mod.WebAuthnServer(RP, [ORIGIN], clock=Clock(), verify=Verifier(),
                               new_recovery_code=iter(["c0de-0001", "c0de-0002"]).__next__)
        codes = s.create_recovery_codes("alice", count=2)
        assert s.use_recovery_code("alice", codes[0]) is True
        assert calls
    finally:
        monkeypatch.undo()
        importlib.reload(solution)


def test_remove_credential_rules():
    s, _, _ = make_server()
    registered(s, "alice")
    registered(s, "bob", Authenticator("b-cred", b"bk"))
    assert code_of(s.remove_credential, "alice", "b-cred") == "unknown_credential"
    assert code_of(s.remove_credential, "alice", "ghost") == "unknown_credential"
    assert code_of(s.remove_credential, "alice", "cred-1") == "last_credential"
    assert s.list_credentials("alice") == ["cred-1"]
    s.create_recovery_codes("alice", count=1)
    s.remove_credential("alice", "cred-1")
    assert s.list_credentials("alice") == []


def test_remove_with_two_credentials_is_allowed_and_used_codes_do_not_count():
    s, _, _ = make_server()
    registered(s, "alice")
    registered(s, "alice", Authenticator("c2", b"k2"))
    s.remove_credential("alice", "cred-1")
    codes = s.create_recovery_codes("alice", count=1)
    assert s.use_recovery_code("alice", codes[0]) is True
    assert code_of(s.remove_credential, "alice", "c2") == "last_credential"
