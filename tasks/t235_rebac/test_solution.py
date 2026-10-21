import threading

import pytest

from solution import Decision, ReBAC

ALICE, BOB, EVE = "user:alice", "user:bob", "user:eve"


def bounded(fn, *args, timeout=5, **kw):
    """Виконує fn у daemon-потоці: рішення, що зациклилось на циклі, дає провал, а не завислий pytest."""
    box = {}

    def run():
        try:
            box["value"] = fn(*args, **kw)
        except BaseException as e:  # noqa: BLE001
            box["error"] = e

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        pytest.fail("перевірка не завершилась: цикл у даних зациклив обхід")
    if "error" in box:
        raise box["error"]
    return box["value"]


def make(tuples=(), **kw):
    r = ReBAC(**kw)
    r.write(add=tuples)
    return r


def allowed(r, user, rel, obj, **kw):
    return r.check(user, rel, obj, **kw).allowed


def assert_path_is_valid(r, decision, user, at=None):
    """Шлях це реальні кортежі сховища, що з'єднують обʼєкт із користувачем."""
    stored = set(r.tuples(at))
    assert decision.allowed
    assert decision.path, "дозвіл без пояснення"
    for t in decision.path:
        assert t in stored
    assert decision.path[-1][2] == user


# --- прямі відносини і виведення ---------------------------------------------------------------

def test_direct_relation_with_explanation():
    r = make([("doc:1", "viewer", ALICE)])
    d = r.check(ALICE, "viewer", "doc:1")
    assert d == Decision(True, (("doc:1", "viewer", ALICE),), "allowed")
    assert r.check(BOB, "viewer", "doc:1") == Decision(False, (), "no_path")


def test_owner_implies_editor_implies_viewer_without_extra_tuples():
    r = make([("doc:1", "owner", ALICE), ("doc:2", "editor", BOB), ("doc:3", "viewer", EVE)])
    assert [allowed(r, ALICE, rel, "doc:1") for rel in ("owner", "editor", "viewer")] == [True, True, True]
    assert [allowed(r, BOB, rel, "doc:2") for rel in ("owner", "editor", "viewer")] == [False, True, True]
    assert [allowed(r, EVE, rel, "doc:3") for rel in ("owner", "editor", "viewer")] == [False, False, True]
    assert r.check(ALICE, "viewer", "doc:1").path == (("doc:1", "owner", ALICE),)


def test_relations_do_not_leak_between_objects_or_users():
    r = make([("doc:1", "owner", ALICE)])
    assert not allowed(r, ALICE, "viewer", "doc:2")
    assert not allowed(r, "user:alice2", "viewer", "doc:1")
    assert not allowed(r, "user:ali", "viewer", "doc:1")
    assert not allowed(r, ALICE, "viewer", "doc:10")
    assert not allowed(r, ALICE, "viewer", "folder:1")


def test_object_id_prefixes_do_not_collide():
    r = make([("doc:1", "viewer", ALICE), ("doc:10", "viewer", BOB)])
    assert allowed(r, BOB, "viewer", "doc:10") and not allowed(r, BOB, "viewer", "doc:1")
    assert allowed(r, ALICE, "viewer", "doc:1") and not allowed(r, ALICE, "viewer", "doc:10")


# --- спадкування від теки ----------------------------------------------------------------------

def test_folder_roles_flow_to_documents_but_owner_does_not():
    r = make([("doc:1", "parent", "folder:a"), ("folder:a", "owner", ALICE),
              ("folder:a", "editor", BOB), ("folder:a", "viewer", EVE)])
    assert [allowed(r, ALICE, rel, "doc:1") for rel in ("owner", "editor", "viewer")] == [False, True, True]
    assert [allowed(r, BOB, rel, "doc:1") for rel in ("owner", "editor", "viewer")] == [False, True, True]
    assert [allowed(r, EVE, rel, "doc:1") for rel in ("owner", "editor", "viewer")] == [False, False, True]
    assert r.check(ALICE, "editor", "doc:1").path == (("doc:1", "parent", "folder:a"), ("folder:a", "owner", ALICE))


def test_nested_folders_and_exact_path():
    r = make([("doc:1", "parent", "folder:c"), ("folder:c", "parent", "folder:b"),
              ("folder:b", "parent", "folder:a"), ("folder:a", "viewer", ALICE)])
    d = r.check(ALICE, "viewer", "doc:1")
    assert d.path == (("doc:1", "parent", "folder:c"), ("folder:c", "parent", "folder:b"),
                      ("folder:b", "parent", "folder:a"), ("folder:a", "viewer", ALICE))
    assert not allowed(r, ALICE, "editor", "doc:1")
    assert allowed(r, ALICE, "viewer", "folder:c")


def test_idor_other_folder_stays_closed():
    r = make([("doc:1", "parent", "folder:a"), ("doc:2", "parent", "folder:b"), ("folder:a", "viewer", ALICE),
              ("folder:b", "viewer", BOB)])
    assert allowed(r, ALICE, "viewer", "doc:1") and not allowed(r, ALICE, "viewer", "doc:2")
    assert allowed(r, BOB, "viewer", "doc:2") and not allowed(r, BOB, "viewer", "doc:1")


def test_parent_does_not_grant_downwards_to_parent_folder():
    r = make([("folder:b", "parent", "folder:a"), ("folder:b", "viewer", ALICE)])
    assert allowed(r, ALICE, "viewer", "folder:b")
    assert not allowed(r, ALICE, "viewer", "folder:a")


# --- групи -------------------------------------------------------------------------------------

def test_group_userset_with_exact_path():
    r = make([("doc:1", "viewer", "group:eng#member"), ("group:eng", "member", BOB)])
    d = r.check(BOB, "viewer", "doc:1")
    assert d.path == (("doc:1", "viewer", "group:eng#member"), ("group:eng", "member", BOB))
    assert not allowed(r, ALICE, "viewer", "doc:1")
    assert allowed(r, BOB, "member", "group:eng")


def test_nested_groups_and_group_inside_folder_inheritance():
    r = make([("doc:1", "parent", "folder:a"), ("folder:a", "editor", "group:all#member"),
              ("group:all", "member", "group:eng#member"), ("group:eng", "member", ALICE)])
    d = r.check(ALICE, "editor", "doc:1")
    assert d.path == (("doc:1", "parent", "folder:a"), ("folder:a", "editor", "group:all#member"),
                      ("group:all", "member", "group:eng#member"), ("group:eng", "member", ALICE))
    assert not allowed(r, BOB, "viewer", "doc:1")


def test_group_membership_is_not_the_group_object_itself():
    r = make([("doc:1", "viewer", "group:eng#member")])
    assert not allowed(r, "user:eng", "viewer", "doc:1")


# --- цикли й глибина ---------------------------------------------------------------------------

def test_group_cycle_terminates():
    r = make([("group:a", "member", "group:b#member"), ("group:b", "member", "group:a#member"),
              ("doc:1", "viewer", "group:a#member")])
    d = bounded(r.check, ALICE, "viewer", "doc:1")
    assert d == Decision(False, (), "no_path")
    r.write(add=[("group:b", "member", ALICE)])
    assert bounded(r.check, ALICE, "viewer", "doc:1").allowed


def test_folder_cycle_terminates():
    r = make([("folder:a", "parent", "folder:b"), ("folder:b", "parent", "folder:a"), ("doc:1", "parent", "folder:a")])
    assert bounded(r.check, ALICE, "viewer", "doc:1") == Decision(False, (), "no_path")
    r.write(add=[("folder:b", "viewer", ALICE)])
    assert bounded(r.check, ALICE, "viewer", "doc:1").allowed
    assert bounded(r.check, ALICE, "viewer", "folder:a").allowed


def test_self_referencing_group():
    r = make([("group:a", "member", "group:a#member"), ("doc:1", "viewer", "group:a#member")])
    assert not bounded(r.check, ALICE, "viewer", "doc:1").allowed


def chain(n):
    """n груп у ланцюжку; ALICE у g0, doc:1 бачить g(n-1)#member. Шлях: 1 + (n-1) + 1 кортежів."""
    t = [("group:g0", "member", ALICE)]
    t += [(f"group:g{i}", "member", f"group:g{i - 1}#member") for i in range(1, n)]
    t += [("doc:1", "viewer", f"group:g{n - 1}#member")]
    return t


def test_depth_limit_boundary():
    r = make(chain(4), max_depth=5)  # шлях 1 + 3 + 1 = 5 кортежів
    d = r.check(ALICE, "viewer", "doc:1")
    assert d.allowed and len(d.path) == 5
    r2 = make(chain(5), max_depth=5)  # шлях 6 кортежів
    d2 = r2.check(ALICE, "viewer", "doc:1")
    assert d2 == Decision(False, (), "depth_limit")


def test_default_depth_is_ten():
    assert allowed(make(chain(9)), ALICE, "viewer", "doc:1")       # 10 кортежів
    assert not allowed(make(chain(10)), ALICE, "viewer", "doc:1")  # 11


def test_long_chain_does_not_blow_the_stack():
    r = make(chain(1500), max_depth=5000)
    assert allowed(r, ALICE, "viewer", "doc:1")


def test_shorter_path_is_preferred_over_longer():
    t = chain(4) + [("doc:1", "viewer", "group:g0#member")]
    d = make(t, max_depth=10).check(ALICE, "viewer", "doc:1")
    assert d.path == (("doc:1", "viewer", "group:g0#member"), ("group:g0", "member", ALICE))


def test_derivation_rules_do_not_count_as_hops():
    r = make([("doc:1", "owner", ALICE)], max_depth=1)
    assert allowed(r, ALICE, "viewer", "doc:1")


# --- write, версії, знімки ---------------------------------------------------------------------

def test_versions_and_noop_writes():
    r = ReBAC()
    assert r.version == 0 and r.tuples() == []
    assert r.write(add=[("doc:1", "viewer", ALICE)]) == 1
    assert r.write(add=[("doc:1", "viewer", ALICE)]) == 1      # дублікат
    assert r.write(remove=[("doc:9", "viewer", ALICE)]) == 1   # видалення неіснуючого
    assert r.write() == 1
    assert r.write(add=[("doc:2", "viewer", ALICE)], remove=[("doc:1", "viewer", ALICE)]) == 2
    assert r.version == 2
    assert r.tuples() == [("doc:2", "viewer", ALICE)]


def test_remove_applies_before_add_in_the_same_batch():
    r = make([("doc:1", "viewer", ALICE)])
    v = r.write(add=[("doc:1", "viewer", ALICE)], remove=[("doc:1", "viewer", ALICE)])
    assert v == 1
    assert allowed(r, ALICE, "viewer", "doc:1")


def test_deleting_tuples_revokes_access_immediately():
    r = make([("doc:1", "parent", "folder:a"), ("folder:a", "viewer", "group:eng#member"), ("group:eng", "member", BOB)])
    assert allowed(r, BOB, "viewer", "doc:1")
    r.write(remove=[("group:eng", "member", BOB)])
    assert not allowed(r, BOB, "viewer", "doc:1")
    r.write(add=[("group:eng", "member", BOB)])
    assert allowed(r, BOB, "viewer", "doc:1")
    r.write(remove=[("doc:1", "parent", "folder:a")])  # документ перенесли
    assert not allowed(r, BOB, "viewer", "doc:1")


def test_invalid_tuple_rejects_whole_batch():
    r = make([("doc:1", "viewer", ALICE)])
    with pytest.raises(ValueError):
        r.write(add=[("doc:2", "viewer", BOB), ("doc:3", "boss", BOB)])
    assert r.version == 1 and r.tuples() == [("doc:1", "viewer", ALICE)]
    with pytest.raises(ValueError):
        r.write(add=[("doc:2", "viewer", BOB)], remove=[("nonsense",)])
    assert r.version == 1 and r.tuples() == [("doc:1", "viewer", ALICE)]


@pytest.mark.parametrize("bad", [
    ("doc:1", "member", ALICE), ("group:g", "viewer", ALICE), ("doc:1", "viewer", "doc:2"),
    ("doc:1", "viewer", "alice"), ("doc:1", "viewer", "group:eng"), ("doc:1", "viewer", "group:eng#viewer"),
    ("doc:1", "viewer", "user:"), ("doc:1", "viewer", "user:a#b"), ("doc:1", "viewer", "user:a b"),
    ("doc:1", "parent", ALICE), ("doc:1", "parent", "doc:2"), ("doc:1", "parent", "folder:a#member"),
    ("1", "viewer", ALICE), ("file:1", "viewer", ALICE), ("doc:", "viewer", ALICE), ("doc:a:b", "viewer", ALICE),
    ("doc:1", "viewer"), ("doc:1", "viewer", None), (1, 2, 3), ("user:alice", "viewer", ALICE),
])
def test_malformed_tuples_are_rejected(bad):
    with pytest.raises(ValueError):
        ReBAC().write(add=[bad])


@pytest.mark.parametrize("user, rel, obj", [
    ("alice", "viewer", "doc:1"), ("user:", "viewer", "doc:1"), ("group:eng#member", "viewer", "doc:1"),
    (ALICE, "parent", "doc:1"), (ALICE, "boss", "doc:1"), (ALICE, "member", "doc:1"), (ALICE, "viewer", "group:eng"),
    (ALICE, "viewer", "doc:"), (ALICE, "viewer", "x"), (None, "viewer", "doc:1"), (ALICE, "viewer", None),
])
def test_check_validates_arguments(user, rel, obj):
    with pytest.raises(ValueError):
        make([("doc:1", "viewer", ALICE)]).check(user, rel, obj)


def test_snapshots_keep_old_state():
    r = ReBAC()
    r.write(add=[("doc:1", "viewer", ALICE)])           # v1
    r.write(remove=[("doc:1", "viewer", ALICE)])        # v2
    r.write(add=[("doc:1", "viewer", BOB)])             # v3
    assert allowed(r, ALICE, "viewer", "doc:1", at_version=1)
    assert not allowed(r, ALICE, "viewer", "doc:1", at_version=2)
    assert not allowed(r, ALICE, "viewer", "doc:1")
    assert allowed(r, BOB, "viewer", "doc:1", at_version=3) and not allowed(r, BOB, "viewer", "doc:1", at_version=1)
    assert r.tuples(at_version=0) == [] and r.tuples(1) == [("doc:1", "viewer", ALICE)]
    d = r.check(ALICE, "viewer", "doc:1", at_version=1)
    assert_path_is_valid(r, d, ALICE, at=1)


@pytest.mark.parametrize("v", [4, 99, -1])
def test_future_or_invalid_version_is_error(v):
    r = ReBAC()
    r.write(add=[("doc:1", "viewer", ALICE)])
    r.write(add=[("doc:2", "viewer", ALICE)])
    r.write(add=[("doc:3", "viewer", ALICE)])
    with pytest.raises(ValueError):
        r.check(ALICE, "viewer", "doc:1", at_version=v)
    with pytest.raises(ValueError):
        r.list_objects(ALICE, "viewer", "doc", at_version=v)
    with pytest.raises(ValueError):
        r.tuples(at_version=v)


def test_returned_tuples_do_not_expose_internal_state():
    r = make([("doc:1", "viewer", ALICE)])
    r.tuples().append(("doc:9", "owner", EVE))
    assert r.tuples() == [("doc:1", "viewer", ALICE)]
    assert not allowed(r, EVE, "owner", "doc:9")


# --- list_objects ------------------------------------------------------------------------------

def build_world():
    return make([
        ("doc:1", "parent", "folder:a"), ("doc:2", "parent", "folder:a"), ("doc:3", "parent", "folder:b"),
        ("doc:4", "owner", ALICE), ("folder:a", "viewer", "group:eng#member"), ("group:eng", "member", ALICE),
        ("folder:b", "editor", BOB), ("doc:5", "viewer", BOB),
    ])


def test_list_objects_sorted_and_by_relation():
    r = build_world()
    assert r.list_objects(ALICE, "viewer", "doc") == ["doc:1", "doc:2", "doc:4"]
    assert r.list_objects(ALICE, "editor", "doc") == ["doc:4"]
    assert r.list_objects(ALICE, "owner", "doc") == ["doc:4"]
    assert r.list_objects(BOB, "viewer", "doc") == ["doc:3", "doc:5"]
    assert r.list_objects(BOB, "editor", "doc") == ["doc:3"]
    assert r.list_objects(EVE, "viewer", "doc") == []


def test_list_objects_by_type_and_consistent_with_check():
    r = build_world()
    assert r.list_objects(ALICE, "viewer", "folder") == ["folder:a"]
    assert r.list_objects(BOB, "viewer", "folder") == ["folder:b"]
    assert r.list_objects(ALICE, "member", "group") == ["group:eng"]
    for user in (ALICE, BOB, EVE):
        for rel in ("owner", "editor", "viewer"):
            expected = sorted(f"doc:{i}" for i in range(1, 6) if allowed(r, user, rel, f"doc:{i}"))
            assert r.list_objects(user, rel, "doc") == expected


def test_list_objects_follows_revocation_snapshots_and_depth():
    r = build_world()
    r.write(remove=[("group:eng", "member", ALICE)])
    assert r.list_objects(ALICE, "viewer", "doc") == ["doc:4"]
    assert r.list_objects(ALICE, "viewer", "doc", at_version=r.version - 1) == ["doc:1", "doc:2", "doc:4"]
    deep = make(chain(5), max_depth=5)
    assert deep.list_objects(ALICE, "viewer", "doc") == []


def test_list_objects_includes_folders_known_only_as_parents():
    r = make([("doc:1", "parent", "folder:a"), ("folder:a", "viewer", ALICE)])
    assert r.list_objects(ALICE, "viewer", "folder") == ["folder:a"]


def test_list_objects_terminates_on_cycles():
    r = make([("folder:a", "parent", "folder:b"), ("folder:b", "parent", "folder:a"), ("folder:a", "viewer", ALICE)])
    assert bounded(r.list_objects, ALICE, "viewer", "folder") == ["folder:a", "folder:b"]


def test_explanations_are_real_tuples_for_all_allowed_checks():
    r = build_world()
    for user in (ALICE, BOB):
        for rel in ("viewer", "editor"):
            for obj in r.list_objects(user, rel, "doc"):
                assert_path_is_valid(r, r.check(user, rel, obj), user)
