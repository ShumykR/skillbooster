import copy
import hashlib

import pytest

from solution import StranglerRouter, bucket, compare


def ref_bucket(key, salt=""):
    digest = hashlib.sha256(f"{salt}:{key}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % 100


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


class Service:
    """Підроблений сервіс: рахує виклики, пам'ятає запити, може падати чи мутувати запит."""

    def __init__(self, fn=None, fail=False, mutate=False):
        self.fn = fn or (lambda req: {"ok": True, "echo": req})
        self.fail = fail
        self.mutate = mutate
        self.calls = []

    def __call__(self, request):
        self.calls.append(copy.deepcopy(request))
        if self.mutate and isinstance(request, dict):
            request["touched"] = True
        if self.fail:
            raise RuntimeError("service down")
        return self.fn(request)


def key_in(percent, salt="", start=0, want=True):
    """Знаходить ключ, що (не) потрапляє у частку percent (обчисленням, а не вгадуванням)."""
    i = start
    while True:
        k = f"client-{i}"
        if (ref_bucket(k, salt) < percent) == want:
            return k
        i += 1


# --- bucket ------------------------------------------------------------------------------------

def test_bucket_matches_the_specified_formula():
    for key in ["a", "client-1", "користувач", "", "x" * 500]:
        for salt in ["", "route-1", "s"]:
            assert bucket(key, salt) == ref_bucket(key, salt)
    assert 0 <= min(bucket(f"k{i}") for i in range(300)) and max(bucket(f"k{i}") for i in range(300)) <= 99


def test_bucket_is_stable_and_salt_changes_assignment():
    assert bucket("user-42") == bucket("user-42")
    assert any(bucket(f"u{i}", "a") != bucket(f"u{i}", "b") for i in range(50))
    assert len({bucket(f"u{i}") for i in range(500)}) > 90


# --- compare -----------------------------------------------------------------------------------

def test_identical_and_different_structures():
    a = {"id": 1, "tags": ["x", "y"], "owner": {"name": "ann", "age": None}}
    assert compare(a, copy.deepcopy(a)) == []
    assert compare({"a": 1}, {"a": 2}) == ["$.a"]
    assert compare({"a": {"b": [1, 2, 3]}}, {"a": {"b": [1, 9, 3]}}) == ["$.a.b[1]"]
    assert compare([1, 2], [1, 2, 3]) == ["$"]
    assert compare("a", "b") == ["$"]
    assert compare(None, 0) == ["$"]


def test_missing_keys_and_type_differences_report_the_path():
    assert compare({"a": 1}, {"a": 1, "b": 2}) == ["$.b"]
    assert compare({"a": 1, "b": 2}, {"a": 1}) == ["$.b"]
    assert compare({"a": 1}, {"a": "1"}) == ["$.a"]
    assert compare({"a": [1]}, {"a": {"0": 1}}) == ["$.a"]
    assert compare({"a": None}, {}) == ["$.a"]


def test_diff_paths_are_sorted_and_complete():
    a = {"z": 1, "a": 1, "items": [{"p": 1}, {"p": 2}]}
    b = {"z": 2, "a": 2, "items": [{"p": 1}, {"p": 3}]}
    assert compare(a, b) == ["$.a", "$.items[1].p", "$.z"]


def test_numbers_bool_and_float_places():
    assert compare({"x": 1}, {"x": 1.0}) == []
    assert compare({"x": True}, {"x": 1}) == ["$.x"]
    assert compare({"x": False}, {"x": 0}) == ["$.x"]
    assert compare({"x": 0.1 + 0.2}, {"x": 0.3}) == ["$.x"]
    assert compare({"x": 0.1 + 0.2}, {"x": 0.3}, float_places=6) == []
    assert compare({"x": 1.0001}, {"x": 1.0002}, float_places=3) == []
    assert compare({"x": 1.001}, {"x": 1.002}, float_places=3) == ["$.x"]
    assert compare([0.1 + 0.2], [0.3], float_places=9) == []


def test_ignore_patterns():
    a = {"data": 1, "meta": {"request_id": "r1", "v": 1}, "items": [{"id": 1, "updated_at": "t1"}, {"id": 2, "updated_at": "t2"}]}
    b = {"data": 1, "meta": {"request_id": "r2", "v": 1}, "items": [{"id": 1, "updated_at": "t9"}, {"id": 2, "updated_at": "t8"}]}
    assert compare(a, b) == ["$.items[0].updated_at", "$.items[1].updated_at", "$.meta.request_id"]
    assert compare(a, b, ignore=["meta.request_id", "items.*.updated_at"]) == []
    assert compare(a, b, ignore=["meta.request_id"]) == ["$.items[0].updated_at", "$.items[1].updated_at"]
    assert compare(a, b, ignore=["items.0.updated_at", "meta.request_id"]) == ["$.items[1].updated_at"]
    assert compare(a, b, ignore=["meta"]) == ["$.items[0].updated_at", "$.items[1].updated_at"]
    assert compare(a, b, ignore=["*.request_id", "items.*.updated_at"]) == []


def test_ignore_applies_when_field_exists_on_one_side_only():
    assert compare({"a": 1, "trace": "x"}, {"a": 1}, ignore=["trace"]) == []
    assert compare({"a": 1}, {"a": 1, "meta": {"t": 1}}, ignore=["meta.t"]) == ["$.meta"]
    assert compare({"a": 1}, {"a": 1, "trace": 1}, ignore=["other"]) == ["$.trace"]


def test_ignore_pattern_depth_must_match():
    a, b = {"x": {"id": 1}}, {"x": {"id": 2}}
    assert compare(a, b, ignore=["id"]) == ["$.x.id"]
    assert compare(a, b, ignore=["x.id.deeper"]) == ["$.x.id"]
    assert compare(a, b, ignore=["x.id"]) == []


def test_unordered_lists_compare_as_multisets():
    a = {"tags": ["b", "a", "a"], "rows": [{"id": 1, "ts": 5}, {"id": 2, "ts": 6}]}
    b = {"tags": ["a", "b", "a"], "rows": [{"id": 2, "ts": 99}, {"id": 1, "ts": 98}]}
    assert compare(a, b) == ["$.rows[0].id", "$.rows[0].ts", "$.rows[1].id", "$.rows[1].ts", "$.tags[0]", "$.tags[1]"]
    assert compare(a, b, unordered=["tags"]) == ["$.rows[0].id", "$.rows[0].ts", "$.rows[1].id", "$.rows[1].ts"]
    assert compare(a, b, unordered=["tags", "rows"], ignore=["rows.*.ts"]) == []
    assert compare({"tags": ["a", "a", "b"]}, {"tags": ["a", "b", "b"]}, unordered=["tags"]) == ["$.tags"]
    assert compare({"tags": ["a"]}, {"tags": ["a", "a"]}, unordered=["tags"]) == ["$.tags"]


def test_unordered_with_float_places():
    assert compare({"v": [0.1 + 0.2, 1.0]}, {"v": [1.0, 0.3]}, unordered=["v"], float_places=6) == []


def test_compare_does_not_mutate_inputs():
    a = {"items": [{"id": 2, "ts": 1}, {"id": 1, "ts": 2}], "m": {"r": 1}}
    b = {"items": [{"id": 1, "ts": 9}, {"id": 2, "ts": 8}], "m": {"r": 2}}
    ca, cb = copy.deepcopy(a), copy.deepcopy(b)
    compare(a, b, ignore=["m.r", "items.*.ts"], unordered=["items"])
    assert (a, b) == (ca, cb)


# --- router: валідація й режими ------------------------------------------------------------------

@pytest.mark.parametrize("kw", [
    {"mode": "blue"}, {"percent": -1}, {"percent": 101}, {"percent": 5.5}, {"percent": True}, {"percent": "10"},
    {"window_seconds": 0}, {"window_seconds": -1}, {"min_samples": 0}, {"max_mismatch_ratio": -0.1},
    {"max_mismatch_ratio": 1.5}, {"min_samples": True},
])
def test_constructor_validation(kw):
    with pytest.raises(ValueError):
        StranglerRouter(Service(), Service(), **kw)


def test_set_mode_validation_keeps_state():
    r = StranglerRouter(Service(), Service(), mode="shadow", percent=40)
    for args in (("nope",), ("canary", 101), ("canary", -1), ("canary", 1.5), ("canary", True)):
        with pytest.raises(ValueError):
            r.set_mode(*args)
    assert (r.mode, r.percent) == ("shadow", 40) and r.events == []


def test_legacy_mode_calls_only_legacy():
    legacy, new = Service(), Service()
    r = StranglerRouter(legacy, new, mode="legacy", percent=100)
    assert r.handle("c1", {"q": 1}) == {"ok": True, "echo": {"q": 1}}
    assert len(legacy.calls) == 1 and new.calls == []
    assert r.stats()["served"] == {"legacy": 1, "new": 0}


def test_new_mode_calls_only_new_and_propagates_errors():
    legacy, new = Service(), Service(fn=lambda req: {"from": "new"})
    r = StranglerRouter(legacy, new, mode="new")
    assert r.handle("c", {}) == {"from": "new"}
    assert legacy.calls == [] and r.stats()["served"] == {"legacy": 0, "new": 1}
    broken = StranglerRouter(legacy, Service(fail=True), mode="new")
    with pytest.raises(RuntimeError):
        broken.handle("c", {})
    assert legacy.calls == []


def test_canary_share_is_exactly_the_bucket_rule():
    legacy = Service(fn=lambda req: {"from": "legacy"})
    new = Service(fn=lambda req: {"from": "new"})
    r = StranglerRouter(legacy, new, mode="canary", percent=30, salt="route-a")
    keys = [f"user-{i}" for i in range(2000)]
    for k in keys:
        expected = "new" if ref_bucket(k, "route-a") < 30 else "legacy"
        assert r.handle(k, {})["from"] == expected
    expected_new = sum(ref_bucket(k, "route-a") < 30 for k in keys)
    assert len(new.calls) == expected_new and len(legacy.calls) == 2000 - expected_new
    assert 450 <= expected_new <= 750
    assert r.stats()["served"] == {"legacy": 2000 - expected_new, "new": expected_new}


def test_canary_is_monotonic_and_deterministic():
    keys = [f"u{i}" for i in range(300)]
    seen = set()
    for p in (0, 10, 25, 60, 100):
        r = StranglerRouter(Service(fn=lambda q: "L"), Service(fn=lambda q: "N"), mode="canary", percent=p)
        now_new = {k for k in keys if r.handle(k, {}) == "N"}
        assert seen <= now_new
        seen = now_new
    assert len(seen) == 300
    r0 = StranglerRouter(Service(fn=lambda q: "L"), Service(fn=lambda q: "N"), mode="canary", percent=0)
    assert all(r0.handle(k, {}) == "L" for k in keys)


def test_same_client_always_gets_the_same_service():
    r = StranglerRouter(Service(fn=lambda q: "L"), Service(fn=lambda q: "N"), mode="canary", percent=50)
    for k in ("a", "b", "c", "d", "e"):
        assert len({r.handle(k, {}) for _ in range(5)}) == 1


def test_canary_new_error_falls_back_to_legacy_and_counts_as_bad():
    clock = Clock()
    legacy = Service(fn=lambda req: {"from": "legacy"})
    r = StranglerRouter(legacy, Service(fail=True), mode="canary", percent=100, clock=clock, min_samples=100)
    assert r.handle("c", {}) == {"from": "legacy"}
    s = r.stats()
    assert s["served"] == {"legacy": 1, "new": 0} and (s["samples"], s["bad_samples"]) == (1, 1)


def test_canary_request_copy_is_passed_to_new():
    new = Service(mutate=True)
    r = StranglerRouter(Service(), new, mode="canary", percent=100)
    request = {"a": 1}
    r.handle("k", request)
    assert request == {"a": 1}


# --- shadow --------------------------------------------------------------------------------------

def test_shadow_returns_legacy_and_calls_new_with_pristine_copy():
    legacy = Service(fn=lambda req: {"v": 1}, mutate=True)
    new = Service(fn=lambda req: {"v": 1})
    r = StranglerRouter(legacy, new, mode="shadow", percent=100)
    request = {"payload": [1, 2]}
    assert r.handle("c1", request) == {"v": 1}
    assert new.calls == [{"payload": [1, 2]}]  # legacy мутував запит, але new бачить оригінал
    assert request.get("touched") is True
    assert r.stats()["served"] == {"legacy": 1, "new": 0}


def test_shadow_response_never_comes_from_new_even_when_different():
    r = StranglerRouter(Service(fn=lambda q: {"v": "old"}), Service(fn=lambda q: {"v": "new"}), mode="shadow", percent=100)
    assert r.handle("c", {}) == {"v": "old"}
    assert r.mismatch_log == [{"key": "c", "paths": ["$.v"]}]


def test_shadow_percent_samples_by_bucket():
    new = Service()
    r = StranglerRouter(Service(), new, mode="shadow", percent=25, salt="x", min_samples=10 ** 6)
    keys = [f"user-{i}" for i in range(1000)]
    for k in keys:
        r.handle(k, {})
    assert len(new.calls) == sum(ref_bucket(k, "x") < 25 for k in keys)
    r0 = StranglerRouter(Service(), Service(), mode="shadow", percent=0)
    r0.handle("k", {})
    assert r0.stats()["samples"] == 0


def test_shadow_new_error_is_swallowed_and_logged():
    r = StranglerRouter(Service(fn=lambda q: "ok"), Service(fail=True), mode="shadow", percent=100, min_samples=100)
    assert r.handle("c", {}) == "ok"
    assert r.mismatch_log == [{"key": "c", "paths": ["<error>"]}]
    assert (r.stats()["samples"], r.stats()["bad_samples"]) == (1, 1)


def test_shadow_legacy_error_propagates_without_sample():
    new = Service()
    r = StranglerRouter(Service(fail=True), new, mode="shadow", percent=100)
    with pytest.raises(RuntimeError):
        r.handle("c", {})
    assert r.stats()["samples"] == 0 and new.calls == [] and r.stats()["served"] == {"legacy": 0, "new": 0}


def test_shadow_normalization_options_are_applied():
    legacy = Service(fn=lambda q: {"total": 0.1 + 0.2, "tags": ["a", "b"], "meta": {"rid": "1"}, "items": [{"id": 1}, {"id": 2}]})
    new = Service(fn=lambda q: {"total": 0.3, "tags": ["b", "a"], "meta": {"rid": "2"}, "items": [{"id": 2}, {"id": 1}]})
    strict = StranglerRouter(legacy, new, mode="shadow", percent=100, min_samples=100, float_places=None)
    strict.handle("c", {})
    assert strict.mismatch_log[0]["paths"] == ["$.items[0].id", "$.items[1].id", "$.meta.rid", "$.tags[0]", "$.tags[1]", "$.total"]
    tuned = StranglerRouter(legacy, new, mode="shadow", percent=100, min_samples=100, ignore=["meta.rid"],
                            unordered=["tags", "items"], float_places=6)
    tuned.handle("c", {})
    assert tuned.mismatch_log == [] and tuned.stats()["bad_samples"] == 0 and tuned.stats()["samples"] == 1


# --- автовідкат ---------------------------------------------------------------------------------

def make_shadow_router(clock, bad_for=lambda req: False, **kw):
    legacy = Service(fn=lambda req: {"v": 1})
    new = Service(fn=lambda req: {"v": 2 if bad_for(req) else 1})
    params = dict(mode="shadow", percent=100, clock=clock, min_samples=10, max_mismatch_ratio=0.2, window_seconds=60)
    params.update(kw)
    return StranglerRouter(legacy, new, **params), legacy, new


def test_no_rollback_below_min_samples_even_if_all_bad():
    clock = Clock()
    r, _, _ = make_shadow_router(clock, bad_for=lambda req: True)
    for i in range(9):
        r.handle(f"c{i}", {})
        clock.advance(1)
    assert r.mode == "shadow" and not r.rolled_back and r.events == []
    assert r.stats()["bad_samples"] == 9


def test_rollback_when_ratio_strictly_exceeds_threshold():
    clock = Clock()
    # 10 проб: 3 погані = 0.3 > 0.2
    r, legacy, new = make_shadow_router(clock, bad_for=lambda req: req["bad"])
    for i in range(10):
        r.handle(f"c{i}", {"bad": i in (0, 1, 2)})
        clock.advance(1)
    assert r.mode == "legacy" and r.percent == 0 and r.rolled_back is True
    assert len(r.events) == 1
    ev = r.events[0]
    assert ev["type"] == "rollback" and ev["samples"] == 10 and ev["ratio"] == pytest.approx(0.3) and ev["at"] == 1009.0


def test_exactly_at_threshold_does_not_roll_back():
    clock = Clock()
    r, _, _ = make_shadow_router(clock, bad_for=lambda req: req["bad"])  # 2 з 10 = 0.2
    for i in range(10):
        r.handle(f"c{i}", {"bad": i < 2})
        clock.advance(1)
    assert r.mode == "shadow" and not r.rolled_back
    assert r.stats()["ratio"] == pytest.approx(0.2)


def test_rollback_happens_after_the_request_is_served():
    clock = Clock()
    r, _, _ = make_shadow_router(clock, bad_for=lambda req: True, min_samples=1, max_mismatch_ratio=0.0)
    assert r.handle("c", {}) == {"v": 1}
    assert r.mode == "legacy"


def test_after_rollback_all_traffic_goes_to_legacy_only_and_no_new_samples():
    clock = Clock()
    r, legacy, new = make_shadow_router(clock, bad_for=lambda req: True, min_samples=3, max_mismatch_ratio=0.5)
    for i in range(3):
        r.handle(f"c{i}", {})
    assert r.rolled_back
    new_calls = len(new.calls)
    for i in range(20):
        assert r.handle(f"x{i}", {}) == {"v": 1}
    assert len(new.calls) == new_calls and r.stats()["samples"] == 0
    assert len(r.events) == 1


def test_old_samples_expire_from_the_window():
    clock = Clock()
    r, _, _ = make_shadow_router(clock, bad_for=lambda req: req["bad"], window_seconds=60, min_samples=5, max_mismatch_ratio=0.5)
    for i in range(4):
        r.handle(f"c{i}", {"bad": True})  # t=1000, 4 погані
    clock.advance(59)
    assert r.stats()["samples"] == 4
    clock.advance(1)  # now - t == 60: проба вже не в вікні
    assert r.stats()["samples"] == 0
    for i in range(4):
        r.handle(f"d{i}", {"bad": False})
    r.handle("e", {"bad": False})
    assert r.mode == "shadow" and not r.rolled_back  # застарілі погані проби не рахуються


def test_boundary_sample_just_inside_window_still_counts():
    clock = Clock()
    r, _, _ = make_shadow_router(clock, bad_for=lambda req: req["bad"], window_seconds=60, min_samples=5, max_mismatch_ratio=0.5)
    for i in range(4):
        r.handle(f"c{i}", {"bad": True})
    clock.advance(59.9)
    r.handle("last", {"bad": True})
    assert r.rolled_back and r.events[0]["samples"] == 5


def test_good_traffic_dilutes_old_bad_samples():
    clock = Clock()
    r, _, _ = make_shadow_router(clock, bad_for=lambda req: req["bad"], min_samples=10, max_mismatch_ratio=0.2)
    for i in range(2):
        r.handle(f"b{i}", {"bad": True})
    for i in range(30):
        r.handle(f"g{i}", {"bad": False})
        clock.advance(0.5)
    assert r.mode == "shadow" and not r.rolled_back


def test_canary_rollback_on_new_errors():
    clock = Clock()
    legacy = Service(fn=lambda q: "L")
    flaky = Service(fn=lambda q: "N")
    r = StranglerRouter(legacy, flaky, mode="canary", percent=100, clock=clock, min_samples=5, max_mismatch_ratio=0.3)
    for _ in range(3):
        assert r.handle("k", {}) == "N"
    flaky.fail = True
    results = [r.handle("k", {}) for _ in range(3)]
    assert results == ["L", "L", "L"]
    assert r.rolled_back and r.mode == "legacy"
    ev = r.events[0]
    assert ev["samples"] == 5 and ev["ratio"] == pytest.approx(0.4)
    assert r.handle("k", {}) == "L" and len(flaky.calls) == 5


def test_canary_good_traffic_never_rolls_back():
    r = StranglerRouter(Service(fn=lambda q: "L"), Service(fn=lambda q: "N"), mode="canary", percent=50,
                        min_samples=5, max_mismatch_ratio=0.0)
    for i in range(200):
        r.handle(f"u{i}", {})
    assert r.mode == "canary" and not r.rolled_back


# --- ручне керування й статистика ----------------------------------------------------------------

def test_set_mode_clears_window_rollback_flag_and_logs():
    clock = Clock()
    r, _, new = make_shadow_router(clock, bad_for=lambda req: True, min_samples=2, max_mismatch_ratio=0.1)
    r.handle("a", {})
    r.handle("b", {})
    assert r.rolled_back
    clock.advance(5)
    r.set_mode("shadow", 100)
    assert (r.mode, r.percent, r.rolled_back) == ("shadow", 100, False)
    assert r.stats()["samples"] == 0
    assert r.events[-1] == {"at": clock(), "type": "set_mode", "mode": "shadow", "percent": 100}
    r.set_mode("canary")
    assert (r.mode, r.percent) == ("canary", 100)
    assert r.events[-1] == {"at": clock(), "type": "set_mode", "mode": "canary", "percent": 100}


def test_promotion_flow_shadow_to_canary_to_new():
    clock = Clock()
    legacy = Service(fn=lambda q: {"v": 1})
    new = Service(fn=lambda q: {"v": 1, "extra": "x"})
    r = StranglerRouter(legacy, new, mode="shadow", percent=100, clock=clock, ignore=["extra"], min_samples=5)
    for i in range(20):
        r.handle(f"u{i}", {})
    assert r.mode == "shadow" and r.stats()["ratio"] == 0.0
    r.set_mode("canary", 20)
    out = [r.handle(f"u{i}", {}) for i in range(100)]
    assert sum("extra" in o for o in out) == sum(ref_bucket(f"u{i}") < 20 for i in range(100))
    r.set_mode("new")
    assert r.handle("u1", {}) == {"v": 1, "extra": "x"}


def test_stats_shape_on_fresh_router():
    r = StranglerRouter(Service(), Service())
    assert r.stats() == {"mode": "legacy", "percent": 0, "rolled_back": False, "served": {"legacy": 0, "new": 0},
                         "samples": 0, "bad_samples": 0, "ratio": 0.0}
    assert r.events == [] and r.mismatch_log == [] and r.rolled_back is False


def test_shadow_response_keeps_ignored_fields_of_legacy():
    legacy = Service(fn=lambda q: {"v": 1, "meta": "from-legacy"})
    new = Service(fn=lambda q: {"v": 1, "meta": "from-new"})
    r = StranglerRouter(legacy, new, mode="shadow", percent=100, ignore=["meta"])
    assert r.handle("c", {}) == {"v": 1, "meta": "from-legacy"}
    assert r.mismatch_log == []


def test_expired_bad_samples_are_pruned_before_the_rollback_decision():
    clock = Clock()
    r, _, _ = make_shadow_router(clock, bad_for=lambda req: req["bad"], window_seconds=60, min_samples=5, max_mismatch_ratio=0.3)
    for i in range(4):
        r.handle(f"b{i}", {"bad": True})
    clock.advance(60)
    for i in range(5):
        r.handle(f"g{i}", {"bad": False})
    assert r.mode == "shadow" and not r.rolled_back and r.events == []


def test_set_mode_clears_a_non_empty_window():
    clock = Clock()
    r, _, _ = make_shadow_router(clock, bad_for=lambda req: True, min_samples=50)
    for i in range(3):
        r.handle(f"c{i}", {})
    assert r.stats()["samples"] == 3
    r.set_mode("shadow", 100)
    assert r.stats()["samples"] == 0 and r.stats()["bad_samples"] == 0
