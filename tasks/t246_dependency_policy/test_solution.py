import copy
from datetime import datetime, timedelta, timezone

import pytest

from solution import check_lock, normalize_name

UTC = timezone.utc
NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


def H(c):
    return "sha256:" + c * 64


def iso(dt):
    return dt.isoformat()


OLD = iso(datetime(2026, 1, 2, tzinfo=UTC))


def rec(files, uploaded=OLD, yanked=False):
    return {"yanked": yanked, "uploaded": uploaded, "files": files}


SNAP = {
    "pypi": {
        "requests": {"2.32.3": rec({"requests-2.32.3-py3-none-any.whl": H("a"), "requests-2.32.3.tar.gz": H("b")})},
        "six": {"1.16.0": rec({"six-1.16.0-py2.py3-none-any.whl": H("c"), "six-1.16.0-py3-none-manylinux.whl": H("d")})},
        "fresh-lib": {"1.0.0": rec({"fresh_lib-1.0.0-py3-none-any.whl": H("e")}, iso(NOW - timedelta(days=3)))},
        "edge-ok": {"1.0.0": rec({"edge_ok-1.0.0-py3-none-any.whl": H("1")}, iso(NOW - timedelta(days=7)))},
        "edge-bad": {"1.0.0": rec({"edge_bad-1.0.0-py3-none-any.whl": H("2")},
                                  iso(NOW - timedelta(days=7) + timedelta(seconds=1)))},
        "future-lib": {"1.0.0": rec({"future_lib-1.0.0-py3-none-any.whl": H("3")}, iso(NOW + timedelta(hours=1)))},
        "old-yanked": {"0.9.0": rec({"old_yanked-0.9.0-py3-none-any.whl": H("f")}, yanked=True)},
        "acme-core": {"9.9.9": rec({"acme_core-9.9.9-py3-none-any.whl": H("9")})},  # клон зловмисника
        "acme-utils": {"9.9.9": rec({"acme_utils-9.9.9-py3-none-any.whl": H("8")})},
    },
    "internal": {
        "acme-core": {"1.4.0": rec({"acme_core-1.4.0-py3-none-any.whl": H("7")})},
        "acme-utils": {"2.0.0": rec({"acme_utils-2.0.0-py3-none-any.whl": H("6")})},
    },
}
POLICY = {"internal_names": ["acme-core"], "internal_prefixes": ["acme-"]}


def E(name, version, filename, hashes, index="pypi"):
    return {"name": name, "version": version, "index": index, "filename": filename, "hashes": hashes}


REQ = E("requests", "2.32.3", "requests-2.32.3-py3-none-any.whl", [H("a")])
SIX = E("six", "1.16.0", "six-1.16.0-py2.py3-none-any.whl", [H("c")])


def run(lock, policy=None, snap=None, now=NOW):
    return check_lock(lock, snap if snap is not None else SNAP, POLICY if policy is None else policy, now)


def rules(result):
    return [(v["package"], v["rule"]) for v in result]


# --- чистий lock і форма результату ------------------------------------------------------------

def test_clean_lock_passes():
    assert run([REQ, SIX]) == []
    assert run([]) == []


def test_normalize_name():
    assert normalize_name("Acme_Core.Utils--x") == "acme-core-utils-x"


def test_result_shape_reason_and_input_not_mutated():
    lock = [E("Requests", "2.32.3", "requests-2.32.3-py3-none-any.whl", [])]
    snap_before, lock_before = copy.deepcopy(SNAP), copy.deepcopy(lock)
    res = run(lock)
    assert [(v["package"], v["version"], v["rule"]) for v in res] == [("requests", "2.32.3", "missing-hash")]
    assert set(res[0]) == {"package", "version", "rule", "reason"}
    assert "requests" in res[0]["reason"] and "2.32.3" in res[0]["reason"]
    assert SNAP == snap_before and lock == lock_before


# --- dependency confusion ----------------------------------------------------------------------

def test_internal_name_from_public_index_is_confusion():
    lock = [E("acme-core", "9.9.9", "acme_core-9.9.9-py3-none-any.whl", [H("9")], index="pypi")]
    assert rules(run(lock)) == [("acme-core", "confusion")]


def test_internal_name_from_internal_index_is_fine():
    lock = [E("acme-core", "1.4.0", "acme_core-1.4.0-py3-none-any.whl", [H("7")], index="internal")]
    assert run(lock) == []


def test_internal_prefix_and_name_normalization():
    lock = [E("Acme_Utils", "9.9.9", "acme_utils-9.9.9-py3-none-any.whl", [H("8")])]
    assert rules(run(lock)) == [("acme-utils", "confusion")]
    lock = [E("ACME.Core", "9.9.9", "acme_core-9.9.9-py3-none-any.whl", [H("9")])]
    assert rules(run(lock, {"internal_names": ["Acme_Core"]})) == [("acme-core", "confusion")]


def test_prefix_must_match_at_start():
    lock = [E("not-acme-core", "1.0.0", "x-1.0.0-py3-none-any.whl", [H("a")])]
    res = run(lock)
    assert [v["rule"] for v in res] == ["not-in-index"]


# --- хеші --------------------------------------------------------------------------------------

@pytest.mark.parametrize("hashes", [[], None])
def test_missing_hashes(hashes):
    entry = dict(REQ, hashes=hashes)
    assert rules(run([entry])) == [("requests", "missing-hash")]


def test_missing_hashes_key_absent():
    entry = {k: v for k, v in REQ.items() if k != "hashes"}
    assert rules(run([entry])) == [("requests", "missing-hash")]


@pytest.mark.parametrize("bad", ["md5:" + "a" * 32, "sha256:" + "A" * 64, "sha256:" + "a" * 63, "a" * 64, "sha256:", ""])
def test_bad_hash_format(bad):
    entry = dict(REQ, hashes=[H("a"), bad])
    assert [v["rule"] for v in run([entry])] == ["bad-hash"]


def test_hash_mismatch():
    entry = dict(REQ, hashes=[H("0")])
    assert rules(run([entry])) == [("requests", "hash-mismatch")]


def test_extra_hashes_for_other_wheels_are_allowed():
    entry = dict(SIX, hashes=[H("d"), H("c")])
    assert run([entry]) == []
    entry = dict(SIX, hashes=[H("c"), H("0")])
    assert run([entry]) == []


def test_require_hashes_false_allows_missing_but_not_wrong():
    assert run([dict(REQ, hashes=[])], {"require_hashes": False}) == []
    assert rules(run([dict(REQ, hashes=[H("0")])], {"require_hashes": False})) == [("requests", "hash-mismatch")]


# --- wheels / yanked ---------------------------------------------------------------------------

def test_sdist_rejected_by_default_and_case_insensitive():
    entry = E("requests", "2.32.3", "requests-2.32.3.tar.gz", [H("b")])
    assert rules(run([entry])) == [("requests", "sdist")]
    snap = copy.deepcopy(SNAP)
    snap["pypi"]["requests"]["2.32.3"]["files"]["Requests-2.32.3-PY3-none-any.WHL"] = H("5")
    assert run([E("requests", "2.32.3", "Requests-2.32.3-PY3-none-any.WHL", [H("5")])], snap=snap) == []


def test_sdist_allowed_when_wheels_only_false():
    entry = E("requests", "2.32.3", "requests-2.32.3.tar.gz", [H("b")])
    assert run([entry], {"wheels_only": False}) == []


def test_yanked_version():
    entry = E("old-yanked", "0.9.0", "old_yanked-0.9.0-py3-none-any.whl", [H("f")])
    assert rules(run([entry])) == [("old-yanked", "yanked")]


# --- cooldown ----------------------------------------------------------------------------------

def test_cooldown_blocks_fresh_release():
    entry = E("fresh-lib", "1.0.0", "fresh_lib-1.0.0-py3-none-any.whl", [H("e")])
    res = run([entry])
    assert rules(res) == [("fresh-lib", "cooldown")]
    assert "3" in res[0]["reason"]


def test_cooldown_boundary_is_exclusive_of_exactly_n_days():
    ok = E("edge-ok", "1.0.0", "edge_ok-1.0.0-py3-none-any.whl", [H("1")])
    bad = E("edge-bad", "1.0.0", "edge_bad-1.0.0-py3-none-any.whl", [H("2")])
    assert run([ok]) == []
    assert rules(run([bad])) == [("edge-bad", "cooldown")]


def test_cooldown_configurable_exempt_and_disabled():
    entry = E("fresh-lib", "1.0.0", "fresh_lib-1.0.0-py3-none-any.whl", [H("e")])
    assert run([entry], {"cooldown_days": 2}) == []
    assert rules(run([entry], {"cooldown_days": 4})) == [("fresh-lib", "cooldown")]
    assert run([entry], {"cooldown_days": 0}) == []
    assert run([entry], {"cooldown_exempt": ["Fresh_Lib"]}) == []


def test_upload_time_in_future_is_a_violation():
    entry = E("future-lib", "1.0.0", "future_lib-1.0.0-py3-none-any.whl", [H("3")])
    assert rules(run([entry])) == [("future-lib", "cooldown")]


def test_cooldown_uses_timezone_aware_arithmetic():
    plus3 = timezone(timedelta(hours=3))
    snap = copy.deepcopy(SNAP)
    # 2026-10-14 14:30+03:00 це 11:30 UTC, тобто 7 днів і 30 хвилин до NOW
    snap["pypi"]["edge-ok"]["1.0.0"]["uploaded"] = datetime(2026, 10, 14, 14, 30, tzinfo=plus3).isoformat()
    entry = E("edge-ok", "1.0.0", "edge_ok-1.0.0-py3-none-any.whl", [H("1")])
    assert run([entry], snap=snap) == []
    snap["pypi"]["edge-ok"]["1.0.0"]["uploaded"] = datetime(2026, 10, 14, 15, 30, tzinfo=plus3).isoformat()
    assert rules(run([entry], snap=snap)) == [("edge-ok", "cooldown")]
    now_plus3 = NOW.astimezone(plus3)
    assert rules(run([entry], snap=snap, now=now_plus3)) == [("edge-ok", "cooldown")]


# --- not-in-index ------------------------------------------------------------------------------

@pytest.mark.parametrize("entry", [
    E("requests", "9.9.9", "requests-9.9.9-py3-none-any.whl", [H("a")]),
    E("nonexistent", "1.0", "nonexistent-1.0-py3-none-any.whl", [H("a")]),
    E("requests", "2.32.3", "requests-2.32.3-cp99-none-any.whl", [H("a")]),
    E("requests", "2.32.3", "requests-2.32.3-py3-none-any.whl", [H("a")], index="mirror"),
])
def test_not_in_index_and_nothing_else_that_depends_on_the_snapshot(entry):
    assert [v["rule"] for v in run([entry])] == ["not-in-index"]


def test_not_in_index_still_reports_lock_only_problems():
    entry = E("requests", "9.9.9", "requests-9.9.9.tar.gz", [])
    assert [v["rule"] for v in run([entry])] == ["missing-hash", "not-in-index", "sdist"]


# --- кілька порушень, порядок, дефолти ---------------------------------------------------------

def test_multiple_violations_sorted():
    lock = [
        E("fresh-lib", "1.0.0", "fresh_lib-1.0.0-py3-none-any.whl", [H("0")]),
        E("acme-core", "9.9.9", "acme_core-9.9.9-py3-none-any.whl", []),
        E("old-yanked", "0.9.0", "old_yanked-0.9.0-py3-none-any.whl", [H("f")]),
    ]
    assert rules(run(lock)) == [
        ("acme-core", "confusion"), ("acme-core", "missing-hash"),
        ("fresh-lib", "cooldown"), ("fresh-lib", "hash-mismatch"),
        ("old-yanked", "yanked"),
    ]


def test_sorted_by_version_within_package():
    snap = copy.deepcopy(SNAP)
    snap["pypi"]["requests"]["2.0.0"] = rec({"requests-2.0.0-py3-none-any.whl": H("4")}, yanked=True)
    lock = [E("requests", "2.32.3", "requests-2.32.3.tar.gz", [H("b")]),
            E("requests", "2.0.0", "requests-2.0.0-py3-none-any.whl", [H("4")])]
    res = run(lock, snap=snap)
    assert [(v["version"], v["rule"]) for v in res] == [("2.0.0", "yanked"), ("2.32.3", "sdist")]


def test_defaults_are_strict_with_empty_policy():
    entry = E("requests", "2.32.3", "requests-2.32.3.tar.gz", [])
    assert [v["rule"] for v in run([entry], {})] == ["missing-hash", "sdist"]
    fresh = E("fresh-lib", "1.0.0", "fresh_lib-1.0.0-py3-none-any.whl", [H("e")])
    assert [v["rule"] for v in run([fresh], {})] == ["cooldown"]


# --- некоректний вхід --------------------------------------------------------------------------

def test_naive_now_is_rejected():
    with pytest.raises(ValueError):
        run([REQ], now=datetime(2026, 10, 21, 12, 0))


@pytest.mark.parametrize("key", ["name", "version", "filename"])
def test_entry_without_required_field(key):
    entry = {k: v for k, v in REQ.items() if k != key}
    with pytest.raises(ValueError):
        run([entry])


def test_naive_uploaded_in_snapshot_is_rejected():
    snap = copy.deepcopy(SNAP)
    snap["pypi"]["requests"]["2.32.3"]["uploaded"] = "2026-01-02T00:00:00"
    with pytest.raises(ValueError):
        run([REQ], snap=snap)


def test_hash_of_another_file_does_not_vouch_for_this_one():
    entry = dict(SIX, hashes=[H("d")])  # хеш іншого wheel того ж релізу
    assert rules(run([entry])) == [("six", "hash-mismatch")]
