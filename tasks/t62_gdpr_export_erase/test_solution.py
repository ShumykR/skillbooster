import copy
import hashlib
import json

import pytest

from solution import UserNotFound, delete_user, export_user_data

PEPPER = "pepper-123"
NOW = 1_700_000_000.0


def make_db():
    return {
        "users": [
            {"id": 1, "email": "ann@example.com", "name": "Ann Petrenko", "phone": "+380501112233", "password_hash": "scrypt$abc", "_notes": "vip"},
            {"id": 2, "email": "bob@example.com", "name": "Bob Kovalenko", "phone": "+380502223344", "password_hash": "scrypt$def", "totp_secret": "T"},
        ],
        "addresses": [
            {"id": 10, "user_id": 1, "street": "Khreshchatyk 1", "city": "Kyiv"},
            {"id": 11, "user_id": 1, "street": "Lva Tolstoho 5", "city": "Kyiv"},
            {"id": 12, "user_id": 2, "street": "Soborna 3", "city": "Lviv"},
        ],
        "orders": [
            {"id": 100, "user_id": 1, "amount": 250, "currency": "UAH", "created_at": "2026-01-02", "email": "ann@example.com",
             "shipping_name": "Ann Petrenko", "shipping_address": "Khreshchatyk 1", "invoice_number": "INV-1"},
            {"id": 101, "user_id": 2, "amount": 90, "currency": "UAH", "created_at": "2026-01-03", "email": "bob@example.com",
             "shipping_name": "Bob Kovalenko", "shipping_address": "Soborna 3", "invoice_number": "INV-2"},
        ],
        "messages": [
            {"id": 1000, "author_id": 1, "to_user_id": 2, "text": "hello Bob"},
            {"id": 1001, "author_id": 2, "to_user_id": 1, "text": "hi Ann"},
            {"id": 1002, "author_id": 2, "to_user_id": 2, "text": "note to self"},
        ],
        "audit_log": [
            {"id": 5000, "user_id": 1, "action": "login", "ip": "203.0.113.7", "at": "2026-01-02T10:00:00"},
            {"id": 5001, "user_id": 2, "action": "login", "ip": "198.51.100.9", "at": "2026-01-02T11:00:00"},
        ],
        "deletion_requests": [],
    }


PSEUDONYM = "deleted-" + hashlib.sha256(f"{PEPPER}:1".encode()).hexdigest()[:12]


# ---------- експорт -----------------------------------------------------------


def test_export_contains_all_users_data():
    data = export_user_data(make_db(), 1)
    assert data["user"] == {"id": 1, "email": "ann@example.com", "name": "Ann Petrenko", "phone": "+380501112233"}
    assert [a["id"] for a in data["addresses"]] == [10, 11]
    assert [o["id"] for o in data["orders"]] == [100]
    assert [m["id"] for m in data["messages"]] == [1000]
    assert [a["id"] for a in data["audit_log"]] == [5000]
    assert data["audit_log"][0]["ip"] == "203.0.113.7"


def test_export_has_no_secrets_internal_fields_or_other_people():
    data = export_user_data(make_db(), 2)
    text = json.dumps(data)  # серіалізується
    for forbidden in ("scrypt", "totp_secret", "_notes", "ann@example.com", "Ann Petrenko", "hello Bob"):
        assert forbidden not in text
    assert "hi Ann" in text and "note to self" in text
    assert all(k not in data["user"] for k in ("password_hash", "totp_secret"))


def test_export_does_not_change_db_and_returns_copies():
    db = make_db()
    before = copy.deepcopy(db)
    data = export_user_data(db, 1)
    data["user"]["name"] = "HACKED"
    data["addresses"][0]["city"] = "HACKED"
    assert db == before


def test_export_unknown_user():
    with pytest.raises(UserNotFound):
        export_user_data(make_db(), 999)


# ---------- видалення ---------------------------------------------------------


def test_delete_report_and_removed_rows():
    db = make_db()
    report = delete_user(db, 1, pepper=PEPPER, now=NOW)
    assert report == {
        "status": "deleted",
        "pseudonym": PSEUDONYM,
        "removed": {"users": 1, "addresses": 2, "messages": 1},
        "anonymized": {"orders": 1, "audit_log": 1, "messages_received": 1},
    }
    assert [u["id"] for u in db["users"]] == [2]
    assert [a["id"] for a in db["addresses"]] == [12]
    assert [m["id"] for m in db["messages"]] == [1001, 1002]


def test_orders_are_kept_but_anonymized():
    db = make_db()
    delete_user(db, 1, pepper=PEPPER, now=NOW)
    order = next(o for o in db["orders"] if o["id"] == 100)
    assert order == {"id": 100, "user_id": PSEUDONYM, "amount": 250, "currency": "UAH", "created_at": "2026-01-02",
                     "email": None, "shipping_name": None, "shipping_address": None, "invoice_number": "INV-1"}


def test_audit_log_and_received_messages_are_pseudonymized():
    db = make_db()
    delete_user(db, 1, pepper=PEPPER, now=NOW)
    entry = next(a for a in db["audit_log"] if a["id"] == 5000)
    assert entry == {"id": 5000, "user_id": PSEUDONYM, "action": "login", "ip": None, "at": "2026-01-02T10:00:00"}
    received = next(m for m in db["messages"] if m["id"] == 1001)
    assert received["to_user_id"] == PSEUDONYM and received["text"] == "hi Ann"


def test_no_personal_data_of_the_user_remains_anywhere():
    db = make_db()
    delete_user(db, 1, pepper=PEPPER, now=NOW)
    blob = json.dumps(db)
    for pii in ("ann@example.com", "Ann Petrenko", "+380501112233", "Khreshchatyk", "203.0.113.7", "scrypt$abc", "Lva Tolstoho"):
        assert pii not in blob, pii
    for table, columns in (("orders", ("user_id",)), ("audit_log", ("user_id",)), ("messages", ("author_id", "to_user_id")),
                           ("addresses", ("user_id",)), ("users", ("id",))):
        for row in db[table]:
            for column in columns:
                assert row.get(column) != 1, f"{table}.{column} досі містить сирий user_id"


def test_other_users_are_untouched():
    db = make_db()
    before = copy.deepcopy(db)
    delete_user(db, 1, pepper=PEPPER, now=NOW)
    assert db["users"][0] == before["users"][1]
    assert db["addresses"] == [before["addresses"][2]]
    assert db["orders"][1] == before["orders"][1]
    assert db["audit_log"][1] == before["audit_log"][1]
    assert db["messages"][1] == before["messages"][2]


def test_deletion_request_is_logged_without_personal_data():
    db = make_db()
    delete_user(db, 1, pepper=PEPPER, now=NOW)
    assert db["deletion_requests"] == [{"pseudonym": PSEUDONYM, "at": NOW}]


def test_pseudonym_depends_on_pepper_and_user():
    a, b, c = make_db(), make_db(), make_db()
    assert delete_user(a, 1, pepper="p1", now=NOW)["pseudonym"] != delete_user(b, 1, pepper="p2", now=NOW)["pseudonym"]
    assert delete_user(c, 2, pepper="p1", now=NOW)["pseudonym"] != delete_user(make_db(), 1, pepper="p1", now=NOW)["pseudonym"]


def test_delete_is_idempotent():
    db = make_db()
    delete_user(db, 1, pepper=PEPPER, now=NOW)
    snapshot = copy.deepcopy(db)
    assert delete_user(db, 1, pepper=PEPPER, now=NOW + 5) == {"status": "already_deleted"}
    assert db == snapshot


def test_delete_unknown_user_and_export_after_delete():
    db = make_db()
    with pytest.raises(UserNotFound):
        delete_user(db, 999, pepper=PEPPER, now=NOW)
    assert db["deletion_requests"] == []
    delete_user(db, 1, pepper=PEPPER, now=NOW)
    with pytest.raises(UserNotFound):
        export_user_data(db, 1)
