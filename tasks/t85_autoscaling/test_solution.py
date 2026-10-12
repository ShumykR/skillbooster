import math

import pytest

from solution import TargetTrackingScaler


def scaler(**kw):
    kw.setdefault("target", 50.0)
    kw.setdefault("min_capacity", 2)
    kw.setdefault("max_capacity", 20)
    return TargetTrackingScaler(**kw)


@pytest.mark.parametrize("kwargs", [
    {"target": 0}, {"target": -1}, {"min_capacity": -1}, {"min_capacity": 5, "max_capacity": 4},
])
def test_invalid_configuration(kwargs):
    with pytest.raises(ValueError):
        scaler(**kwargs)


# ---------- масштабування вгору ----------------------------------------------


def test_proportional_scale_out():
    assert scaler().evaluate(4, 100.0, 0) == 8
    assert scaler().evaluate(4, 75.0, 0) == 6
    assert scaler().evaluate(3, 51.0, 0) == 4, "ceil"


def test_scale_out_is_capped_by_max():
    assert scaler().evaluate(10, 500.0, 0) == 20


def test_at_max_nothing_changes_and_nothing_is_recorded():
    s = scaler()
    assert s.evaluate(20, 500.0, 0) == 20
    assert s.evaluate(10, 100.0, 1) == 20, "попереднє нічого не записало, cooldown не заважає"


def test_scale_out_cooldown_blocks_second_scale_out():
    s = scaler()
    assert s.evaluate(4, 100.0, 1000) == 8
    assert s.evaluate(8, 200.0, 1059) == 8
    assert s.evaluate(8, 100.0, 1060) == 16


def test_first_scale_out_is_never_blocked():
    assert scaler().evaluate(4, 100.0, 0) == 8


# ---------- масштабування вниз ------------------------------------------------


def test_scale_in_needs_clear_margin_below_target():
    s = scaler()
    assert s.evaluate(20, 46.0, 0) == 20, "raw = 19 < 20, але 46 >= 0.9 * 50: запас, лишаємо"
    assert s.evaluate(20, 45.0, 1) == 20, "рівно 0.9 * target ще не достатньо (потрібно строго менше)"
    assert s.evaluate(20, 44.9, 2) == 18


def test_scale_in_step_is_limited_to_a_quarter():
    s = scaler()
    assert s.evaluate(12, 10.0, 0) == 9, "raw=3, але не більше ніж -25% (12 // 4 = 3)"


def test_scale_in_step_is_at_least_one():
    s = scaler(min_capacity=1)
    assert s.evaluate(3, 5.0, 0) == 2


def test_scale_in_stops_at_min():
    s = scaler(min_capacity=5)
    assert s.evaluate(6, 1.0, 0) == 5
    assert s.evaluate(5, 1.0, 10_000) == 5


def test_scale_in_uses_raw_when_it_is_closer_than_the_step():
    s = scaler()
    assert s.evaluate(8, 40.0, 0) == 7, "raw = ceil(8 * 40 / 50) = 7; крок до 6 не потрібен"


def test_scale_in_cooldown_after_scale_in():
    s = scaler()
    assert s.evaluate(12, 10.0, 1000) == 9
    assert s.evaluate(9, 10.0, 1299) == 9
    assert s.evaluate(9, 10.0, 1300) == 7


def test_recent_scale_out_also_blocks_scale_in():
    s = scaler()
    assert s.evaluate(4, 100.0, 1000) == 8
    assert s.evaluate(8, 5.0, 1100) == 8, "після масштабування вгору вниз не йдемо весь scale_in_cooldown"
    assert s.evaluate(8, 5.0, 1300) == 6


def test_scale_out_after_scale_in_is_governed_by_out_cooldown_only():
    s = scaler()
    assert s.evaluate(12, 10.0, 1000) == 9
    assert s.evaluate(9, 100.0, 1001) == 18, "вгору не було раніше: охолодження вгору не діє"


def test_custom_cooldowns():
    s = scaler(scale_out_cooldown=10, scale_in_cooldown=20)
    assert s.evaluate(4, 100.0, 0) == 8
    assert s.evaluate(8, 100.0, 10) == 16
    assert s.evaluate(16, 5.0, 29) == 16
    assert s.evaluate(16, 5.0, 30) == 12


def test_exact_cooldown_boundaries_are_open():
    s = scaler()
    s.evaluate(4, 100.0, 0)
    assert s.evaluate(8, 100.0, 59.9) == 8
    assert s.evaluate(8, 100.0, 60.0) == 16


# ---------- межі і відсутність даних ------------------------------------------


def test_below_min_is_raised_immediately_ignoring_cooldowns_and_metric():
    s = scaler(min_capacity=3)
    assert s.evaluate(1, None, 0) == 3
    assert s.evaluate(2, 0.0, 1) == 3


def test_above_max_is_cut_immediately():
    s = scaler(max_capacity=10)
    assert s.evaluate(15, 100.0, 0) == 10
    assert s.evaluate(30, None, 1) == 10


def test_clamping_counts_as_scaling_activity():
    s = scaler(min_capacity=3)
    s.evaluate(1, None, 1000)  # піднято до min у момент 1000
    assert s.evaluate(5, 1.0, 1100) == 5, "щойно масштабувались вгору: вниз ще рано"
    assert s.evaluate(5, 1.0, 1300) == 4


@pytest.mark.parametrize("metric", [None, math.nan])
def test_no_data_holds_capacity(metric):
    assert scaler().evaluate(7, metric, 0) == 7


def test_zero_instances_and_zero_min():
    s = scaler(min_capacity=0)
    assert s.evaluate(0, 0.0, 0) == 0
    assert s.evaluate(0, 10.0, 1) == 1


def test_scale_in_to_zero_when_allowed():
    s = scaler(min_capacity=0)
    assert s.evaluate(1, 0.0, 0) == 0


def test_stable_metric_around_target_changes_nothing():
    s = scaler()
    for i, metric in enumerate([50.0, 49.0, 50.0, 48.0, 50.0]):
        assert s.evaluate(6, metric, i * 1000) == 6


def test_realistic_traffic_spike_and_calm_down():
    s = scaler()
    capacity, history = 4, []
    for t, metric in [(0, 50), (60, 120), (120, 120), (180, 90), (240, 60), (300, 30), (900, 30), (1500, 30), (2100, 30)]:
        capacity = s.evaluate(capacity, metric, t)
        history.append(capacity)
    assert history == [4, 10, 20, 20, 20, 20, 15, 12, 9]
