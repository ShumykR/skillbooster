import copy
import hashlib
import hmac
import json

import pytest

from solution import AuditLog, verify

KEY = b"audit-key-0123456789"
GENESIS = "0" * 64


def canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def mac(key, obj):
    return hmac.new(key, canon(obj), hashlib.sha256).hexdigest()


def entry_hash(e):
    keys = ("seq", "ts", "actor", "action", "data", "pii_hashes", "subject_hash", "prev")
    return hashlib.sha256(canon({k: e[k] for k in keys})).hexdigest()


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        self.t += 1
        return self.t


@pytest.fixture
def log():
    return AuditLog(KEY, Clock())


def filled(log, n=6):
    for i in range(n):
        log.append("agent", f"tool_call_{i}", {"step": i, "ok": True})
    return log.export()


def reseal(entries, start=0):
    """Атакувач перераховує хеші й посилання від позиції start (без доступу до якоря)."""
    prev = entries[start - 1]["hash"] if start else GENESIS
    for i in range(start, len(entries)):
        entries[i]["prev"] = prev
        entries[i]["hash"] = entry_hash(entries[i])
        prev = entries[i]["hash"]


# --- append / формат запису --------------------------------------------------------------------

def test_append_returns_sequential_numbers(log):
    assert [log.append("a", "x", {}) for _ in range(3)] == [0, 1, 2]


def test_first_entry_matches_the_documented_format(log):
    seq = log.append("agent-7", "approve_refund", {"amount": 12, "currency": "EUR"},
                     pii={"email": "alice@example.com", "name": "Аліса"}, subject="user-42")
    e = log.export()[0]
    assert seq == 0
    assert e["seq"] == 0 and e["ts"] == 1001.0 and e["actor"] == "agent-7" and e["action"] == "approve_refund"
    assert e["data"] == {"amount": 12, "currency": "EUR"}
    assert e["pii"] == {"email": "alice@example.com", "name": "Аліса"} and e["erased"] is False
    assert e["pii_hashes"] == {
        "email": mac(KEY, {"seq": 0, "field": "email", "value": "alice@example.com"}),
        "name": mac(KEY, {"seq": 0, "field": "name", "value": "Аліса"}),
    }
    assert e["subject_hash"] == mac(KEY, {"subject": "user-42"})
    assert e["prev"] == GENESIS
    assert e["hash"] == entry_hash(e)


def test_entries_are_chained(log):
    entries = filled(log)
    assert entries[0]["prev"] == GENESIS
    for i in range(1, len(entries)):
        assert entries[i]["prev"] == entries[i - 1]["hash"]
        assert entries[i]["hash"] == entry_hash(entries[i])
    assert len({e["hash"] for e in entries}) == len(entries)


def test_entry_without_pii_or_subject(log):
    log.append("a", "x", {"k": 1})
    e = log.export()[0]
    assert e["pii"] == {} and e["pii_hashes"] == {} and e["subject_hash"] is None


def test_pii_hash_depends_on_seq_field_and_key():
    a, b = AuditLog(KEY, Clock()), AuditLog(b"another-key-xxxxxxxxx", Clock())
    for lg in (a, b):
        lg.append("x", "y", {}, pii={"email": "e@x.io"})
        lg.append("x", "y", {}, pii={"email": "e@x.io"})
    ea, eb = a.export(), b.export()
    assert ea[0]["pii_hashes"]["email"] != ea[1]["pii_hashes"]["email"]  # одне значення, різні seq
    assert ea[0]["pii_hashes"]["email"] != eb[0]["pii_hashes"]["email"]


def test_plain_subject_and_pii_never_enter_the_hashed_fields(log):
    log.append("a", "x", {"k": 1}, pii={"email": "alice@example.com"}, subject="alice-the-subject")
    e = log.export()[0]
    hashed = {k: e[k] for k in ("data", "pii_hashes", "subject_hash", "actor", "action")}
    blob = json.dumps(hashed)
    assert "alice@example.com" not in blob and "alice-the-subject" not in blob


def test_log_stores_copies_of_inputs(log):
    data, pii = {"nested": {"n": 1}}, {"tags": ["a"]}
    log.append("a", "x", data, pii=pii)
    data["nested"]["n"] = 999
    pii["tags"].append("b")
    e = log.export()[0]
    assert e["data"] == {"nested": {"n": 1}} and e["pii"] == {"tags": ["a"]}
    assert verify(log.export(), hmac_key=KEY)["ok"]


def test_export_is_a_deep_copy(log):
    filled(log, 3)
    ex = log.export()
    ex[0]["data"]["step"] = 123
    ex[1]["hash"] = "x"
    ex.pop()
    assert verify(log.export(), hmac_key=KEY)["ok"] and len(log.export()) == 3


@pytest.mark.parametrize("args, kwargs", [
    (("", "x", {}), {}), (("a", "", {}), {}), ((None, "x", {}), {}), (("a", "x", []), {}), (("a", "x", None), {}),
    (("a", "x", {}), {"pii": [1]}), (("a", "x", {}), {"subject": ""}), (("a", "x", {}), {"subject": 5}),
    (("a", "x", {"bad": object()}), {}), (("a", "x", {}), {"pii": {"f": object()}}),
])
def test_append_validation(log, args, kwargs):
    with pytest.raises(ValueError):
        log.append(*args, **kwargs)
    assert log.export() == []


# --- verify: чесний журнал ---------------------------------------------------------------------

def test_verify_ok_for_honest_log_and_empty_log(log):
    assert verify([]) == {"ok": True, "broken_at": None, "reason": None}
    entries = filled(log, 12)
    assert verify(entries) == {"ok": True, "broken_at": None, "reason": None}
    assert verify(entries, anchor=log.anchor(), hmac_key=KEY)["ok"] is True


def test_anchor(log):
    assert log.anchor() == {"count": 0, "hash": GENESIS}
    entries = filled(log, 4)
    assert log.anchor() == {"count": 4, "hash": entries[-1]["hash"]}


# --- verify: зміни, вставки, видалення ---------------------------------------------------------

@pytest.mark.parametrize("field, value", [
    ("data", {"step": 99}), ("actor", "mallory"), ("action", "delete_everything"), ("ts", 5.0),
    ("pii_hashes", {"email": "0" * 64}), ("subject_hash", "f" * 64),
])
def test_modified_field_is_detected_at_its_position(log, field, value):
    entries = filled(log, 6)
    entries[3][field] = value
    assert verify(entries) == {"ok": False, "broken_at": 3, "reason": "bad-hash"}


def test_modified_hash_field_is_detected_in_place(log):
    entries = filled(log, 6)
    entries[2]["hash"] = "a" * 64
    assert verify(entries) == {"ok": False, "broken_at": 2, "reason": "bad-hash"}


def test_modified_prev_and_seq(log):
    entries = filled(log, 6)
    entries[4]["prev"] = "b" * 64
    assert verify(entries) == {"ok": False, "broken_at": 4, "reason": "bad-link"}
    entries = filled(AuditLog(KEY, Clock()), 6)
    entries[4]["seq"] = 7
    assert verify(entries) == {"ok": False, "broken_at": 4, "reason": "bad-seq"}


def test_first_entry_must_link_to_genesis(log):
    entries = filled(log, 3)
    entries[0]["prev"] = "c" * 64
    assert verify(entries) == {"ok": False, "broken_at": 0, "reason": "bad-link"}


@pytest.mark.parametrize("index", [0, 1, 3, 4])
def test_deleted_entry_is_detected(log, index):
    entries = filled(log, 5)
    del entries[index]
    if index == 4:  # видалено останній: ланцюжок цілий, виявляє лише якір
        assert verify(entries)["ok"] is True
    else:
        assert verify(entries) == {"ok": False, "broken_at": index, "reason": "bad-seq"}


def test_deleted_entry_with_renumbering_is_detected_by_link(log):
    entries = filled(log, 5)
    del entries[2]
    for i, e in enumerate(entries):
        e["seq"] = i
    result = verify(entries)
    assert result["ok"] is False and result["broken_at"] == 2


def test_swapped_entries_are_detected(log):
    entries = filled(log, 5)
    entries[1], entries[2] = entries[2], entries[1]
    assert verify(entries) == {"ok": False, "broken_at": 1, "reason": "bad-seq"}


def test_duplicated_entry_is_detected(log):
    entries = filled(log, 4)
    entries.insert(3, copy.deepcopy(entries[1]))
    assert verify(entries)["ok"] is False


def test_forged_entry_with_valid_own_hash_is_detected_at_the_next_one(log):
    entries = filled(log, 5)
    forged = {"seq": 2, "ts": 1.0, "actor": "mallory", "action": "grant_admin", "data": {}, "pii_hashes": {},
              "subject_hash": None, "pii": {}, "erased": False, "prev": entries[1]["hash"]}
    forged["hash"] = entry_hash(forged)
    entries.insert(2, forged)
    assert verify(entries) == {"ok": False, "broken_at": 3, "reason": "bad-seq"}


def test_rewriting_the_tail_is_caught_only_with_an_anchor(log):
    entries = filled(log, 6)
    anchor = log.anchor()
    entries[3]["data"] = {"step": "rewritten"}
    reseal(entries, 3)
    assert verify(entries)["ok"] is True  # самого ланцюжка замало
    assert verify(entries, anchor=anchor) == {"ok": False, "broken_at": 6, "reason": "truncated"}


def test_truncated_tail_is_caught_only_with_an_anchor(log):
    entries = filled(log, 6)
    anchor = log.anchor()
    cut = entries[:4]
    assert verify(cut)["ok"] is True
    assert verify(cut, anchor=anchor) == {"ok": False, "broken_at": 4, "reason": "truncated"}
    assert verify([], anchor=anchor) == {"ok": False, "broken_at": 0, "reason": "truncated"}
    assert verify([], anchor={"count": 0, "hash": GENESIS})["ok"] is True


def test_appended_forged_entries_beyond_the_anchor_are_caught(log):
    entries = filled(log, 3)
    anchor = log.anchor()
    forged = {"seq": 3, "ts": 1.0, "actor": "m", "action": "x", "data": {}, "pii_hashes": {}, "subject_hash": None,
              "pii": {}, "erased": False, "prev": entries[-1]["hash"]}
    forged["hash"] = entry_hash(forged)
    entries.append(forged)
    assert verify(entries)["ok"] is True
    assert verify(entries, anchor=anchor)["reason"] == "truncated"


@pytest.mark.parametrize("bad", [None, 5, "x", [], {}, {"seq": 0}, {"seq": 0, "prev": GENESIS}])
def test_garbage_entries_never_raise(bad):
    result = verify([bad])
    assert result["ok"] is False and result["broken_at"] == 0 and result["reason"] == "bad-seq"


# --- PII: видалення без зламу ланцюжка ---------------------------------------------------------

def make_pii_log():
    lg = AuditLog(KEY, Clock())
    lg.append("agent", "lookup", {"q": 1}, pii={"email": "alice@example.com", "phone": "+380501112233"}, subject="alice")
    lg.append("agent", "lookup", {"q": 2}, pii={"email": "bob@example.com"}, subject="bob")
    lg.append("agent", "summary", {"q": 3})
    lg.append("agent", "lookup", {"q": 4}, pii={"email": "alice@example.com"}, subject="alice")
    return lg


def test_erase_subject_removes_values_but_keeps_chain_valid():
    lg = make_pii_log()
    before = lg.export()
    assert "alice@example.com" in json.dumps(before)
    assert lg.erase_subject("alice") == 2
    after = lg.export()
    assert "alice@example.com" not in json.dumps(after) and "+380501112233" not in json.dumps(after)
    assert verify(after)["ok"] and verify(after, anchor=lg.anchor(), hmac_key=KEY)["ok"]
    for b, a in zip(before, after):
        assert a["hash"] == b["hash"] and a["prev"] == b["prev"] and a["pii_hashes"] == b["pii_hashes"]
        assert a["data"] == b["data"] and a["subject_hash"] == b["subject_hash"]


def test_erase_marks_only_that_subjects_entries():
    lg = make_pii_log()
    lg.erase_subject("alice")
    e = lg.export()
    assert [x["erased"] for x in e] == [True, False, False, True]
    assert e[0]["pii"] == {} and e[3]["pii"] == {}
    assert e[1]["pii"] == {"email": "bob@example.com"}


def test_erase_is_idempotent_and_unknown_subject_is_zero():
    lg = make_pii_log()
    assert lg.erase_subject("nobody") == 0
    assert lg.erase_subject("alice") == 2
    assert lg.erase_subject("alice") == 0
    assert lg.erase_subject("bob") == 1


def test_log_keeps_working_after_erase():
    lg = make_pii_log()
    lg.erase_subject("alice")
    lg.append("agent", "later", {"q": 5}, pii={"email": "c@x.io"}, subject="carol")
    ex = lg.export()
    assert len(ex) == 5 and ex[4]["prev"] == ex[3]["hash"]
    assert verify(ex, anchor=lg.anchor(), hmac_key=KEY)["ok"]


def test_erased_entries_cannot_be_verified_against_pii_but_tampering_with_hashes_still_fails():
    lg = make_pii_log()
    lg.erase_subject("alice")
    ex = lg.export()
    ex[0]["pii_hashes"]["email"] = "0" * 64
    assert verify(ex, hmac_key=KEY) == {"ok": False, "broken_at": 0, "reason": "bad-hash"}


def test_pii_mismatch_needs_the_key():
    lg = make_pii_log()
    ex = lg.export()
    ex[1]["pii"]["email"] = "evil@example.com"  # значення підмінили, хеш запису цілий
    assert verify(ex)["ok"] is True
    assert verify(ex, hmac_key=KEY) == {"ok": False, "broken_at": 1, "reason": "pii-mismatch"}
    assert verify(lg.export(), hmac_key=b"wrong-key-wrong-key-1")["reason"] == "pii-mismatch"


@pytest.mark.parametrize("mutate", [
    lambda e: e["pii"].update(extra="x"),
    lambda e: e["pii"].pop("email"),
    lambda e: e.update(pii={}),  # значення прибрали, а прапорець erased не виставили
])
def test_pii_fields_must_match_hashes(mutate):
    lg = make_pii_log()
    ex = lg.export()
    mutate(ex[1])
    assert verify(ex, hmac_key=KEY) == {"ok": False, "broken_at": 1, "reason": "pii-mismatch"}


def test_checks_run_in_documented_order():
    lg = make_pii_log()
    ex = lg.export()
    ex[1]["seq"] = 5
    ex[1]["prev"] = "x"
    ex[1]["pii"]["email"] = "z"
    assert verify(ex, hmac_key=KEY)["reason"] == "bad-seq"
    ex[1]["seq"] = 1
    assert verify(ex, hmac_key=KEY)["reason"] == "bad-link"
    ex[1]["prev"] = ex[0]["hash"]
    assert verify(ex, hmac_key=KEY)["reason"] == "pii-mismatch"
    ex[1]["data"] = {"q": "changed"}
    assert verify(ex, hmac_key=KEY)["reason"] == "bad-hash"
