import math
import random

import pytest

from solution import (best_threshold, confusion, expected_calibration_error, false_alarms_per_detection,
                      log_loss, platt_apply, platt_fit, precision_at_base_rate)


# --- base rate: precision --------------------------------------------------------------------

def test_precision_classic_example():
    # детектор 99% / 1% на трафіку з 0.1% атак: лише ~9% тривог справжні
    assert precision_at_base_rate(0.99, 0.01, 0.001) == pytest.approx(0.0902, abs=1e-4)


@pytest.mark.parametrize("rate, expected", [
    (0.5, 0.9794), (0.1, 0.8407), (0.01, 0.3242), (0.001, 0.0454), (0.0001, 0.0047),
])
def test_precision_table(rate, expected):
    assert precision_at_base_rate(0.95, 0.02, rate) == pytest.approx(expected, abs=1e-4)


def test_precision_grows_with_base_rate_and_with_tpr():
    values = [precision_at_base_rate(0.9, 0.05, r) for r in (0.001, 0.01, 0.1, 0.5, 0.9)]
    assert values == sorted(values) and len(set(values)) == 5
    assert precision_at_base_rate(0.95, 0.05, 0.01) > precision_at_base_rate(0.9, 0.05, 0.01)
    assert precision_at_base_rate(0.9, 0.01, 0.01) > precision_at_base_rate(0.9, 0.05, 0.01)


def test_precision_edge_cases():
    assert precision_at_base_rate(1.0, 0.0, 0.3) == 1.0
    assert precision_at_base_rate(0.9, 0.1, 0.0) == 0.0     # атак немає: усі тривоги хибні
    assert precision_at_base_rate(0.9, 0.1, 1.0) == 1.0     # самі атаки
    assert precision_at_base_rate(0.0, 0.0, 0.5) == 0.0     # нічого не спрацьовує
    assert precision_at_base_rate(0.5, 0.5, 0.5) == pytest.approx(0.5)


@pytest.mark.parametrize("args", [(1.1, 0.1, 0.1), (-0.1, 0.1, 0.1), (0.9, 1.5, 0.1), (0.9, 0.1, -0.01),
                                  (0.9, 0.1, 2), ("0.9", 0.1, 0.1), (True, 0.1, 0.1), (None, 0.1, 0.1)])
def test_probability_validation(args):
    with pytest.raises(ValueError):
        precision_at_base_rate(*args)
    with pytest.raises(ValueError):
        false_alarms_per_detection(*args)


def test_false_alarms_per_detection():
    assert false_alarms_per_detection(0.99, 0.01, 0.001) == pytest.approx(10.0909, abs=1e-4)
    assert false_alarms_per_detection(0.9, 0.05, 0.5) == pytest.approx(0.05 / 0.9)
    assert false_alarms_per_detection(0.9, 0.0, 0.1) == 0.0
    assert false_alarms_per_detection(0.0, 0.1, 0.1) == math.inf
    assert false_alarms_per_detection(0.0, 0.0, 0.1) == 0.0
    assert false_alarms_per_detection(0.9, 0.1, 0.0) == math.inf


def test_precision_and_false_alarms_are_consistent():
    for rate in (0.001, 0.02, 0.3):
        p = precision_at_base_rate(0.9, 0.04, rate)
        r = false_alarms_per_detection(0.9, 0.04, rate)
        assert p == pytest.approx(1 / (1 + r))


# --- confusion і поріг за вартістю ----------------------------------------------------------------

SCORES = [0.2, 0.4, 0.6, 0.8]
LABELS = [1, 0, 1, 0]


def test_confusion_counts_and_threshold_is_inclusive():
    assert confusion(SCORES, LABELS, 0.6) == {"tp": 1, "fp": 1, "tn": 1, "fn": 1}
    assert confusion(SCORES, LABELS, 0.2) == {"tp": 2, "fp": 2, "tn": 0, "fn": 0}
    assert confusion(SCORES, LABELS, math.inf) == {"tp": 0, "fp": 0, "tn": 2, "fn": 2}
    assert confusion(SCORES, LABELS, 0.61) == {"tp": 0, "fp": 1, "tn": 1, "fn": 2}
    assert confusion([0.5], [1], 0.5) == {"tp": 1, "fp": 0, "tn": 0, "fn": 0}


@pytest.mark.parametrize("scores, labels", [([], []), ([0.1], [1, 0]), ([0.1, 0.2], [1, 2]), ([0.1], [0.5]),
                                            ([0.1], ["1"]), ([0.1], [None])])
def test_confusion_validation(scores, labels):
    with pytest.raises(ValueError):
        confusion(scores, labels, 0.5)
    with pytest.raises(ValueError):
        best_threshold(scores, labels, 1, 1)


def test_best_threshold_separable_data():
    for costs in [(1, 1), (1, 10), (10, 1)]:
        assert best_threshold([0.1, 0.2, 0.8, 0.9], [0, 0, 1, 1], *costs) == 0.8


def test_best_threshold_depends_on_costs():
    assert best_threshold(SCORES, LABELS, 1, 10) == 0.2          # пропуск атаки дорогий: ловимо все
    assert best_threshold(SCORES, LABELS, 10, 1) == math.inf     # хибна тривога дорога: не блокуємо нічого


def test_best_threshold_tie_prefers_fewer_alerts():
    # при рівних витратах (2, 3, 2, 3, 2) обирається найвищий поріг
    assert best_threshold(SCORES, LABELS, 1, 1) == math.inf


def test_best_threshold_costs_are_weighted_exactly():
    # .2 → 2*cfp, .4 → 2*cfp+cfn, .6 → cfp+cfn, .8 → cfp+2*cfn, inf → 2*cfn
    for cfp, cfn in [(1, 1), (2, 3), (3, 2), (1, 5), (5, 1), (4, 4), (0.5, 0.7)]:
        costs = {0.2: 2 * cfp, 0.4: 2 * cfp + cfn, 0.6: cfp + cfn, 0.8: cfp + 2 * cfn, math.inf: 2 * cfn}
        low = min(costs.values())
        expected = max(t for t, c in costs.items() if c == low)
        assert best_threshold(SCORES, LABELS, cfp, cfn) == expected


def test_best_threshold_zero_costs_and_validation():
    assert best_threshold(SCORES, LABELS, 0, 0) == math.inf
    with pytest.raises(ValueError):
        best_threshold(SCORES, LABELS, -1, 1)
    with pytest.raises(ValueError):
        best_threshold(SCORES, LABELS, 1, -1)


def test_best_threshold_is_monotone_in_false_negative_cost():
    rng = random.Random(5)
    scores = [rng.random() for _ in range(200)]
    labels = [1 if rng.random() < s else 0 for s in scores]
    previous = math.inf
    for cfn in (0.1, 0.5, 1, 2, 5, 10, 50, 500):
        t = best_threshold(scores, labels, 1, cfn)
        assert t <= previous
        previous = t
    # пропуск атаки дорожчий за всі можливі хибні тривоги разом: ловимо кожну атаку
    assert best_threshold(scores, labels, 1, 500) == min(x for x, y in zip(scores, labels) if y)


def test_best_threshold_is_one_of_the_scores_or_infinity():
    rng = random.Random(1)
    scores = [round(rng.random(), 3) for _ in range(60)]
    labels = [rng.randint(0, 1) for _ in range(60)]
    t = best_threshold(scores, labels, 2, 3)
    assert t == math.inf or t in scores


# --- ECE -------------------------------------------------------------------------------------------

def test_ece_hand_computed():
    assert expected_calibration_error([0.1, 0.1, 0.9, 0.9], [0, 0, 1, 1]) == pytest.approx(0.1)
    assert expected_calibration_error([0.5, 0.5, 0.5, 0.5], [0, 1, 0, 1]) == pytest.approx(0.0)
    assert expected_calibration_error([1.0, 1.0], [0, 0]) == pytest.approx(1.0)
    assert expected_calibration_error([0.0, 0.0], [1, 1]) == pytest.approx(1.0)
    assert expected_calibration_error([0.8, 0.8, 0.8, 0.8, 0.8], [1, 1, 1, 1, 0]) == pytest.approx(0.0)


def test_ece_is_weighted_by_bin_size():
    # бін 0.9: 3 елементи (acc 1/3, conf 0.9 → 0.5667), бін 0.1: 1 елемент (acc 0, conf 0.1 → 0.1)
    probs = [0.9, 0.9, 0.9, 0.1]
    labels = [1, 0, 0, 0]
    expected = 3 / 4 * abs(1 / 3 - 0.9) + 1 / 4 * 0.1
    assert expected_calibration_error(probs, labels) == pytest.approx(expected)


def test_ece_bin_edges_and_custom_bins():
    # 0.1 за 10 бінів потрапляє в бін [0.1, 0.2), а 1.0 в останній бін
    probs = [0.09, 0.1, 1.0]
    labels = [0, 1, 1]
    # бін 0: conf .09 acc 0 → .09 (вага 1/3); бін 1: conf .1 acc 1 → .9 (1/3); бін 9: 0 (1/3)
    assert expected_calibration_error(probs, labels) == pytest.approx((0.09 + 0.9) / 3)
    # p == 1.0 належить останньому біну, а не першому
    assert expected_calibration_error([0.0, 1.0], [1, 0]) == pytest.approx(1.0)
    # 2 біни: [0, .5) і [.5, 1]
    assert expected_calibration_error([0.4, 0.6], [1, 0], bins=2) == pytest.approx(0.5 * 0.6 + 0.5 * 0.6)
    assert expected_calibration_error([0.4, 0.6], [1, 0], bins=1) == pytest.approx(abs(0.5 - 0.5))


@pytest.mark.parametrize("probs, labels, bins", [([], [], 10), ([0.5], [1, 0], 10), ([1.2], [1], 10), ([-0.1], [0], 10),
                                                  ([0.5], [1], 0), ([0.5], [1], 2.5), ([0.5], [2], 10)])
def test_ece_validation(probs, labels, bins):
    with pytest.raises(ValueError):
        expected_calibration_error(probs, labels, bins)


# --- Platt scaling ----------------------------------------------------------------------------------

def sigmoid(z):
    return 1 / (1 + math.exp(-z))


@pytest.fixture(scope="module")
def overconfident():
    rng = random.Random(0)
    scores = [rng.uniform(-6, 6) for _ in range(600)]
    labels = [1 if rng.random() < sigmoid(0.5 * x - 1) else 0 for x in scores]
    raw = [sigmoid(x) for x in scores]
    return scores, labels, raw


def test_platt_apply_values_and_stability():
    assert platt_apply([0.0], 1.0, 0.0) == [0.5]
    out = platt_apply([-2.0, 0.0, 3.0], 2.0, -1.0)
    assert out == pytest.approx([sigmoid(-5.0), sigmoid(-1.0), sigmoid(5.0)])
    extreme = platt_apply([1e4, -1e4], 1.0, 0.0)
    assert extreme == [1.0, 0.0]
    assert platt_apply([], 1.0, 0.0) == []


def test_platt_fit_recovers_the_generating_sigmoid(overconfident):
    scores, labels, _ = overconfident
    a, b = platt_fit(scores, labels)
    assert 0.3 < a < 0.7
    assert -1.3 < b < -0.6


def test_platt_fit_fixes_calibration(overconfident):
    scores, labels, raw = overconfident
    assert expected_calibration_error(raw, labels) > 0.1       # сирі впевненості хибні
    a, b = platt_fit(scores, labels)
    calibrated = platt_apply(scores, a, b)
    assert expected_calibration_error(calibrated, labels) < 0.07
    assert log_loss(calibrated, labels) < log_loss(raw, labels) - 0.1


def test_platt_keeps_the_ordering(overconfident):
    scores, labels, _ = overconfident
    a, b = platt_fit(scores, labels)
    assert a > 0
    ordered = sorted(scores)
    probs = platt_apply(ordered, a, b)
    assert probs == sorted(probs)


def test_platt_fit_handles_degenerate_labels_without_blowing_up():
    for labels in ([0, 0, 0, 0], [1, 1, 1, 1]):
        a, b = platt_fit([-1.0, 0.0, 1.0, 2.0], labels)
        assert math.isfinite(a) and math.isfinite(b)
        probs = platt_apply([-1.0, 2.0], a, b)
        assert all(0.0 <= p <= 1.0 for p in probs)
    a, b = platt_fit([-1.0, 0.0, 1.0, 2.0], [0, 0, 0, 0])
    assert platt_apply([0.0], a, b)[0] < 0.5


def test_platt_fit_does_not_mutate_inputs_and_is_deterministic(overconfident):
    scores, labels, _ = overconfident
    s2, l2 = list(scores), list(labels)
    first = platt_fit(scores, labels)
    assert (scores, labels) == (s2, l2)
    assert platt_fit(scores, labels) == first


def test_platt_fit_validation():
    with pytest.raises(ValueError):
        platt_fit([], [])
    with pytest.raises(ValueError):
        platt_fit([0.1, 0.2], [1])
    with pytest.raises(ValueError):
        platt_fit([0.1], [3])


# --- log_loss -----------------------------------------------------------------------------------------

def test_log_loss_values():
    assert log_loss([0.5, 0.5], [0, 1]) == pytest.approx(math.log(2))
    assert log_loss([0.9, 0.1], [1, 0]) == pytest.approx(-math.log(0.9))
    assert math.isfinite(log_loss([1.0, 0.0], [0, 1]))          # обрізання, а не log(0)
    assert log_loss([1.0, 0.0], [1, 0]) < 1e-9
    with pytest.raises(ValueError):
        log_loss([], [])
