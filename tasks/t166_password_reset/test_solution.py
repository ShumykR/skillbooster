import hashlib

import pytest

from solution import GENERIC_MESSAGE, ResetService

STRONG = "correct horse battery"


class Env:
    def __init__(self, ttl=900, min_length=12):
        self.now = 1000.0
        self.sent = []
        self.changed = []
        self.counter = 0
        self.svc = ResetService(
            {"a@x.io": 1, "b@x.io": 2},
            send=lambda email, token: self.sent.append((email, token)),
            set_password=lambda uid, pw: self.changed.append((uid, pw)),
            clock=lambda: self.now,
            new_token=self._token,
            ttl=ttl,
            min_length=min_length,
        )

    def _token(self):
        self.counter += 1
        return f"tok-{self.counter}-" + "x" * 32

    def token_for(self, email):
        return [t for e, t in self.sent if e == email][-1]


@pytest.fixture
def env():
    return Env()


# ---------- request_reset ----------

def test_known_and_unknown_email_get_identical_response(env):
    a = env.svc.request_reset("a@x.io")
    b = env.svc.request_reset("nobody@x.io")
    assert a == b == GENERIC_MESSAGE


def test_unknown_email_sends_nothing(env):
    env.svc.request_reset("nobody@x.io")
    assert env.sent == []


def test_known_email_sends_exactly_one_mail(env):
    env.svc.request_reset("a@x.io")
    assert len(env.sent) == 1 and env.sent[0][0] == "a@x.io"


def test_email_is_normalized(env):
    env.svc.request_reset("  A@X.IO ")
    assert [e for e, _ in env.sent] == ["a@x.io"]


@pytest.mark.parametrize("bad", [None, 123, b"a@x.io", ["a@x.io"], ""])
def test_bad_input_is_generic_not_error(env, bad):
    assert env.svc.request_reset(bad) == GENERIC_MESSAGE
    assert env.sent == []


def test_default_token_source_is_unpredictable_and_long():
    sent = []
    svc = ResetService({"a@x.io": 1}, send=lambda e, t: sent.append(t), set_password=lambda *_: None,
                       clock=lambda: 0)
    svc.request_reset("a@x.io")
    svc.request_reset("a@x.io")
    assert len(sent) == 2 and sent[0] != sent[1]
    assert all(len(t) >= 32 for t in sent)


def test_raw_token_is_not_stored(env):
    env.svc.request_reset("a@x.io")
    token = env.token_for("a@x.io")
    assert token not in repr(vars(env.svc))
    assert hashlib.sha256(token.encode()).hexdigest() in repr(vars(env.svc))


# ---------- confirm_reset ----------

def test_valid_token_changes_password(env):
    env.svc.request_reset("a@x.io")
    assert env.svc.confirm_reset(env.token_for("a@x.io"), STRONG) is True
    assert env.changed == [(1, STRONG)]


def test_token_resets_only_its_owner(env):
    env.svc.request_reset("a@x.io")
    env.svc.request_reset("b@x.io")
    assert env.svc.confirm_reset(env.token_for("b@x.io"), STRONG)
    assert env.changed == [(2, STRONG)]


def test_token_is_single_use(env):
    env.svc.request_reset("a@x.io")
    t = env.token_for("a@x.io")
    assert env.svc.confirm_reset(t, STRONG) is True
    assert env.svc.confirm_reset(t, "another strong pass 1") is False
    assert len(env.changed) == 1


def test_expiry_boundary(env):
    env.svc.request_reset("a@x.io")
    t = env.token_for("a@x.io")
    env.now += 899.9
    assert env.svc.confirm_reset(t, STRONG) is True


def test_expired_exactly_at_ttl(env):
    env.svc.request_reset("a@x.io")
    t = env.token_for("a@x.io")
    env.now += 900
    assert env.svc.confirm_reset(t, STRONG) is False
    assert env.changed == []


def test_custom_ttl():
    e = Env(ttl=60)
    e.svc.request_reset("a@x.io")
    t = e.token_for("a@x.io")
    e.now += 61
    assert e.svc.confirm_reset(t, STRONG) is False


def test_expired_token_stays_dead_when_clock_goes_back(env):
    env.svc.request_reset("a@x.io")
    t = env.token_for("a@x.io")
    env.now += 1000
    assert env.svc.confirm_reset(t, STRONG) is False
    env.now -= 1000
    assert env.svc.confirm_reset(t, STRONG) is False


def test_new_request_invalidates_old_token(env):
    env.svc.request_reset("a@x.io")
    old = env.token_for("a@x.io")
    env.svc.request_reset("a@x.io")
    new = env.token_for("a@x.io")
    assert old != new
    assert env.svc.confirm_reset(old, STRONG) is False
    assert env.svc.confirm_reset(new, STRONG) is True


def test_new_request_for_other_user_keeps_first_token(env):
    env.svc.request_reset("a@x.io")
    env.svc.request_reset("b@x.io")
    assert env.svc.confirm_reset(env.token_for("a@x.io"), STRONG) is True


def test_new_request_restarts_ttl(env):
    env.svc.request_reset("a@x.io")
    env.now += 800
    env.svc.request_reset("a@x.io")
    t = env.token_for("a@x.io")
    env.now += 800
    assert env.svc.confirm_reset(t, STRONG) is True


@pytest.mark.parametrize("bad", ["", "garbage", "tok-1-", None, 123, b"tok", ["x"]])
def test_unknown_or_malformed_token_is_false(env, bad):
    env.svc.request_reset("a@x.io")
    assert env.svc.confirm_reset(bad, STRONG) is False
    assert env.changed == []


def test_token_is_case_sensitive(env):
    env.svc.request_reset("a@x.io")
    assert env.svc.confirm_reset(env.token_for("a@x.io").upper(), STRONG) is False


def test_weak_password_rejected_and_token_kept(env):
    env.svc.request_reset("a@x.io")
    t = env.token_for("a@x.io")
    with pytest.raises(ValueError, match="weak_password"):
        env.svc.confirm_reset(t, "short")
    assert env.changed == []
    assert env.svc.confirm_reset(t, STRONG) is True


def test_password_length_boundary(env):
    env.svc.request_reset("a@x.io")
    t = env.token_for("a@x.io")
    with pytest.raises(ValueError):
        env.svc.confirm_reset(t, "x" * 11)
    assert env.svc.confirm_reset(t, "x" * 12) is True


def test_custom_min_length():
    e = Env(min_length=20)
    e.svc.request_reset("a@x.io")
    with pytest.raises(ValueError):
        e.svc.confirm_reset(e.token_for("a@x.io"), "x" * 19)


def test_non_string_password_is_weak(env):
    env.svc.request_reset("a@x.io")
    with pytest.raises(ValueError):
        env.svc.confirm_reset(env.token_for("a@x.io"), None)


def test_invalid_token_does_not_leak_password_policy(env):
    # невідомий токен + слабкий пароль: не ValueError, інакше можна відрізнити дійсний токен
    env.svc.request_reset("a@x.io")
    assert env.svc.confirm_reset("nope", "short") is False


def test_expired_token_with_weak_password_is_false(env):
    env.svc.request_reset("a@x.io")
    t = env.token_for("a@x.io")
    env.now += 5000
    assert env.svc.confirm_reset(t, "short") is False


def test_success_does_not_resend_or_change_other_users(env):
    env.svc.request_reset("a@x.io")
    env.svc.confirm_reset(env.token_for("a@x.io"), STRONG)
    assert len(env.sent) == 1
    assert all(uid == 1 for uid, _ in env.changed)
