import base64
import hashlib
import time

import pytest

from solution import DEFAULT, Params, check_password_policy, hash_password, needs_rehash, new_token, verify_password

FAST = Params(16, 8, 1)  # у тестах слабкі параметри, щоб було швидко; у production використовуй DEFAULT і вище
STRONGER = Params(32, 8, 1)
SALT = bytes(range(16))


# --- hash_password ----------------------------------------------------------------------------

def test_format_and_known_vector():
    stored = hash_password("correct horse", FAST, SALT)
    scheme, n, r, p, salt_b64, hash_b64 = stored.split("$")
    assert (scheme, n, r, p) == ("scrypt", "16", "8", "1")
    assert "=" not in salt_b64 + hash_b64
    expected = hashlib.scrypt(b"correct horse", salt=SALT, n=16, r=8, p=1, dklen=32)
    assert base64.b64decode(hash_b64 + "=" * (-len(hash_b64) % 4)) == expected
    assert base64.b64decode(salt_b64 + "=" * (-len(salt_b64) % 4)) == SALT


def test_salt_is_random_by_default():
    a, b = hash_password("same password", FAST), hash_password("same password", FAST)
    assert a != b
    assert verify_password("same password", a) and verify_password("same password", b)


def test_same_salt_gives_same_record():
    assert hash_password("x" * 12, FAST, SALT) == hash_password("x" * 12, FAST, SALT)


def test_plaintext_does_not_appear_in_record():
    assert "hunter2hunter2" not in hash_password("hunter2hunter2", FAST)


def test_default_params_are_sane():
    assert DEFAULT == Params(2**14, 8, 1)
    assert hash_password("pw-default", salt=SALT).startswith("scrypt$16384$8$1$")


@pytest.mark.parametrize("bad", ["", "a" * 129])
def test_length_limits(bad):
    with pytest.raises(ValueError):
        hash_password(bad, FAST)


def test_max_length_is_accepted():
    assert verify_password("a" * 128, hash_password("a" * 128, FAST))


@pytest.mark.parametrize("bad", [None, 123, b"bytes"])
def test_password_must_be_str(bad):
    with pytest.raises(TypeError):
        hash_password(bad, FAST)


@pytest.mark.parametrize("params", [Params(15, 8, 1), Params(2**17, 8, 1), Params(8, 8, 1), Params(16, 0, 1),
                                    Params(16, 8, 0), Params(16, 8, 5), Params(16, 17, 1), Params(16.0, 8, 1)])
def test_params_are_validated(params):
    with pytest.raises(ValueError):
        hash_password("long enough pw", params)


@pytest.mark.parametrize("salt", [b"", b"short", bytes(17), "0123456789abcdef"])
def test_salt_must_be_16_bytes(salt):
    with pytest.raises(ValueError):
        hash_password("long enough pw", FAST, salt)


# --- verify_password -------------------------------------------------------------------------------

def test_correct_and_wrong_password():
    stored = hash_password("s3cret-passphrase", FAST)
    assert verify_password("s3cret-passphrase", stored) is True
    assert verify_password("s3cret-passphrasE", stored) is False
    assert verify_password("", stored) is False


def test_unicode_normalisation_nfkc():
    stored = hash_password("ｐａｓｓ１２３４５６", FAST)  # повношириннi символи
    assert verify_password("pass123456", stored)
    stored2 = hash_password("é-café-passphrase", FAST)  # «é» одним символом
    assert verify_password("é-café-passphrase", stored2)  # «e» + комбінований наголос


def test_params_are_taken_from_the_record():
    weak = hash_password("moving target", FAST, SALT)
    strong = hash_password("moving target", STRONGER, SALT)
    assert weak != strong
    assert verify_password("moving target", weak) and verify_password("moving target", strong)


@pytest.mark.parametrize(
    "stored",
    [None, 5, b"scrypt$16$8$1$AAAA$BBBB", "", "scrypt", "$", "bcrypt$16$8$1$" + "A" * 22 + "$" + "B" * 43,
     "plaintext-password", "scrypt$16$8$1$onlyfive", "scrypt$16$8$1$a$b$c$d"],
)
def test_garbage_records_are_false_not_exceptions(stored):
    assert verify_password("anything-here", stored) is False


def test_tampered_records_are_false():
    stored = hash_password("tamper test pw", FAST, SALT)
    parts = stored.split("$")
    for i in range(1, 6):
        broken = parts.copy()
        broken[i] = ("A" if broken[i][0] != "A" else "B") + broken[i][1:] if i >= 4 else str(int(broken[i]) + 1)
        assert verify_password("tamper test pw", "$".join(broken)) is False


@pytest.mark.parametrize("n, r, p", [(2**30, 8, 1), (2**17, 8, 1), (15, 8, 1), (0, 8, 1), (16, 8, 100), (16, 1000, 1),
                                     (16, 0, 1), (-16, 8, 1)])
def test_dangerous_params_in_record_are_rejected_without_computation(n, r, p):
    salt = base64.b64encode(SALT).decode().rstrip("=")
    h = base64.b64encode(bytes(32)).decode().rstrip("=")
    started = time.perf_counter()
    assert verify_password("whatever-pass", f"scrypt${n}${r}${p}${salt}${h}") is False
    assert time.perf_counter() - started < 1.0  # якби scrypt справді рахувався з n=2**30, це були б хвилини й гігабайти


def test_non_str_and_oversized_password_is_false():
    stored = hash_password("some pass phrase", FAST)
    assert verify_password(None, stored) is False
    assert verify_password(b"some pass phrase", stored) is False
    assert verify_password("x" * 10_000, stored) is False


def test_verify_uses_constant_time_compare(monkeypatch):
    import hmac
    calls = []
    real = hmac.compare_digest

    def spy(a, b):
        calls.append(1)
        return real(a, b)

    monkeypatch.setattr(hmac, "compare_digest", spy)
    stored = hash_password("compare me please", FAST)
    verify_password("compare me please", stored)
    assert calls, "використай hmac.compare_digest"


# --- needs_rehash ------------------------------------------------------------------------------------

def test_needs_rehash_when_record_is_weaker():
    weak = hash_password("rehash me please", FAST)
    assert needs_rehash(weak, STRONGER) is True
    assert needs_rehash(weak, Params(16, 16, 1)) is True
    assert needs_rehash(weak, Params(16, 8, 2)) is True


def test_no_rehash_when_equal_or_stronger():
    strong = hash_password("rehash me please", STRONGER)
    assert needs_rehash(strong, STRONGER) is False
    assert needs_rehash(strong, FAST) is False
    assert needs_rehash(hash_password("x" * 12, Params(32, 16, 2)), STRONGER) is False


@pytest.mark.parametrize("stored", ["", "garbage", None, "bcrypt$12$abc", "scrypt$16$8$1$a$b"])
def test_unknown_or_broken_records_need_rehash(stored):
    assert needs_rehash(stored, FAST) is True


# --- політика -----------------------------------------------------------------------------------------

def test_good_passwords_pass():
    assert check_password_policy("correct horse battery staple") == []
    assert check_password_policy("a simple but long sentence 🙂") == []
    assert check_password_policy("only-lowercase-letters") == []  # складових вимог немає


def test_too_short_and_too_long():
    assert check_password_policy("Ab1!xyz") == ["too_short"]
    assert check_password_policy("x9Kq2mP4tz") == []  # рівно 10
    assert "too_long" in check_password_policy("aB3" * 50)


@pytest.mark.parametrize("pw", ["password123", "Password123", "QWERTYUIOP", "1234567890", "Administrator"])
def test_common_passwords(pw):
    assert "common" in check_password_policy(pw)


def test_contains_user_input():
    assert check_password_policy("ann-smith-2024-xyz", ["Ann Smith", "ann", "smith"]) == ["contains_user_input"]
    assert check_password_policy("xxROMANxxlongpass", ["roman"]) == ["contains_user_input"]
    assert check_password_policy("unrelated-long-pass", ["al", ""]) == []  # коротші за 3 символи ігноруються


@pytest.mark.parametrize("pw", ["a" * 12, "abababababab", "123123123123", "xyz" * 5])
def test_repetitive(pw):
    assert "repetitive" in check_password_policy(pw)


def test_not_repetitive():
    assert "repetitive" not in check_password_policy("abababababac")
    assert "repetitive" not in check_password_policy("aaaaaaaaaab")


def test_codes_are_in_documented_order():
    assert check_password_policy("password", ["pass"]) == ["too_short", "common", "contains_user_input"]
    assert check_password_policy("aaaa", ["aaa"]) == ["too_short", "contains_user_input", "repetitive"]


# --- токени ---------------------------------------------------------------------------------------------

def test_tokens_are_unique_urlsafe_and_long_enough():
    tokens = {new_token() for _ in range(200)}
    assert len(tokens) == 200
    for t in list(tokens)[:20]:
        assert len(t) >= 43 and set(t) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")


def test_token_length_follows_nbytes():
    assert len(new_token(16)) == 22
    assert len(new_token(64)) == 86


@pytest.mark.parametrize("bad", [0, 15, -1, 16.0, "32", None, True])
def test_token_nbytes_validation(bad):
    with pytest.raises(ValueError):
        new_token(bad)


def test_tokens_come_from_secrets(monkeypatch):
    import secrets
    monkeypatch.setattr(secrets, "token_urlsafe", lambda n=None: f"fixed-{n}")
    assert new_token(24) == "fixed-24"
