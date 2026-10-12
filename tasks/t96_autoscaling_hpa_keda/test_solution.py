import pytest

from solution import hpa_desired, simulate_hpa, simulate_queue_scaler


# ---------- hpa_desired -------------------------------------------------------


@pytest.mark.parametrize("current, metric, target, expected", [
    (4, 90, 60, 6),       # 4 * 1.5
    (4, 100, 60, 7),      # 6.67 округлюємо вгору
    (3, 100, 50, 6),      # рівно 6: без зайвої репліки
    (10, 53, 60, 9),      # 8.83 -> 9
    (10, 25, 50, 5),
])
def test_formula_rounds_up(current, metric, target, expected):
    assert hpa_desired(current, metric, target) == expected


@pytest.mark.parametrize("metric, expected", [
    (66, 5),   # рівно межа зони нечутливості (10%): без змін
    (54, 5),   # те саме з іншого боку
    (67, 6),   # 5 * 67 / 60 = 5.58 -> 6
    (53, 5),   # 5 * 53 / 60 = 4.42 -> 5 (збіглось із current, але через формулу)
    (60, 5),
])
def test_tolerance_dead_zone_is_inclusive(metric, expected):
    assert hpa_desired(5, metric, 60) == expected


def test_dead_zone_blocks_the_formula_not_only_equal_results():
    assert hpa_desired(10, 65, 60, max_replicas=20) == 10, "65/60 = 1.083: усередині зони, хоча формула дала б 11"
    assert hpa_desired(10, 67, 60, max_replicas=20) == 12, "поза зоною: 10 * 67 / 60 = 11.17 -> 12"


def test_tolerance_is_configurable():
    assert hpa_desired(5, 61, 60, tolerance_pct=0) == 6
    assert hpa_desired(5, 90, 60, tolerance_pct=50) == 5
    assert hpa_desired(5, 91, 60, tolerance_pct=50) == 8


def test_result_is_clamped_to_bounds():
    assert hpa_desired(4, 600, 60) == 10
    assert hpa_desired(4, 600, 60, max_replicas=20) == 20
    assert hpa_desired(4, 6, 60) == 1
    assert hpa_desired(4, 6, 60, min_replicas=2) == 2


def test_clamp_applies_inside_dead_zone_too():
    assert hpa_desired(12, 60, 60, max_replicas=10) == 10
    assert hpa_desired(1, 60, 60, min_replicas=3) == 3


@pytest.mark.parametrize("args, kwargs", [
    ((0, 50, 50), {}),
    ((3, -1, 50), {}),
    ((3, 50, 0), {}),
    ((3, 50, 50), {"min_replicas": 0}),
    ((3, 50, 50), {"min_replicas": 5, "max_replicas": 4}),
    ((3, 50, 50), {"tolerance_pct": -1}),
])
def test_hpa_desired_validation(args, kwargs):
    with pytest.raises(ValueError):
        hpa_desired(*args, **kwargs)


# ---------- simulate_hpa ------------------------------------------------------


def test_scale_up_is_immediate_and_scale_down_waits_for_the_window():
    out = simulate_hpa([100, 100, 100, 25, 25, 25, 25, 25, 25], initial=2, target=50)
    # 2 -> 4 -> 8 -> 10 (max); вікно 300 с = 20 кроків, тож рекомендація 10 тримає репліки до кінця серії
    assert out[:3] == [4, 8, 10]
    assert out[3:] == [10] * 6, "300 с вікно ще тримає максимум"


def test_scale_down_after_window_with_short_window():
    out = simulate_hpa([100, 100, 100, 25, 25, 25, 25, 25, 25], initial=2, target=50, scale_down_window=45)
    # t=45: вікно [0..45] ще містить 10; t=90 (крок 6): вікно [45..90] має лише 5
    assert out == [4, 8, 10, 10, 10, 10, 5, 5, 5]


def test_window_boundary_is_inclusive():
    # період 15 с, вікно 30 с: рекомендація 4 з t=0 ще враховується у t=30, але не у t=45
    assert simulate_hpa([100, 25, 25, 25], initial=2, target=50, scale_down_window=30) == [4, 4, 4, 2]


def test_dead_zone_prevents_flapping():
    assert simulate_hpa([52, 48, 53, 47, 55, 45], initial=6, target=50) == [6] * 6


def test_no_scale_down_below_min_and_no_scale_up_above_max():
    out = simulate_hpa([1000, 1000], initial=3, target=50, max_replicas=6)
    assert out == [6, 6]
    out = simulate_hpa([0, 0, 0], initial=3, target=50, min_replicas=2, scale_down_window=0)
    assert out == [2, 2, 2]


def test_zero_window_scales_down_at_once():
    assert simulate_hpa([25, 25], initial=8, target=50, scale_down_window=0) == [4, 2]


def test_window_keeps_the_highest_recommendation_not_the_latest():
    out = simulate_hpa([100, 250, 25, 25, 25, 25], initial=2, target=50, scale_down_window=30, max_replicas=20)
    assert out == [4, 20, 20, 20, 10, 10]


def test_empty_metrics():
    assert simulate_hpa([], initial=3, target=50) == []


# ---------- simulate_queue_scaler --------------------------------------------

KW = dict(messages_per_replica=10, max_replicas=5, period=30, cooldown=90, scale_down_window=60)


def test_full_cycle_scale_up_hold_and_sleep():
    queue = [0, 25, 25, 100, 5, 5, 0, 0, 0, 0, 0]
    assert simulate_queue_scaler(queue, **KW) == [0, 3, 3, 5, 5, 5, 1, 1, 0, 0, 0]


@pytest.mark.parametrize("q, replicas", [(1, 1), (10, 1), (11, 2), (50, 5), (1000, 5)])
def test_replicas_follow_queue_length(q, replicas):
    assert simulate_queue_scaler([q], **KW) == [replicas]


def test_wakes_up_from_zero_immediately():
    assert simulate_queue_scaler([0, 0, 7], **KW) == [0, 0, 1]


def test_cooldown_boundary_is_exclusive_at_sleep():
    kw = dict(KW, scale_down_window=0)
    assert simulate_queue_scaler([10, 0, 0, 0, 0], **kw) == [1, 1, 1, 0, 0], "на 90-й секунді (= cooldown) вже засинаємо"


def test_going_to_zero_ignores_the_stabilization_window():
    out = simulate_queue_scaler([50, 0, 0, 0, 0], messages_per_replica=10, max_replicas=10, cooldown=90, scale_down_window=10_000)
    assert out == [5, 5, 5, 0, 0]


def test_min_replicas_keeps_workers_alive():
    kw = dict(KW, min_replicas=2)
    assert simulate_queue_scaler([0, 0], **kw) == [2, 2]
    assert simulate_queue_scaler([5, 0, 0, 0, 0, 0, 0], **kw)[-1] == 2
    assert simulate_queue_scaler([5], **kw) == [2], "навіть при малій черзі не нижче min"


def test_new_work_resets_the_cooldown():
    kw = dict(KW, scale_down_window=0)
    out = simulate_queue_scaler([10, 0, 0, 10, 0, 0, 0, 0], **kw)
    assert out == [1, 1, 1, 1, 1, 1, 0, 0]


def test_initial_replicas_without_work_go_to_zero_when_never_active():
    assert simulate_queue_scaler([0, 0], initial=3, **KW) == [0, 0]


@pytest.mark.parametrize("kwargs", [
    dict(messages_per_replica=0, max_replicas=3),
    dict(messages_per_replica=5, max_replicas=0),
    dict(messages_per_replica=5, max_replicas=3, min_replicas=-1),
    dict(messages_per_replica=5, max_replicas=3, min_replicas=4),
])
def test_queue_scaler_validation(kwargs):
    with pytest.raises(ValueError):
        simulate_queue_scaler([1], **kwargs)
