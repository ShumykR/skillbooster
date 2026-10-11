import itertools

import pytest

from solution import authorize

ACTIONS = ["read", "update", "delete", "share"]


def user(roles=(), uid="u1", tenant="t1", clearance=0):
    return {"id": uid, "tenant": tenant, "roles": list(roles), "clearance": clearance}


def doc(owner="someone-else", tenant="t1", status="active", classification="internal"):
    return {"id": "r1", "tenant": tenant, "owner_id": owner, "status": status, "classification": classification}


def allowed(u, r):
    return {a for a in ACTIONS if authorize(u, a, r)}


# (ролі, чи власник, очікувані дозволені дії на звичайному ресурсі)
MATRIX = [
    ([], False, set()),
    (["viewer"], False, {"read"}),
    (["editor"], False, {"read", "update"}),
    (["admin"], False, {"read", "update", "delete", "share"}),
    ([], True, {"read", "update", "delete"}),
    (["viewer"], True, {"read", "update", "delete"}),
    (["editor"], True, {"read", "update", "delete"}),
    (["admin"], True, {"read", "update", "delete", "share"}),
    (["viewer", "editor"], False, {"read", "update"}),
    (["ghost"], False, set()),
    (["ghost", "viewer"], False, {"read"}),
]


@pytest.mark.parametrize("roles, is_owner, expected", MATRIX)
def test_permission_matrix(roles, is_owner, expected):
    u = user(roles)
    r = doc(owner="u1" if is_owner else "other")
    assert allowed(u, r) == expected


def test_unknown_action_is_denied_for_everyone():
    u = user(["admin"], uid="owner")
    r = doc(owner="owner")
    assert authorize(u, "launch", r) is False
    assert authorize(u, "", r) is False


@pytest.mark.parametrize("roles", [["viewer"], ["editor"], ["admin"], []])
def test_other_tenant_is_always_denied(roles):
    u = user(roles, uid="owner")
    assert allowed(u, doc(owner="owner", tenant="t2")) == set()


@pytest.mark.parametrize("u_tenant, r_tenant", [(None, None), ("", ""), (None, "t1"), ("t1", None)])
def test_missing_tenant_is_denied(u_tenant, r_tenant):
    u = user(["admin"])
    u["tenant"] = u_tenant
    r = doc()
    r["tenant"] = r_tenant
    assert allowed(u, r) == set()


@pytest.mark.parametrize("clearance, ok", [(0, False), (1, False), (2, True), (3, True)])
def test_confidential_requires_clearance_even_for_admin_and_owner(clearance, ok):
    u = user(["admin"], uid="o", clearance=clearance)
    r = doc(owner="o", classification="confidential")
    assert allowed(u, r) == (set(ACTIONS) if ok else set())


def test_missing_clearance_counts_as_zero():
    u = user(["admin"])
    del u["clearance"]
    assert allowed(u, doc(classification="confidential")) == set()
    assert authorize(u, "read", doc(classification="public")) is True


def test_non_confidential_ignores_clearance():
    for cls in ("public", "internal", None):
        r = doc(classification=cls)
        assert authorize(user(["viewer"], clearance=0), "read", r) is True


def test_archived_allows_only_read_and_admin_delete():
    r = doc(status="archived", owner="u1")
    assert allowed(user(["editor"]), r) == {"read"}  # власник теж: update/delete заборонені
    assert allowed(user(["admin"]), r) == {"read", "delete"}
    assert allowed(user(["viewer"], uid="x"), r) == {"read"}


def test_archived_admin_cannot_share_or_update():
    r = doc(status="archived")
    u = user(["admin"])
    assert authorize(u, "update", r) is False
    assert authorize(u, "share", r) is False
    assert authorize(u, "delete", r) is True


def test_archived_and_confidential_combine():
    r = doc(status="archived", classification="confidential")
    assert allowed(user(["admin"], clearance=1), r) == set()
    assert allowed(user(["admin"], clearance=2), r) == {"read", "delete"}


def test_missing_fields_do_not_raise():
    assert authorize({}, "read", {}) is False
    assert authorize({"tenant": "t1"}, "read", {"tenant": "t1"}) is False
    assert authorize({"tenant": "t1", "roles": None}, "read", {"tenant": "t1"}) is False
    assert authorize({"tenant": "t1", "roles": ["viewer"]}, "read", {"tenant": "t1"}) is True


def test_anonymous_user_without_id_is_not_the_owner_of_ownerless_resource():
    u = {"tenant": "t1", "roles": []}
    r = {"tenant": "t1"}
    assert allowed(u, r) == set()


def test_exhaustive_consistency_with_rules():
    # шлях "ззовні": жодна комбінація не може дати дозвіл, якого немає в матриці
    for roles, owner, status, cls, clearance in itertools.product(
        [[], ["viewer"], ["editor"], ["admin"]], [False, True], ["active", "archived"],
        ["internal", "confidential"], [0, 2],
    ):
        u = user(roles, uid="u1", clearance=clearance)
        r = doc(owner="u1" if owner else "x", status=status, classification=cls)
        got = allowed(u, r)
        if cls == "confidential" and clearance < 2:
            assert got == set()
        elif status == "archived":
            assert got <= {"read", "delete"}
            assert ("delete" in got) == ("admin" in roles)
        else:
            assert got <= {"read", "update", "delete", "share"}
