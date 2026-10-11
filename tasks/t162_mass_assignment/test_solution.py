import copy

import pytest
from fastapi.testclient import TestClient

from solution import create_app

USERS = {
    1: {"id": 1, "name": "Ann", "bio": "hello", "email": "ann@example.com", "role": "user", "is_active": True,
        "password_hash": "HASH-ann"},
    2: {"id": 2, "name": "Bob", "bio": None, "email": "bob@example.com", "role": "user", "is_active": True,
        "password_hash": "HASH-bob"},
    3: {"id": 3, "name": "Root", "bio": None, "email": "root@example.com", "role": "admin", "is_active": True,
        "password_hash": "HASH-root"},
    4: {"id": 4, "name": "Dead", "bio": None, "email": "dead@example.com", "role": "user", "is_active": False,
        "password_hash": "HASH-dead"},
    5: {"id": 5, "name": "Root2", "bio": None, "email": "root2@example.com", "role": "admin", "is_active": True,
        "password_hash": "HASH-root2"},
}

ME_KEYS = {"id", "name", "bio", "email"}
ADMIN_KEYS = {"id", "name", "email", "role", "is_active"}


@pytest.fixture
def users():
    return copy.deepcopy(USERS)


@pytest.fixture
def client(users):
    return TestClient(create_app(users))


def as_user(uid):
    return {"X-User-Id": str(uid)}


def assert_no_leak(response):
    assert "HASH-" not in response.text and "password_hash" not in response.text


# --- автентифікація ---------------------------------------------------------------------------------

@pytest.mark.parametrize("headers", [{}, {"X-User-Id": "abc"}, {"X-User-Id": ""}, {"X-User-Id": "999"},
                                     {"X-User-Id": "1.5"}, {"X-User-Id": "1; DROP"}])
def test_unauthenticated_is_401_everywhere(client, headers):
    assert client.get("/users/me", headers=headers).status_code == 401
    assert client.patch("/users/me", json={"name": "X"}, headers=headers).status_code == 401
    assert client.patch("/admin/users/2", json={"role": "admin"}, headers=headers).status_code == 401


def test_inactive_user_is_403_everywhere(client):
    h = as_user(4)
    assert client.get("/users/me", headers=h).status_code == 403
    assert client.patch("/users/me", json={"name": "X"}, headers=h).status_code == 403


# --- GET /users/me --------------------------------------------------------------------------------------

def test_get_me_returns_only_public_fields(client):
    r = client.get("/users/me", headers=as_user(1))
    assert r.status_code == 200
    assert r.json() == {"id": 1, "name": "Ann", "bio": "hello", "email": "ann@example.com"}
    assert_no_leak(r)


# --- PATCH /users/me: чесні запити -----------------------------------------------------------------------------

def test_patch_name_and_bio(client, users):
    r = client.patch("/users/me", json={"name": "Anna", "bio": "new bio"}, headers=as_user(1))
    assert r.status_code == 200
    assert set(r.json()) == ME_KEYS and r.json()["name"] == "Anna" and r.json()["bio"] == "new bio"
    assert users[1]["name"] == "Anna" and users[1]["bio"] == "new bio"
    assert_no_leak(r)


def test_partial_update_keeps_other_fields(client, users):
    client.patch("/users/me", json={"bio": "only bio"}, headers=as_user(1))
    assert users[1]["name"] == "Ann" and users[1]["bio"] == "only bio"
    client.patch("/users/me", json={"name": "Only Name"}, headers=as_user(1))
    assert users[1]["name"] == "Only Name" and users[1]["bio"] == "only bio"


def test_bio_null_clears_the_bio(client, users):
    r = client.patch("/users/me", json={"bio": None}, headers=as_user(1))
    assert r.status_code == 200 and r.json()["bio"] is None
    assert users[1]["bio"] is None


def test_name_is_stripped_and_limits_are_inclusive(client, users):
    assert client.patch("/users/me", json={"name": "  Ann Lee  "}, headers=as_user(1)).json()["name"] == "Ann Lee"
    assert client.patch("/users/me", json={"name": "n" * 50}, headers=as_user(1)).status_code == 200
    assert client.patch("/users/me", json={"bio": "b" * 500}, headers=as_user(1)).status_code == 200
    assert client.patch("/users/me", json={"bio": ""}, headers=as_user(1)).status_code == 200


def test_user_edits_only_own_profile(client, users):
    client.patch("/users/me", json={"name": "Changed"}, headers=as_user(2))
    assert users[2]["name"] == "Changed" and users[1]["name"] == "Ann"


# --- PATCH /users/me: mass assignment ---------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "field, value",
    [("role", "admin"), ("is_active", False), ("is_active", True), ("id", 99), ("id", 3), ("email", "evil@example.com"),
     ("password_hash", "pwned"), ("is_admin", True), ("is_superuser", True), ("created_at", "2000-01-01"),
     ("owner_id", 3), ("__class__", "x"), ("isAdmin", True), ("Role", "admin"), ("role ", "admin"), ("", "x")],
)
def test_privileged_or_unknown_fields_are_rejected_and_nothing_changes(client, users, field, value):
    before = copy.deepcopy(users)
    r = client.patch("/users/me", json={"name": "Hacker", field: value}, headers=as_user(1))
    assert r.status_code == 422
    assert users == before  # атомарно: навіть дозволене «name» не застосовано


def test_privileged_field_alone_is_rejected(client, users):
    before = copy.deepcopy(users)
    assert client.patch("/users/me", json={"role": "admin"}, headers=as_user(2)).status_code == 422
    assert users == before


@pytest.mark.parametrize(
    "body",
    [{}, [], ["name"], "name", 5, None, {"name": None}, {"name": ""}, {"name": "   "}, {"name": "n" * 51}, {"name": 5},
     {"name": True}, {"name": ["a"]}, {"bio": 5}, {"bio": "b" * 501}, {"bio": ["x"]}, {"bio": True}],
)
def test_invalid_bodies_are_422(client, users, body):
    before = copy.deepcopy(users)
    assert client.patch("/users/me", json=body, headers=as_user(1)).status_code == 422
    assert users == before


def test_non_json_body_is_422(client):
    r = client.patch("/users/me", content=b"name=Ann", headers={**as_user(1), "Content-Type": "application/json"})
    assert r.status_code == 422


# --- admin ---------------------------------------------------------------------------------------------------------------------

def test_admin_can_change_role_and_activity(client, users):
    r = client.patch("/admin/users/2", json={"role": "admin", "is_active": False}, headers=as_user(3))
    assert r.status_code == 200
    assert set(r.json()) == ADMIN_KEYS
    assert r.json() == {"id": 2, "name": "Bob", "email": "bob@example.com", "role": "admin", "is_active": False}
    assert users[2]["role"] == "admin" and users[2]["is_active"] is False
    assert_no_leak(r)


def test_admin_partial_updates(client, users):
    client.patch("/admin/users/2", json={"is_active": False}, headers=as_user(3))
    assert users[2]["is_active"] is False and users[2]["role"] == "user"
    client.patch("/admin/users/2", json={"role": "admin"}, headers=as_user(3))
    assert users[2]["role"] == "admin" and users[2]["is_active"] is False


@pytest.mark.parametrize("uid", [1, 2])
def test_non_admin_is_403(client, users, uid):
    before = copy.deepcopy(users)
    r = client.patch("/admin/users/2", json={"role": "admin"}, headers=as_user(uid))
    assert r.status_code == 403
    assert users == before


def test_access_check_comes_before_body_validation(client):
    # непривілейований не повинен бачити, які поля існують
    assert client.patch("/admin/users/2", json={"anything": 1}, headers=as_user(1)).status_code == 403
    assert client.patch("/admin/users/2", json={}, headers=as_user(1)).status_code == 403


def test_inactive_admin_is_403(client, users):
    users[3]["is_active"] = False
    assert client.patch("/admin/users/2", json={"role": "admin"}, headers=as_user(3)).status_code == 403


@pytest.mark.parametrize(
    "field, value",
    [("name", "Renamed"), ("email", "new@example.com"), ("id", 77), ("password_hash", "pwned"), ("bio", "x"),
     ("is_admin", True)],
)
def test_admin_endpoint_does_not_edit_other_fields(client, users, field, value):
    before = copy.deepcopy(users)
    r = client.patch("/admin/users/2", json={"role": "admin", field: value}, headers=as_user(3))
    assert r.status_code == 422
    assert users == before


@pytest.mark.parametrize(
    "body",
    [{}, [], None, {"role": "superuser"}, {"role": "ADMIN"}, {"role": None}, {"role": 1}, {"is_active": "yes"},
     {"is_active": 1}, {"is_active": "true"}, {"is_active": None}, {"is_active": 0}],
)
def test_admin_invalid_bodies_are_422(client, users, body):
    before = copy.deepcopy(users)
    assert client.patch("/admin/users/2", json=body, headers=as_user(3)).status_code == 422
    assert users == before


def test_unknown_target_is_404(client):
    assert client.patch("/admin/users/999", json={"role": "user"}, headers=as_user(3)).status_code == 404


def test_admin_cannot_modify_self(client, users):
    before = copy.deepcopy(users)
    assert client.patch("/admin/users/3", json={"role": "user"}, headers=as_user(3)).status_code == 409
    assert client.patch("/admin/users/3", json={"role": "admin"}, headers=as_user(3)).status_code == 409
    assert client.patch("/admin/users/3", json={"is_active": False}, headers=as_user(3)).status_code == 409
    assert users == before


def test_admin_can_modify_another_admin(client, users):
    assert client.patch("/admin/users/5", json={"role": "user"}, headers=as_user(3)).status_code == 200
    assert users[5]["role"] == "user"


def test_privilege_escalation_chain_does_not_work(client, users):
    # звичайний користувач намагається стати адміном двома шляхами
    client.patch("/users/me", json={"role": "admin"}, headers=as_user(1))
    client.patch("/admin/users/1", json={"role": "admin"}, headers=as_user(1))
    assert users[1]["role"] == "user"
