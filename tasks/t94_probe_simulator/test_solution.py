import pytest

from solution import max_startup_seconds, simulate


def sim(probes, app=None, duration=100):
    return simulate(probes, app or {}, duration)


# ---------- без проб ----------

def test_no_probes_ready_immediately():
    assert sim({}) == {"restarts": 0, "restart_times": [], "first_ready_at": 0, "ready_at_end": True}


def test_no_probes_never_restarts_even_if_app_is_down():
    r = sim({}, {"ready_after": 500})
    assert r["restarts"] == 0 and r["first_ready_at"] == 0


# ---------- liveness ----------

def test_liveness_kills_slow_starting_app():
    probes = {"liveness": {"initial_delay": 5, "period": 5, "failure_threshold": 3}}
    r = sim(probes, {"ready_after": 30}, 100)
    assert r["restart_times"] == [15, 31, 47, 63, 79, 95]
    assert r["restarts"] == 6


def test_liveness_survives_when_app_fast_enough():
    probes = {"liveness": {"initial_delay": 5, "period": 5, "failure_threshold": 3}}
    r = sim(probes, {"ready_after": 15}, 100)
    assert r["restarts"] == 0


def test_liveness_one_second_too_slow():
    probes = {"liveness": {"initial_delay": 5, "period": 5, "failure_threshold": 3}}
    r = sim(probes, {"ready_after": 16}, 100)
    assert r["restart_times"][0] == 15


def test_liveness_kills_hanging_app():
    probes = {"liveness": {"period": 10, "failure_threshold": 3}}
    r = sim(probes, {"down": [(50, None)]}, 100)
    assert r["restart_times"] == [70]


def test_liveness_restarted_app_hangs_again():
    probes = {"liveness": {"period": 10, "failure_threshold": 3}}
    r = sim(probes, {"down": [(50, None)]}, 150)
    assert r["restart_times"] == [70, 141]


def test_liveness_success_resets_failure_counter():
    probes = {"liveness": {"period": 10, "failure_threshold": 3}}
    assert sim(probes, {"down": [(20, 40)]})["restarts"] == 0       # невдачі на 20 і 30
    assert sim(probes, {"down": [(20, 50)]}, 45)["restart_times"] == [40]  # невдачі на 20, 30, 40


def test_liveness_two_blips_do_not_add_up():
    probes = {"liveness": {"period": 10, "failure_threshold": 3}}
    assert sim(probes, {"down": [(20, 40), (50, 70)]})["restarts"] == 0


def test_liveness_threshold_one():
    probes = {"liveness": {"period": 10, "failure_threshold": 1}}
    assert sim(probes, {"down": [(25, 26)]})["restarts"] == 0   # між перевірками
    assert sim(probes, {"down": [(30, 31)]}, 35)["restart_times"] == [30]


def test_down_window_is_half_open():
    probes = {"liveness": {"period": 10, "failure_threshold": 1}}
    assert sim(probes, {"down": [(20, 30)]}, 25)["restarts"] == 1
    assert sim(probes, {"down": [(21, 30)]})["restarts"] == 0


def test_liveness_defaults():
    # period=10, failure_threshold=3, initial_delay=0: перевірки на 0, 10, 20
    r = sim({"liveness": {}}, {"ready_after": 1000}, 25)
    assert r["restart_times"] == [20]


def test_liveness_no_restart_before_first_probe():
    probes = {"liveness": {"initial_delay": 60, "period": 10, "failure_threshold": 1}}
    r = sim(probes, {"ready_after": 60}, 200)
    assert r["restarts"] == 0


def test_kill_moment_is_last_probe_not_end_of_period():
    probes = {"liveness": {"period": 7, "failure_threshold": 2}}
    r = sim(probes, {"ready_after": 1000}, 8)
    assert r["restart_times"] == [7]


def test_restart_gap_is_one_second():
    probes = {"liveness": {"period": 1, "failure_threshold": 1}}
    r = sim(probes, {"ready_after": 3}, 20)
    # age 0 (t=0) невдача -> kill t=0, новий контейнер age 0 у t=1, kill t=1, ...
    assert r["restart_times"] == list(range(0, 21))


# ---------- startup ----------

def test_startup_protects_slow_app():
    probes = {
        "startup": {"period": 5, "failure_threshold": 12},
        "liveness": {"period": 10, "failure_threshold": 3},
    }
    r = sim(probes, {"ready_after": 30}, 100)
    assert r["restarts"] == 0
    assert r["first_ready_at"] == 30
    assert r["ready_at_end"] is True


def test_startup_failure_kills_container():
    probes = {"startup": {"period": 10, "failure_threshold": 3}}
    r = sim(probes, {"ready_after": 100}, 100)
    assert r["restart_times"] == [20, 41, 62, 83]


def test_startup_blocks_liveness_until_passed():
    # liveness з порогом 1 убила б застосунок на 0, але startup ще не пройшов
    probes = {
        "startup": {"period": 5, "failure_threshold": 20},
        "liveness": {"period": 5, "failure_threshold": 1},
    }
    r = sim(probes, {"ready_after": 40}, 100)
    assert r["restarts"] == 0


def test_liveness_works_after_startup():
    probes = {
        "startup": {"period": 5, "failure_threshold": 20},
        "liveness": {"period": 10, "failure_threshold": 1},
    }
    r = sim(probes, {"ready_after": 0, "down": [(50, 51)]}, 100)
    assert r["restart_times"] == [50]


def test_startup_only_after_restart_runs_again():
    probes = {
        "startup": {"period": 5, "failure_threshold": 4},
        "liveness": {"period": 5, "failure_threshold": 1},
    }
    r = sim(probes, {"ready_after": 10, "down": [(40, None)]}, 120)
    # startup пройшов на 10; liveness перша перевірка на 15..., невдача на 40 -> kill 40
    assert r["restart_times"][0] == 40
    # після рестарту (age 0 у t=41) startup знову працює і liveness знову відкладено
    assert r["restart_times"][1] == 41 + 40


def test_startup_initial_delay():
    probes = {"startup": {"initial_delay": 10, "period": 10, "failure_threshold": 2}}
    r = sim(probes, {"ready_after": 50}, 40)
    assert r["restart_times"] == [20]


def test_startup_not_ready_before_pass_when_no_readiness():
    probes = {"startup": {"initial_delay": 30, "period": 5}}
    r = sim(probes, {"ready_after": 0}, 100)
    assert r["first_ready_at"] == 30


# ---------- readiness ----------

def test_readiness_success_threshold():
    probes = {"readiness": {"initial_delay": 10, "period": 5, "success_threshold": 2, "failure_threshold": 3}}
    r = sim(probes, {"ready_after": 20}, 60)
    assert r["first_ready_at"] == 25
    assert r["restarts"] == 0
    assert r["ready_at_end"] is True


def test_readiness_failures_make_pod_not_ready_without_restart():
    probes = {"readiness": {"initial_delay": 10, "period": 5, "success_threshold": 2, "failure_threshold": 3}}
    r = sim(probes, {"ready_after": 20, "down": [(40, None)]}, 60)
    assert r["restarts"] == 0
    assert r["first_ready_at"] == 25
    assert r["ready_at_end"] is False


def test_readiness_recovers_after_blip():
    probes = {"readiness": {"period": 10, "failure_threshold": 2, "success_threshold": 1}}
    r = sim(probes, {"down": [(30, 50)]}, 70)
    # невдачі на 30, 40 -> not ready на 40; успіх на 50 -> знову ready
    assert r["first_ready_at"] == 0
    assert r["ready_at_end"] is True
    assert sim(probes, {"down": [(30, 50)]}, 45)["ready_at_end"] is False
    assert sim(probes, {"down": [(30, 50)]}, 35)["ready_at_end"] is True


def test_readiness_failure_resets_success_streak():
    probes = {"readiness": {"period": 10, "success_threshold": 2, "failure_threshold": 5}}
    # успіхи: 0 ok(1), 10 fail(скидання), 20 ok(1), 30 ok(2) -> ready на 30
    r = sim(probes, {"down": [(10, 20)]}, 60)
    assert r["first_ready_at"] == 30


def test_readiness_success_resets_failure_streak():
    probes = {"readiness": {"period": 10, "success_threshold": 1, "failure_threshold": 3}}
    # ready на 0; невдачі 20,30, успіх 40 (скидання), невдачі 60,70: усього < 3 поспіль
    r = sim(probes, {"down": [(20, 40), (60, 80)]}, 90)
    assert r["ready_at_end"] is True
    # на 60 і 70 лише дві невдачі від останнього успіху, тож pod ще ready
    assert sim(probes, {"down": [(20, 40), (60, 80)]}, 75)["ready_at_end"] is True
    assert sim(probes, {"down": [(20, 40), (60, 90)]}, 85)["ready_at_end"] is False


def test_readiness_not_ready_at_start_with_initial_delay():
    probes = {"readiness": {"initial_delay": 30, "period": 10}}
    r = sim(probes, {}, 100)
    assert r["first_ready_at"] == 30


def test_readiness_never_ready():
    r = sim({"readiness": {"period": 10}}, {"ready_after": 1000}, 100)
    assert r["first_ready_at"] is None and r["ready_at_end"] is False


def test_readiness_waits_for_startup():
    probes = {
        "startup": {"period": 10, "failure_threshold": 10},
        "readiness": {"period": 10},
    }
    r = sim(probes, {"ready_after": 25}, 100)
    # startup пройшов на 30, readiness перший раз після цього: на 40
    assert r["first_ready_at"] == 40


def test_readiness_does_not_run_in_kill_moment():
    probes = {
        "liveness": {"period": 10, "failure_threshold": 1},
        "readiness": {"period": 10, "failure_threshold": 1},
    }
    r = sim(probes, {"down": [(20, 21)]}, 20)
    assert r["restart_times"] == [20]
    assert r["ready_at_end"] is False


def test_ready_state_reset_after_restart():
    probes = {
        "liveness": {"period": 10, "failure_threshold": 1},
        "readiness": {"period": 10, "initial_delay": 10},
    }
    r = sim(probes, {"down": [(30, 31)]}, 35)
    assert r["restart_times"] == [30]
    assert r["first_ready_at"] == 10
    assert r["ready_at_end"] is False


# ---------- валідація ----------

@pytest.mark.parametrize("probes", [
    {"healthz": {}},
    {"liveness": {"period": 0}},
    {"liveness": {"failure_threshold": 0}},
    {"readiness": {"success_threshold": 0}},
    {"liveness": {"initial_delay": -1}},
])
def test_invalid_probes(probes):
    with pytest.raises(ValueError):
        simulate(probes, {}, 10)


def test_invalid_app_and_duration():
    with pytest.raises(ValueError):
        simulate({}, {"ready_after": -1}, 10)
    with pytest.raises(ValueError):
        simulate({}, {}, -1)


def test_duration_zero():
    r = simulate({"readiness": {"period": 10}}, {}, 0)
    assert r["first_ready_at"] == 0


def test_inputs_not_mutated():
    probes = {"liveness": {"period": 5}}
    app = {"down": [(10, 20)]}
    b = (repr(probes), repr(app))
    simulate(probes, app, 50)
    assert (repr(probes), repr(app)) == b


# ---------- max_startup_seconds ----------

def test_max_startup_none_without_killers():
    assert max_startup_seconds({}) is None
    assert max_startup_seconds({"readiness": {"period": 5}}) is None


def test_max_startup_from_liveness():
    assert max_startup_seconds({"liveness": {"initial_delay": 5, "period": 5, "failure_threshold": 3}}) == 15


def test_max_startup_from_startup_wins():
    probes = {
        "startup": {"period": 5, "failure_threshold": 12},
        "liveness": {"initial_delay": 5, "period": 5, "failure_threshold": 3},
    }
    assert max_startup_seconds(probes) == 55


def test_max_startup_defaults():
    assert max_startup_seconds({"liveness": {}}) == 20


@pytest.mark.parametrize("probes", [
    {"liveness": {"initial_delay": 5, "period": 5, "failure_threshold": 3}},
    {"liveness": {"period": 7, "failure_threshold": 2}},
    {"liveness": {"initial_delay": 12, "period": 10, "failure_threshold": 1}},
    {"startup": {"initial_delay": 3, "period": 4, "failure_threshold": 6}, "liveness": {"period": 10, "failure_threshold": 1}},
    {"startup": {"period": 5, "failure_threshold": 30}, "liveness": {"period": 5}, "readiness": {"period": 5}},
])
def test_max_startup_matches_simulation(probes):
    budget = max_startup_seconds(probes)
    ok = simulate(probes, {"ready_after": budget}, budget + 300)
    assert ok["restarts"] == 0
    bad = simulate(probes, {"ready_after": budget + 1}, budget + 300)
    assert bad["restart_times"][0] == budget


def test_max_startup_validates():
    with pytest.raises(ValueError):
        max_startup_seconds({"liveness": {"period": 0}})
    with pytest.raises(ValueError):
        max_startup_seconds({"nope": {}})
