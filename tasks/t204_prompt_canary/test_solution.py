import hashlib

import pytest

from solution import CanaryController


def feed(c, variant, n, *, errors=0, cost=1.0, latency=100.0, quality=None):
    """n записів: перші `errors` невдалі; latency число або список; quality число або список."""
    for i in range(n):
        lat = latency[i % len(latency)] if isinstance(latency, list) else latency
        q = quality[i % len(quality)] if isinstance(quality, list) else quality
        c.record(variant, i >= errors, cost, lat, quality=q)


def healthy(c, n=20):
    feed(c, "stable", n, quality=0.8)
    feed(c, "canary", n, quality=0.8)


def bucket(salt, user):
    return int(hashlib.sha256(f"{salt}:{user}".encode()).hexdigest(), 16) % 100


# --- конструктор -------------------------------------------------------------------------------

def test_defaults():
    c = CanaryController("s")
    assert c.weight == 5 and c.state == "running"


def test_custom_steps_and_start_weight():
    assert CanaryController("s", steps=(10, 100)).weight == 10


@pytest.mark.parametrize("steps", [(), (5, 25), (25, 5, 100), (5, 5, 100), (0, 100), (5, 101, 100), (-1, 100)])
def test_invalid_steps(steps):
    with pytest.raises(ValueError):
        CanaryController("s", steps=steps)


@pytest.mark.parametrize("n", [0, -3])
def test_invalid_min_samples(n):
    with pytest.raises(ValueError):
        CanaryController("s", min_samples=n)


# --- assign ------------------------------------------------------------------------------------

def test_assign_follows_the_documented_formula():
    c = CanaryController("exp-1", steps=(30, 100))
    for u in range(300):
        expected = "canary" if bucket("exp-1", u) < 30 else "stable"
        assert c.assign(u) == expected


def test_assign_is_sticky_and_accepts_int_or_str():
    c = CanaryController("s", steps=(50, 100))
    first = [c.assign(f"user-{i}") for i in range(200)]
    assert first == [c.assign(f"user-{i}") for i in range(200)]
    assert c.assign(42) == c.assign("42")


@pytest.mark.parametrize("weight", [5, 25, 50])
def test_traffic_share_is_close_to_weight(weight):
    c = CanaryController("share", steps=(weight, 100))
    share = sum(c.assign(i) == "canary" for i in range(10000)) / 10000
    assert abs(share - weight / 100) < 0.015


def test_users_in_canary_stay_in_canary_when_weight_grows():
    c = CanaryController("grow", min_samples=1)
    users = range(3000)
    seen = []
    for _ in range(3):
        seen.append({u for u in users if c.assign(u) == "canary"})
        healthy(c, 1)
        assert c.step()["action"] == "promote"
    assert seen[0] < seen[1] < seen[2]


def test_different_salt_gives_different_assignment():
    a = CanaryController("exp-a", steps=(25, 100))
    b = CanaryController("exp-b", steps=(25, 100))
    sa = {u for u in range(4000) if a.assign(u) == "canary"}
    sb = {u for u in range(4000) if b.assign(u) == "canary"}
    assert sa != sb
    assert len(sa & sb) / len(sa) < 0.5


# --- evaluate: wait / promote ------------------------------------------------------------------

def test_wait_until_both_variants_have_min_samples():
    c = CanaryController("s")
    assert c.evaluate()["action"] == "wait"
    feed(c, "stable", 20)
    feed(c, "canary", 19)
    assert c.evaluate() == {"action": "wait", "reasons": [], "metrics": c.evaluate()["metrics"]}
    c.record("canary", True, 1.0, 100.0)
    assert c.evaluate()["action"] == "promote"


def test_wait_when_only_canary_is_ready():
    c = CanaryController("s")
    feed(c, "canary", 100)
    feed(c, "stable", 19)
    assert c.evaluate()["action"] == "wait"


def test_min_samples_is_configurable():
    c = CanaryController("s", min_samples=3)
    healthy(c, 3)
    assert c.evaluate()["action"] == "promote"


def test_promote_reports_metrics():
    c = CanaryController("s")
    feed(c, "stable", 20, errors=2, cost=2.0, latency=100.0, quality=[0.5, 0.7])
    feed(c, "canary", 25, errors=1, cost=1.0, latency=90.0, quality=0.7)
    d = c.evaluate()
    assert d["action"] == "promote" and d["reasons"] == []
    assert d["metrics"]["stable"] == {"n": 20, "error_rate": 0.1, "mean_cost": 2.0, "p95_latency": 100.0, "mean_quality": 0.6}
    assert d["metrics"]["canary"] == {"n": 25, "error_rate": 0.04, "mean_cost": 1.0, "p95_latency": 90.0, "mean_quality": 0.7}


def test_evaluate_does_not_change_state():
    c = CanaryController("s")
    feed(c, "stable", 30)
    feed(c, "canary", 30, errors=30)
    for _ in range(3):
        assert c.evaluate()["action"] == "rollback"
    assert c.weight == 5 and c.state == "running"


# --- пороги ------------------------------------------------------------------------------------

def test_error_rate_threshold_is_strict():
    c = CanaryController("s", min_samples=50)
    feed(c, "stable", 50)
    feed(c, "canary", 50, errors=1)  # різниця рівно 0.02
    assert c.evaluate()["action"] == "promote"
    c.record("canary", False, 1.0, 100.0)
    assert c.evaluate()["reasons"] == ["error-rate"]


def test_error_rate_improvement_is_not_a_violation():
    c = CanaryController("s")
    feed(c, "stable", 20, errors=10)
    feed(c, "canary", 20)
    assert c.evaluate()["action"] == "promote"


def test_quality_threshold_is_strict_and_uses_stable_minus_canary():
    c = CanaryController("s", thresholds={"max_quality_drop": 0.25})
    feed(c, "stable", 20, quality=1.0)
    feed(c, "canary", 20, quality=0.75)  # падіння рівно 0.25
    assert c.evaluate()["action"] == "promote"
    c2 = CanaryController("s", thresholds={"max_quality_drop": 0.25})
    feed(c2, "stable", 20, quality=1.0)
    feed(c2, "canary", 20, quality=0.7)
    assert c2.evaluate()["reasons"] == ["quality"]
    c3 = CanaryController("s")
    feed(c3, "stable", 20, quality=0.5)
    feed(c3, "canary", 20, quality=0.9)  # покращення
    assert c3.evaluate()["action"] == "promote"


def test_quality_ignored_when_one_side_has_none():
    c = CanaryController("s")
    feed(c, "stable", 20, quality=0.9)
    feed(c, "canary", 20)
    assert c.evaluate()["action"] == "promote"
    assert c.evaluate()["metrics"]["canary"]["mean_quality"] is None


def test_quality_mean_skips_missing_values():
    c = CanaryController("s")
    feed(c, "stable", 20, quality=[0.8, None])
    feed(c, "canary", 20, quality=[0.6, None, None, None])
    d = c.evaluate()
    assert d["metrics"]["stable"]["mean_quality"] == 0.8
    assert d["metrics"]["canary"]["mean_quality"] == 0.6
    assert d["reasons"] == ["quality"]


def test_cost_ratio_threshold_is_strict():
    c = CanaryController("s")
    feed(c, "stable", 20, cost=4.0)
    feed(c, "canary", 20, cost=5.0)  # рівно 1.25
    assert c.evaluate()["action"] == "promote"
    c.record("canary", True, 100.0, 100.0)
    assert c.evaluate()["reasons"] == ["cost"]


def test_cost_with_zero_stable_cost():
    free = CanaryController("s")
    feed(free, "stable", 20, cost=0.0)
    feed(free, "canary", 20, cost=0.0)
    assert free.evaluate()["action"] == "promote"
    paid = CanaryController("s")
    feed(paid, "stable", 20, cost=0.0)
    feed(paid, "canary", 20, cost=0.01)
    assert paid.evaluate()["reasons"] == ["cost"]


def test_latency_threshold_is_strict_on_p95():
    c = CanaryController("s")
    feed(c, "stable", 20, latency=100.0)
    feed(c, "canary", 20, latency=150.0)  # рівно 1.5
    assert c.evaluate()["action"] == "promote"
    c2 = CanaryController("s")
    feed(c2, "stable", 20, latency=100.0)
    feed(c2, "canary", 20, latency=151.0)
    assert c2.evaluate()["reasons"] == ["latency"]


def test_latency_uses_p95_not_mean_or_max():
    c = CanaryController("s")
    feed(c, "stable", 40, latency=100.0)
    # 40 запитів: p95 це елемент з індексом ceil(38) - 1 = 37, тобто третій з кінця
    feed(c, "canary", 40, latency=[100.0] * 39 + [100000.0])
    assert c.evaluate()["action"] == "promote"
    c2 = CanaryController("s")
    feed(c2, "stable", 40, latency=100.0)
    feed(c2, "canary", 40, latency=[100.0] * 37 + [1000.0] * 3)
    assert c2.evaluate()["reasons"] == ["latency"]


@pytest.mark.parametrize("n, expected", [(20, 19.0), (21, 20.0), (100, 95.0), (1, 1.0)])
def test_p95_is_nearest_rank(n, expected):
    c = CanaryController("s", min_samples=1)
    for i in range(n, 0, -1):  # у зворотному порядку: сортування обов'язкове
        c.record("canary", True, 1.0, float(i))
    c.record("stable", True, 1.0, 1.0)
    assert c.evaluate()["metrics"]["canary"]["p95_latency"] == expected


def test_zero_stable_latency():
    c = CanaryController("s")
    feed(c, "stable", 20, latency=0.0)
    feed(c, "canary", 20, latency=0.0)
    assert c.evaluate()["action"] == "promote"
    c2 = CanaryController("s")
    feed(c2, "stable", 20, latency=0.0)
    feed(c2, "canary", 20, latency=5.0)
    assert c2.evaluate()["reasons"] == ["latency"]


def test_all_reasons_in_fixed_order():
    c = CanaryController("s")
    feed(c, "stable", 20, cost=1.0, latency=100.0, quality=0.9)
    feed(c, "canary", 20, errors=10, cost=9.0, latency=900.0, quality=0.1)
    assert c.evaluate()["reasons"] == ["error-rate", "quality", "cost", "latency"]


def test_threshold_overrides_merge_with_defaults():
    c = CanaryController("s", thresholds={"max_cost_ratio": 3.0})
    feed(c, "stable", 20, cost=1.0)
    feed(c, "canary", 20, cost=2.5)
    assert c.evaluate()["action"] == "promote"  # кост у межах нового порогу
    feed(c, "canary", 20, errors=20)  # а типовий поріг помилок досі діє
    assert c.evaluate()["reasons"] == ["error-rate"]


# --- step --------------------------------------------------------------------------------------

def test_step_wait_changes_nothing():
    c = CanaryController("s")
    assert c.step() == {"action": "wait", "reasons": [], "weight": 5, "state": "running"}


def test_step_promotes_through_all_steps_and_resets_counters():
    c = CanaryController("s")
    expected = [(25, "running"), (50, "running"), (100, "promoted")]
    for weight, state in expected:
        healthy(c)
        r = c.step()
        assert r == {"action": "promote", "reasons": [], "weight": weight, "state": state}
        assert c.weight == weight and c.state == state
        if state == "running":
            assert c.evaluate()["action"] == "wait"  # лічильники обнулено


def test_old_data_does_not_leak_into_the_next_step():
    c = CanaryController("s", thresholds={"max_error_delta": 0.06})
    feed(c, "stable", 20)
    feed(c, "canary", 20, errors=1)
    assert c.step()["action"] == "promote"
    feed(c, "stable", 20)
    feed(c, "canary", 20)
    d = c.evaluate()
    assert d["metrics"]["canary"]["n"] == 20 and d["metrics"]["canary"]["error_rate"] == 0.0


def test_rollback_sets_zero_weight_and_everyone_goes_stable():
    c = CanaryController("s", steps=(50, 100))
    assert any(c.assign(u) == "canary" for u in range(100))
    feed(c, "stable", 20)
    feed(c, "canary", 20, errors=20)
    assert c.step() == {"action": "rollback", "reasons": ["error-rate"], "weight": 0, "state": "rolled_back"}
    assert c.weight == 0
    assert all(c.assign(u) == "stable" for u in range(2000))


def test_after_rollback_everything_is_frozen():
    c = CanaryController("s")
    feed(c, "stable", 20)
    feed(c, "canary", 20, errors=20)
    c.step()
    healthy(c, 100)  # записи ігноруються
    assert c.evaluate() == {"action": "done", "reasons": [], "metrics": c.evaluate()["metrics"]}
    assert c.step() == {"action": "done", "reasons": [], "weight": 0, "state": "rolled_back"}


def test_after_promoted_everything_is_frozen_and_all_traffic_is_canary():
    c = CanaryController("s", steps=(100,), min_samples=2)
    healthy(c, 2)
    assert c.step() == {"action": "promote", "reasons": [], "weight": 100, "state": "promoted"}
    assert all(c.assign(u) == "canary" for u in range(500))
    feed(c, "canary", 50, errors=50)
    assert c.step() == {"action": "done", "reasons": [], "weight": 100, "state": "promoted"}


# --- record ------------------------------------------------------------------------------------

@pytest.mark.parametrize("args", [
    ("beta", True, 1.0, 1.0), ("stable", True, -0.1, 1.0), ("stable", True, 1.0, -1.0), ("", True, 1.0, 1.0),
])
def test_record_rejects_bad_input(args):
    c = CanaryController("s")
    with pytest.raises(ValueError):
        c.record(*args)
    assert c.evaluate()["action"] == "wait"
