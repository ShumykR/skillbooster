import base64
import hashlib
import hmac
import importlib
import random
import secrets

import pytest

import solution as sol

KEY = bytes(range(32))
OTHER_KEY = bytes(range(1, 33))


@pytest.fixture
def spies(monkeypatch):
    """Підміняє compare_digest і KDF шпигунами й перезавантажує solution (працює для обох стилів імпорту)."""
    calls = {"compare": 0, "scrypt": [], "pbkdf2": []}
    real_cmp, real_scrypt, real_pbkdf2 = hmac.compare_digest, hashlib.scrypt, hashlib.pbkdf2_hmac

    def cmp(a, b):
        calls["compare"] += 1
        return real_cmp(a, b)

    def scrypt(password, *args, **kw):
        calls["scrypt"].append(kw)
        return real_scrypt(password, *args, **kw)

    def pbkdf2(hash_name, password, salt, iterations, *args, **kw):
        calls["pbkdf2"].append((hash_name, iterations))
        return real_pbkdf2(hash_name, password, salt, iterations, *args, **kw)

    monkeypatch.setattr(hmac, "compare_digest", cmp)
    monkeypatch.setattr(secrets, "compare_digest", cmp)
    monkeypatch.setattr(hashlib, "scrypt", scrypt)
    monkeypatch.setattr(hashlib, "pbkdf2_hmac", pbkdf2)
    importlib.reload(sol)
    yield calls
    monkeypatch.undo()
    importlib.reload(sol)


# --- sign / verify -----------------------------------------------------------------------------

def test_sign_is_hmac_sha256_hex():
    expected = hmac.new(KEY, b"hello", hashlib.sha256).hexdigest()
    assert sol.sign(KEY, b"hello") == expected
    assert sol.sign(KEY, b"") == hmac.new(KEY, b"", hashlib.sha256).hexdigest()


def test_verify_accepts_valid_tag_str_and_bytes():
    tag = sol.sign(KEY, b"msg")
    assert sol.verify(KEY, b"msg", tag) is True
    assert sol.verify(KEY, b"msg", tag.encode()) is True


def test_verify_rejects_wrong_data_key_tag():
    tag = sol.sign(KEY, b"msg")
    assert sol.verify(KEY, b"msg2", tag) is False
    assert sol.verify(OTHER_KEY, b"msg", tag) is False
    assert sol.verify(KEY, b"msg", "0" * 64) is False
    assert sol.verify(KEY, b"msg", tag[:-1]) is False
    assert sol.verify(KEY, b"msg", tag.upper()) is False


@pytest.mark.parametrize("bad", ["", b"", None, 123, "тег", "é" * 64, ["a"], b"\xff" * 64])
def test_verify_never_raises_on_garbage_tag(bad):
    assert sol.verify(KEY, b"msg", bad) is False


def test_verify_uses_constant_time_compare(spies):
    tag = sol.sign(KEY, b"msg")
    spies["compare"] = 0
    assert sol.verify(KEY, b"msg", tag)
    assert spies["compare"] >= 1
    spies["compare"] = 0
    assert not sol.verify(KEY, b"msg", "0" * 64)
    assert spies["compare"] >= 1


# --- new_token ---------------------------------------------------------------------------------

def test_token_does_not_depend_on_random_module_state():
    random.seed(1234)
    a = sol.new_token()
    random.seed(1234)
    b = sol.new_token()
    assert a != b


def test_token_shape_and_uniqueness():
    tokens = {sol.new_token() for _ in range(500)}
    assert len(tokens) == 500
    t = sol.new_token(32)
    assert isinstance(t, str)
    assert set(t) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
    raw = base64.urlsafe_b64decode(t + "=" * (-len(t) % 4))
    assert len(raw) >= 32


def test_token_entropy_in_alphabet():
    # 64 символи алфавіту: з ~6400 символів має трапитись понад 40 різних
    chars = "".join(sol.new_token(48) for _ in range(100))
    assert len(set(chars)) > 40


@pytest.mark.parametrize("n", [0, 1, 15, -5])
def test_token_too_short_rejected(n):
    with pytest.raises(ValueError):
        sol.new_token(n)


# --- passwords ---------------------------------------------------------------------------------

def test_password_roundtrip_and_wrong():
    s = sol.hash_password("correct horse")
    assert isinstance(s, str)
    assert sol.verify_password("correct horse", s) is True
    assert sol.verify_password("correct horsf", s) is False
    assert sol.verify_password("", s) is False


def test_password_unicode_and_long():
    for pw in ["пароль-🔑", "p" * 1000, "  spaced  ", ""]:
        s = sol.hash_password(pw)
        assert sol.verify_password(pw, s) is True
    assert sol.verify_password("p" * 999, sol.hash_password("p" * 1000)) is False


def test_password_hash_is_salted():
    assert sol.hash_password("same") != sol.hash_password("same")


def test_password_hash_does_not_contain_fast_digests():
    pw = "hunter2"
    s = sol.hash_password(pw)
    for algo in ("md5", "sha1", "sha256", "sha512"):
        assert hashlib.new(algo, pw.encode()).hexdigest() not in s
    assert pw not in s


@pytest.mark.parametrize("junk", ["", "x", "$", "$$$", "a$b$c", hashlib.md5(b"hunter2").hexdigest(),
                                  "scrypt$$$", "\x00" * 10, "é" * 50])
def test_verify_password_garbage_stored_is_false(junk):
    assert sol.verify_password("hunter2", junk) is False


def test_password_uses_slow_kdf_with_sane_cost(spies):
    s = sol.hash_password("pw")
    assert sol.verify_password("pw", s)
    assert spies["scrypt"] or spies["pbkdf2"], "очікується hashlib.scrypt або hashlib.pbkdf2_hmac"
    for kw in spies["scrypt"]:
        assert kw.get("n", 0) >= 2 ** 14
    for name, iterations in spies["pbkdf2"]:
        assert name in ("sha256", "sha512")
        assert iterations >= 100_000


# --- encrypt_blob / decrypt_blob ---------------------------------------------------------------

@pytest.mark.parametrize("n", [0, 1, 15, 16, 17, 31, 32, 1000])
def test_blob_roundtrip(n):
    data = bytes(i % 251 for i in range(n))
    assert sol.decrypt_blob(KEY, sol.encrypt_blob(KEY, data)) == data


def test_blob_same_plaintext_gives_different_blobs():
    assert sol.encrypt_blob(KEY, b"secret") != sol.encrypt_blob(KEY, b"secret")


def test_blob_has_no_repeating_blocks_for_repeating_plaintext():
    blob = sol.encrypt_blob(KEY, b"A" * 160)
    blocks = [blob[i:i + 16] for i in range(0, len(blob) - 15, 16)]
    assert len(blocks) == len(set(blocks))


def test_blob_tamper_at_every_position_is_detected():
    blob = sol.encrypt_blob(KEY, b"transfer 100 to alice, ref 0042!")
    for i in range(len(blob)):
        bad = bytearray(blob)
        bad[i] ^= 0x01
        with pytest.raises(ValueError):
            sol.decrypt_blob(KEY, bytes(bad))


@pytest.mark.parametrize("cut", [0, 1, 5, 16, 28])
def test_blob_truncated_or_empty(cut):
    blob = sol.encrypt_blob(KEY, b"some data to protect")
    with pytest.raises(ValueError):
        sol.decrypt_blob(KEY, blob[:cut])
    with pytest.raises(ValueError):
        sol.decrypt_blob(KEY, blob + b"\x00")


def test_blob_wrong_key():
    blob = sol.encrypt_blob(KEY, b"some data to protect")
    with pytest.raises(ValueError):
        sol.decrypt_blob(OTHER_KEY, blob)


@pytest.mark.parametrize("bad", [b"", b"short", bytes(16), bytes(31), bytes(33), "x" * 32, None])
def test_blob_key_length_validated(bad):
    with pytest.raises(ValueError):
        sol.encrypt_blob(bad, b"x")
    with pytest.raises(ValueError):
        sol.decrypt_blob(bad, b"x" * 64)


# --- seal / open_sealed ------------------------------------------------------------------------

def test_seal_format_and_roundtrip():
    blob = sol.seal(KEY, b"hello world")
    assert len(blob) == 12 + len(b"hello world") + 16
    assert sol.open_sealed(KEY, blob) == b"hello world"
    assert sol.open_sealed(KEY, sol.seal(KEY, b"")) == b""


def test_seal_matches_aesgcm_layout():
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    blob = sol.seal(KEY, b"layout check", b"hdr")
    assert AESGCM(KEY).decrypt(blob[:12], blob[12:], b"hdr") == b"layout check"


def test_seal_nonce_never_repeats():
    nonces = [sol.seal(KEY, b"x")[:12] for _ in range(2000)]
    assert len(set(nonces)) == 2000
    assert b"\x00" * 12 not in nonces


def test_seal_same_plaintext_gives_different_blobs_no_xor_leak():
    a, b = sol.seal(KEY, b"A" * 32), sol.seal(KEY, b"B" * 32)
    assert a[12:44] != b[12:44]
    xor_ct = bytes(x ^ y for x, y in zip(a[12:44], b[12:44]))
    assert xor_ct != bytes(x ^ y for x, y in zip(b"A" * 32, b"B" * 32))


def test_seal_aad_binding():
    blob = sol.seal(KEY, b"data", b"user:1")
    assert sol.open_sealed(KEY, blob, b"user:1") == b"data"
    with pytest.raises(ValueError):
        sol.open_sealed(KEY, blob, b"user:2")
    with pytest.raises(ValueError):
        sol.open_sealed(KEY, blob)


def test_seal_tamper_wrong_key_short():
    blob = sol.seal(KEY, b"data to protect")
    for i in range(len(blob)):
        bad = bytearray(blob)
        bad[i] ^= 0x80
        with pytest.raises(ValueError):
            sol.open_sealed(KEY, bytes(bad))
    with pytest.raises(ValueError):
        sol.open_sealed(OTHER_KEY, blob)
    for cut in (0, 5, 12, 27):
        with pytest.raises(ValueError):
            sol.open_sealed(KEY, blob[:cut])


@pytest.mark.parametrize("bad", [b"", bytes(16), bytes(31), bytes(33), None])
def test_seal_key_length_validated(bad):
    with pytest.raises(ValueError):
        sol.seal(bad, b"x")
    with pytest.raises(ValueError):
        sol.open_sealed(bad, b"x" * 40)
