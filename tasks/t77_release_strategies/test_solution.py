import pytest

from solution import simulate_release


def always_bad(share):
    return 0.5


def always_good(share):
    return 0.001


def breaks_under_load(limit):
    """Ламається лише коли нова версія бере на себе не менше за `limit` трафіку."""
    return lambda share: 0.4 if share >= limit else 0.001


class Spy:
    def __init__(self, fn):
        self.fn, self.calls = fn, []

    def __call__(self, share):
        self.calls.append(share)
        return self.fn(share)


# ---------- canary ------------------------------------------------------------


def test_canary_healthy_release_is_promoted_step_by_step():
    result = simulate_release("canary", health=always_good)
    assert result["status"] == "promoted" and result["exposure"] == 1.0
    assert [(s["action"], s["traffic_new"]) for s in result["log"]] == [("shift", 0.05), ("shift", 0.25), ("shift", 0.5), ("shift", 1.0)]
    assert all(s["error_rate"] == 0.001 for s in result["log"])


def test_canary_broken_release_hurts_only_the_first_step():
    result = simulate_release("canary", health=always_bad)
    assert result["status"] == "rolled_back" and result["exposure"] == 0.05
    assert result["log"] == [
        {"action": "shift", "traffic_new": 0.05, "error_rate": 0.5},
        {"action": "rollback", "traffic_new": 0.0},
    ]


def test_canary_catches_load_dependent_bug_at_the_step_where_it_appears_and_stops():
    spy = Spy(breaks_under_load(0.5))
    result = simulate_release("canary", health=spy)
    assert result["status"] == "rolled_back" and result["exposure"] == 0.5
    assert spy.calls == [0.05, 0.25, 0.5], "після провалу далі не йдемо"


def test_canary_custom_steps_and_threshold():
    result = simulate_release("canary", health=lambda s: 0.08, threshold=0.1, canary_steps=[10, 100])
    assert result["status"] == "promoted" and [s["traffic_new"] for s in result["log"]] == [0.1, 1.0]
    strict = simulate_release("canary", health=lambda s: 0.08, threshold=0.05, canary_steps=[10, 100])
    assert strict["status"] == "rolled_back" and strict["exposure"] == 0.1


def test_threshold_is_strict():
    assert simulate_release("canary", health=lambda s: 0.05)["status"] == "promoted"
    assert simulate_release("canary", health=lambda s: 0.0500001)["status"] == "rolled_back"


# ---------- rolling -----------------------------------------------------------


def test_rolling_healthy():
    result = simulate_release("rolling", health=always_good, replicas=4)
    assert result["status"] == "promoted" and result["exposure"] == 1.0
    assert [(s["action"], s["new_pods"], s["traffic_new"]) for s in result["log"]] == [
        ("replace", 1, 0.25), ("replace", 2, 0.5), ("replace", 3, 0.75), ("replace", 4, 1.0)]


def test_rolling_broken_release_is_caught_after_first_pod():
    result = simulate_release("rolling", health=always_bad, replicas=10)
    assert result["status"] == "rolled_back" and result["exposure"] == 0.1
    assert result["log"][-1] == {"action": "rollback", "traffic_new": 0.0}
    assert len(result["log"]) == 2


def test_rolling_load_dependent_bug():
    result = simulate_release("rolling", health=breaks_under_load(0.5), replicas=10)
    assert result["status"] == "rolled_back" and result["exposure"] == 0.5
    assert [s["new_pods"] for s in result["log"] if s["action"] == "replace"] == [1, 2, 3, 4, 5]


def test_rolling_single_replica():
    assert simulate_release("rolling", health=always_good, replicas=1)["log"] == [
        {"action": "replace", "new_pods": 1, "traffic_new": 1.0, "error_rate": 0.001}]


# ---------- blue-green --------------------------------------------------------


def test_blue_green_healthy():
    result = simulate_release("blue_green", health=always_good)
    assert result == {
        "status": "promoted", "exposure": 1.0, "old_kept": True,
        "log": [
            {"action": "deploy_green", "traffic_new": 0.0},
            {"action": "smoke", "traffic_new": 0.0, "error_rate": 0.001},
            {"action": "switch", "traffic_new": 1.0, "error_rate": 0.001},
        ],
    }


def test_blue_green_smoke_test_rejects_before_any_user_sees_it():
    result = simulate_release("blue_green", health=always_bad)
    assert result["status"] == "rejected" and result["exposure"] == 0.0
    assert [s["action"] for s in result["log"]] == ["deploy_green", "smoke"]


def test_blue_green_load_dependent_bug_hits_everyone_but_rolls_back_instantly():
    result = simulate_release("blue_green", health=breaks_under_load(0.5))
    assert result["status"] == "rolled_back" and result["exposure"] == 1.0
    assert [s["action"] for s in result["log"]] == ["deploy_green", "smoke", "switch", "rollback"]
    assert result["log"][-1] == {"action": "rollback", "traffic_new": 0.0}


def test_only_blue_green_reports_old_kept():
    assert "old_kept" not in simulate_release("canary", health=always_good)
    assert "old_kept" not in simulate_release("rolling", health=always_good)
    assert simulate_release("blue_green", health=always_bad)["old_kept"] is True


# ---------- висновок: радіус ураження ----------------------------------------


def test_blast_radius_comparison_for_the_same_load_dependent_bug():
    bug = breaks_under_load(0.5)
    exposure = {s: simulate_release(s, health=bug)["exposure"] for s in ("canary", "rolling", "blue_green")}
    assert exposure == {"canary": 0.5, "rolling": 0.5, "blue_green": 1.0}


def test_blast_radius_for_always_broken_release():
    exposure = {s: simulate_release(s, health=always_bad)["exposure"] for s in ("canary", "rolling", "blue_green")}
    assert exposure == {"canary": 0.05, "rolling": 0.1, "blue_green": 0.0}


# ---------- валідація ---------------------------------------------------------


@pytest.mark.parametrize("kwargs", [
    {"strategy": "big-bang"},
    {"strategy": "rolling", "replicas": 0},
    {"strategy": "canary", "canary_steps": [10, 50]},
    {"strategy": "canary", "canary_steps": [50, 10, 100]},
    {"strategy": "canary", "canary_steps": [10, 10, 100]},
    {"strategy": "canary", "canary_steps": []},
])
def test_invalid_arguments(kwargs):
    strategy = kwargs.pop("strategy")
    with pytest.raises(ValueError):
        simulate_release(strategy, health=always_good, **kwargs)
