import copy
import json
import os
import random

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from solution import FieldEncryptor, ShreddedError


class MockKMS:
    """KEK живуть лише тут. wrap/unwrap це AES-GCM з context як AAD."""

    def __init__(self, *kek_ids):
        self._keys = {k: os.urandom(32) for k in kek_ids}
        self.wrap_calls = []
        self.unwrap_calls = []
        self.fail_wrap_on_call = None

    def create_key(self, kek_id):
        self._keys[kek_id] = os.urandom(32)

    def destroy_key(self, kek_id):
        del self._keys[kek_id]

    def wrap(self, kek_id, dek, context):
        self.wrap_calls.append((kek_id, context))
        if self.fail_wrap_on_call == len(self.wrap_calls):
            raise RuntimeError("KMS unavailable")
        nonce = os.urandom(12)
        return nonce + AESGCM(self._keys[kek_id]).encrypt(nonce, dek, context)

    def unwrap(self, kek_id, wrapped, context):
        self.unwrap_calls.append((kek_id, context))
        key = self._keys[kek_id]  # KeyError, якщо знищено
        try:
            return AESGCM(key).decrypt(wrapped[:12], wrapped[12:], context)
        except InvalidTag:
            raise ValueError("context mismatch or tampered")


def ctx(user):
    return f"user:{user}".encode()


def aad(table, field, record_id):
    return json.dumps([table, field, record_id], separators=(",", ":")).encode()


@pytest.fixture
def env():
    kms = MockKMS("kek-v1", "kek-v2")
    store = {}
    enc = FieldEncryptor(kms, store, "kek-v1")
    return kms, store, enc


def seeded_rng(seed):
    return random.Random(seed).randbytes


# --- шифрування і структура запису -------------------------------------------------------------

@pytest.mark.parametrize("data", [b"", b"a", b"alice@example.com", bytes(range(256)) * 10])
def test_roundtrip(env, data):
    _, _, enc = env
    rec = enc.encrypt("u1", "users", "email", "42", data)
    assert enc.decrypt("u1", "users", "email", "42", rec) == data


def test_record_shape_and_real_aes_gcm_with_documented_aad(env):
    kms, store, enc = env
    rec = enc.encrypt("u1", "users", "email", "42", b"alice@example.com")
    assert set(rec) == {"v", "dek_version", "nonce", "ciphertext"}
    assert rec["v"] == 1 and rec["dek_version"] == 1
    assert isinstance(rec["nonce"], bytes) and len(rec["nonce"]) == 12
    assert len(rec["ciphertext"]) == len(b"alice@example.com") + 16
    entry = store["u1"]
    assert set(entry) == {"version", "kek_id", "wrapped_dek"}
    assert entry["version"] == 1 and entry["kek_id"] == "kek-v1"
    dek = kms.unwrap(entry["kek_id"], entry["wrapped_dek"], ctx("u1"))
    assert len(dek) == 32
    assert AESGCM(dek).decrypt(rec["nonce"], rec["ciphertext"], aad("users", "email", "42")) == b"alice@example.com"


def test_dek_is_never_stored_in_clear_and_plaintext_not_in_record(env):
    kms, store, enc = env
    rec = enc.encrypt("u1", "users", "email", "42", b"alice@example.com")
    dek = kms.unwrap("kek-v1", store["u1"]["wrapped_dek"], ctx("u1"))
    blob = repr(store).encode() + repr(rec).encode()
    assert dek not in blob and dek.hex().encode() not in blob
    assert b"alice@example.com" not in blob


def test_one_dek_per_user_wrapped_once_with_user_context(env):
    kms, store, enc = env
    for i in range(5):
        enc.encrypt("u1", "users", f"f{i}", str(i), b"x")
    assert kms.wrap_calls == [("kek-v1", ctx("u1"))]
    enc.encrypt("u2", "users", "email", "1", b"y")
    assert kms.wrap_calls[1:] == [("kek-v1", ctx("u2"))]
    assert set(store) == {"u1", "u2"}


def test_dek_differs_between_users(env):
    kms, store, enc = env
    enc.encrypt("u1", "t", "f", "1", b"x")
    enc.encrypt("u2", "t", "f", "1", b"x")
    d1 = kms.unwrap("kek-v1", store["u1"]["wrapped_dek"], ctx("u1"))
    d2 = kms.unwrap("kek-v1", store["u2"]["wrapped_dek"], ctx("u2"))
    assert d1 != d2


def test_nonce_is_fresh_every_time(env):
    _, _, enc = env
    recs = [enc.encrypt("u1", "t", "f", "1", b"same") for _ in range(300)]
    assert len({r["nonce"] for r in recs}) == 300
    assert len({r["ciphertext"] for r in recs}) == 300


def test_all_randomness_comes_from_rng():
    def run():
        kms = MockKMS("kek-v1")
        store = {}
        enc = FieldEncryptor(kms, store, "kek-v1", rng=seeded_rng(7))
        r1 = enc.encrypt("u1", "t", "f", "1", b"hello")
        r2 = enc.encrypt("u1", "t", "f", "2", b"hello")
        return r1, r2
    a, b = run(), run()
    assert a[0]["nonce"] == b[0]["nonce"] and a[1]["nonce"] == b[1]["nonce"]
    assert a[0]["nonce"] != a[1]["nonce"]
    assert a[0]["ciphertext"] == b[0]["ciphertext"]


@pytest.mark.parametrize("args", [
    ("", "t", "f", "1", b"x"), ("u", "", "f", "1", b"x"), ("u", "t", "", "1", b"x"), ("u", "t", "f", "", b"x"),
    (None, "t", "f", "1", b"x"), ("u", "t", "f", 1, b"x"), ("u", "t", "f", "1", "text"), ("u", "t", "f", "1", None),
    ("u", "t", "f", "1", bytearray(b"x")),
])
def test_encrypt_validates_arguments(env, args):
    _, store, enc = env
    with pytest.raises(ValueError):
        enc.encrypt(*args)
    assert store == {}


# --- AAD: привʼязка до місця -------------------------------------------------------------------

def test_record_cannot_be_moved_to_another_record_field_or_table(env):
    _, _, enc = env
    rec = enc.encrypt("u1", "users", "email", "42", b"alice@example.com")
    for args in [("users", "email", "43"), ("users", "phone", "42"), ("orders", "email", "42")]:
        with pytest.raises(ValueError):
            enc.decrypt("u1", *args, rec)
    assert enc.decrypt("u1", "users", "email", "42", rec) == b"alice@example.com"


def test_swapping_two_records_of_same_user_fails(env):
    _, _, enc = env
    r1 = enc.encrypt("u1", "users", "email", "1", b"one@example.com")
    r2 = enc.encrypt("u1", "users", "email", "2", b"two@example.com")
    with pytest.raises(ValueError):
        enc.decrypt("u1", "users", "email", "1", r2)
    with pytest.raises(ValueError):
        enc.decrypt("u1", "users", "email", "2", r1)


def test_aad_has_no_separator_ambiguity(env):
    _, _, enc = env
    rec = enc.encrypt("u1", "a/b", "c", "1", b"x")
    with pytest.raises(ValueError):
        enc.decrypt("u1", "a", "b/c", "1", rec)
    rec2 = enc.encrypt("u1", "a", "bc", "d", b"x")
    with pytest.raises(ValueError):
        enc.decrypt("u1", "ab", "c", "d", rec2)


def test_other_users_record_cannot_be_read_as_mine(env):
    _, _, enc = env
    rec = enc.encrypt("u1", "users", "email", "1", b"secret")
    enc.encrypt("u2", "users", "email", "2", b"other")
    with pytest.raises(ValueError):
        enc.decrypt("u2", "users", "email", "1", rec)


def test_wrapped_dek_copied_between_users_does_not_open_data(env):
    kms, store, enc = env
    rec = enc.encrypt("u1", "users", "email", "1", b"secret")
    enc.encrypt("u2", "users", "email", "2", b"other")
    store["u2"] = copy.deepcopy(store["u1"])  # атака на keystore: DEK u1 під іменем u2
    with pytest.raises(ValueError):
        enc.decrypt("u2", "users", "email", "1", rec)


# --- цілісність --------------------------------------------------------------------------------

def test_tampering_with_nonce_or_ciphertext_is_detected(env):
    _, _, enc = env
    rec = enc.encrypt("u1", "users", "email", "1", b"alice@example.com")
    for key in ("nonce", "ciphertext"):
        for i in range(len(rec[key])):
            bad = dict(rec)
            raw = bytearray(rec[key])
            raw[i] ^= 0x01
            bad[key] = bytes(raw)
            with pytest.raises(ValueError):
                enc.decrypt("u1", "users", "email", "1", bad)


@pytest.mark.parametrize("mutate", [
    lambda r: None, lambda r: "text", lambda r: [], lambda r: {**r, "v": 2}, lambda r: {**r, "v": "1"},
    lambda r: {k: v for k, v in r.items() if k != "nonce"}, lambda r: {**r, "nonce": r["nonce"][:-1]},
    lambda r: {**r, "nonce": r["nonce"] + b"\x00"}, lambda r: {**r, "nonce": r["nonce"].hex()},
    lambda r: {**r, "ciphertext": r["ciphertext"][:15]}, lambda r: {**r, "ciphertext": b""},
    lambda r: {**r, "ciphertext": None}, lambda r: {**r, "dek_version": "1"}, lambda r: {**r, "dek_version": None},
])
def test_malformed_record_is_value_error(env, mutate):
    _, _, enc = env
    rec = enc.encrypt("u1", "users", "email", "1", b"x")
    with pytest.raises(ValueError):
        enc.decrypt("u1", "users", "email", "1", mutate(rec))


def test_truncated_tag_is_rejected(env):
    _, _, enc = env
    rec = enc.encrypt("u1", "users", "email", "1", b"some longer plaintext")
    bad = {**rec, "ciphertext": rec["ciphertext"][:-1]}
    with pytest.raises(ValueError):
        enc.decrypt("u1", "users", "email", "1", bad)


# --- ротація KEK -------------------------------------------------------------------------------

def test_rotation_rewraps_deks_without_touching_records(env):
    kms, store, enc = env
    recs = {(u, i): enc.encrypt(u, "users", "email", str(i), f"{u}-{i}@x.io".encode())
            for u in ("u1", "u2", "u3") for i in range(3)}
    frozen = copy.deepcopy(recs)
    old_wrapped = {u: e["wrapped_dek"] for u, e in store.items()}
    assert enc.rotate_kek("kek-v2") == 3
    assert recs == frozen  # дані не перешифровувались
    for u, e in store.items():
        assert e["kek_id"] == "kek-v2" and e["wrapped_dek"] != old_wrapped[u] and e["version"] == 1
    kms.destroy_key("kek-v1")  # старий KEK більше не потрібен
    for (u, i), rec in recs.items():
        assert enc.decrypt(u, "users", "email", str(i), rec) == f"{u}-{i}@x.io".encode()


def test_rotation_uses_user_context_for_both_calls(env):
    kms, store, enc = env
    enc.encrypt("u1", "t", "f", "1", b"x")
    kms.unwrap_calls.clear()
    kms.wrap_calls.clear()
    enc.rotate_kek("kek-v2")
    assert kms.unwrap_calls == [("kek-v1", ctx("u1"))]
    assert kms.wrap_calls == [("kek-v2", ctx("u1"))]


def test_new_deks_use_new_kek_after_rotation_and_rotation_is_idempotent(env):
    kms, store, enc = env
    enc.encrypt("u1", "t", "f", "1", b"x")
    assert enc.rotate_kek("kek-v2") == 1
    assert enc.rotate_kek("kek-v2") == 0
    enc.encrypt("u2", "t", "f", "1", b"y")
    assert store["u2"]["kek_id"] == "kek-v2"


def test_rotation_skips_tombstones_and_keeps_shredding(env):
    kms, store, enc = env
    rec = enc.encrypt("u1", "t", "f", "1", b"x")
    enc.encrypt("u2", "t", "f", "1", b"y")
    enc.shred_user("u1")
    assert enc.rotate_kek("kek-v2") == 1
    assert store["u1"] == {"version": 1, "kek_id": None, "wrapped_dek": None}
    with pytest.raises(ShreddedError):
        enc.decrypt("u1", "t", "f", "1", rec)


def test_rotation_is_atomic_when_kms_fails_midway(env):
    kms, store, enc = env
    for u in ("u1", "u2", "u3"):
        enc.encrypt(u, "t", "f", "1", b"x")
    before = copy.deepcopy(store)
    kms.fail_wrap_on_call = len(kms.wrap_calls) + 2  # другий wrap під час ротації
    with pytest.raises(RuntimeError):
        enc.rotate_kek("kek-v2")
    assert store == before
    kms.fail_wrap_on_call = None
    enc.encrypt("u4", "t", "f", "1", b"x")
    assert store["u4"]["kek_id"] == "kek-v1"  # поточний KEK не змінився
    assert enc.rotate_kek("kek-v2") == 4


def test_rotation_with_destroyed_old_kek_raises_and_changes_nothing(env):
    kms, store, enc = env
    enc.encrypt("u1", "t", "f", "1", b"x")
    before = copy.deepcopy(store)
    kms.destroy_key("kek-v1")
    with pytest.raises(KeyError):
        enc.rotate_kek("kek-v2")
    assert store == before


# --- crypto-shredding --------------------------------------------------------------------------

def test_shred_makes_all_user_data_unreadable_but_keeps_others(env):
    kms, store, enc = env
    r1 = enc.encrypt("u1", "users", "email", "1", b"one@x.io")
    r2 = enc.encrypt("u1", "orders", "address", "9", b"street 1")
    r3 = enc.encrypt("u2", "users", "email", "2", b"two@x.io")
    wrapped = store["u1"]["wrapped_dek"]
    assert enc.shred_user("u1") is True
    assert store["u1"] == {"version": 1, "kek_id": None, "wrapped_dek": None}
    assert wrapped not in repr(store).encode()
    with pytest.raises(ShreddedError):
        enc.decrypt("u1", "users", "email", "1", r1)
    with pytest.raises(ShreddedError):
        enc.decrypt("u1", "orders", "address", "9", r2)
    assert enc.decrypt("u2", "users", "email", "2", r3) == b"two@x.io"


def test_shred_unknown_or_twice_returns_false(env):
    _, _, enc = env
    assert enc.shred_user("ghost") is False
    enc.encrypt("u1", "t", "f", "1", b"x")
    assert enc.shred_user("u1") is True
    assert enc.shred_user("u1") is False


def test_old_records_stay_dead_after_user_gets_a_new_dek(env):
    kms, store, enc = env
    old = enc.encrypt("u1", "users", "email", "1", b"old@x.io")
    enc.shred_user("u1")
    new = enc.encrypt("u1", "users", "email", "1", b"new@x.io")
    assert new["dek_version"] == 2 and store["u1"]["version"] == 2
    assert enc.decrypt("u1", "users", "email", "1", new) == b"new@x.io"
    with pytest.raises(ShreddedError):
        enc.decrypt("u1", "users", "email", "1", old)
    enc.shred_user("u1")
    enc.encrypt("u1", "users", "email", "1", b"newer@x.io")
    assert store["u1"]["version"] == 3


def test_record_with_wrong_dek_version_is_shredded_not_garbage(env):
    _, _, enc = env
    rec = enc.encrypt("u1", "t", "f", "1", b"x")
    with pytest.raises(ShreddedError):
        enc.decrypt("u1", "t", "f", "1", {**rec, "dek_version": 2})


def test_unknown_user_is_shredded_error(env):
    _, _, enc = env
    rec = enc.encrypt("u1", "t", "f", "1", b"x")
    with pytest.raises(ShreddedError):
        enc.decrypt("nobody", "t", "f", "1", rec)


def test_destroyed_kek_means_shredded_error(env):
    kms, _, enc = env
    rec = enc.encrypt("u1", "t", "f", "1", b"x")
    kms.destroy_key("kek-v1")
    with pytest.raises(ShreddedError):
        enc.decrypt("u1", "t", "f", "1", rec)
