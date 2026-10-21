import random

import pytest

from solution import bootstrap_ci, min_sample_size, paired_bootstrap, regression_gate


def bern(seed, n, p):
    rng = random.Random(seed)
    return [1 if rng.random() < p else 0 for _ in range(n)]


def flipped(base, ones_to_zero=0, zeros_to_one=0):
    """Копія base, де задану кількість 1 стала 0 і навпаки (парні дані: той самий набір кейсів)."""
    cand = list(base)
    ones = [i for i, x in enumerate(base) if x == 1]
    zeros = [i for i, x in enumerate(base) if x == 0]
    for i in ones[:ones_to_zero]:
        cand[i] = 0
    for i in zeros[:zeros_to_one]:
        cand[i] = 1
    return cand


# --- bootstrap_ci ------------------------------------------------------------------------------

def test_ci_brackets_the_sample_mean_and_is_ordered():
    data = bern(1, 100, 0.7)
    low, high = bootstrap_ci(data)
    assert low <= sum(data) / len(data) <= high
    assert low < high


def test_ci_is_deterministic_for_the_same_seed_and_differs_across_seeds():
    data = bern(2, 80, 0.6)
    assert bootstrap_ci(data, seed=5) == bootstrap_ci(data, seed=5)
    assert bootstrap_ci(data, seed=5) != bootstrap_ci(data, seed=6)


def test_ci_does_not_use_global_random_state():
    data = bern(3, 60, 0.5)
    random.seed(1)
    a = bootstrap_ci(data, seed=9)
    random.seed(2)
    random.random()
    assert bootstrap_ci(data, seed=9) == a


def test_constant_data_gives_degenerate_interval():
    assert bootstrap_ci([1] * 50) == (1.0, 1.0)
    assert bootstrap_ci([0.25] * 10) == (0.25, 0.25)


def test_single_element():
    assert bootstrap_ci([0.5]) == (0.5, 0.5)


def test_width_matches_theory_for_95_percent():
    data = [1] * 70 + [0] * 30   # sd = 0.458, 2 * 1.96 * sd / 10 = 0.1795
    low, high = bootstrap_ci(data, n_resamples=10000, seed=1)
    assert 0.165 <= high - low <= 0.195


def test_confidence_level_scales_the_width():
    data = [1] * 70 + [0] * 30
    w = {c: (lambda r: r[1] - r[0])(bootstrap_ci(data, n_resamples=10000, confidence=c, seed=1)) for c in (0.8, 0.95, 0.99)}
    assert w[0.99] > w[0.95] > w[0.8]
    assert 0.22 <= w[0.99] <= 0.25          # 2 * 2.576 * 0.0458
    assert 0.11 <= w[0.8] <= 0.14           # 2 * 1.2816 * 0.0458


def test_more_data_gives_a_narrower_interval():
    small = [1] * 70 + [0] * 30
    big = small * 4
    ws = bootstrap_ci(small, n_resamples=4000, seed=1)
    wb = bootstrap_ci(big, n_resamples=4000, seed=1)
    ratio = (wb[1] - wb[0]) / (ws[1] - ws[0])
    assert 0.4 <= ratio <= 0.62             # ~ 1 / sqrt(4) = 0.5


def test_interval_covers_the_true_rate_most_of_the_time():
    covered = 0
    for i in range(40):
        low, high = bootstrap_ci(bern(500 + i, 100, 0.7), n_resamples=400, seed=i)
        covered += low <= 0.7 <= high
    assert covered >= 33   # номінально 95% (очікується ~38 із 40)


def test_works_for_ordinal_scores_and_tuples():
    low, high = bootstrap_ci((1, 2, 3, 4, 5, 5, 4, 3), seed=1)
    assert 1 <= low < high <= 5


def test_input_not_mutated():
    data = [3, 1, 2, 5, 4]
    copy = list(data)
    bootstrap_ci(data)
    assert data == copy


@pytest.mark.parametrize("kwargs", [{"n_resamples": 99}, {"n_resamples": 0}, {"n_resamples": 1000.0}, {"confidence": 0},
                                     {"confidence": 1}, {"confidence": 1.5}, {"confidence": -0.1}])
def test_ci_parameter_validation(kwargs):
    with pytest.raises(ValueError):
        bootstrap_ci([1, 0, 1], **kwargs)


@pytest.mark.parametrize("bad", [[], (), ["a", 1], [None], [1, None], "abc", None])
def test_ci_bad_scores(bad):
    with pytest.raises(ValueError):
        bootstrap_ci(bad)


# --- paired_bootstrap --------------------------------------------------------------------------

def test_mean_diff_is_candidate_minus_baseline_exactly():
    res = paired_bootstrap([1, 1, 0, 0], [1, 0, 0, 0])
    assert res["mean_diff"] == pytest.approx(-0.25)
    res = paired_bootstrap([0.5, 0.5], [1.0, 1.0])
    assert res["mean_diff"] == pytest.approx(0.5)


def test_identical_runs_have_zero_diff_and_degenerate_interval():
    data = bern(4, 100, 0.7)
    res = paired_bootstrap(data, list(data))
    assert res["mean_diff"] == 0 and res["ci"] == (0, 0) and res["p_worse"] == 0.0


def test_consistent_small_drop_is_detected_thanks_to_pairing():
    base = bern(7, 200, 0.7)
    cand = flipped(base, ones_to_zero=10)
    res = paired_bootstrap(base, cand, seed=3)
    low, high = res["ci"]
    assert res["mean_diff"] == pytest.approx(-0.05)
    assert high < 0 and low < high
    assert high - low < 0.1          # непарний bootstrap дав би ~0.18
    assert res["p_worse"] > 0.99


def test_improvement_has_positive_interval_and_low_p_worse():
    base = bern(8, 200, 0.6)
    cand = flipped(base, zeros_to_one=20)
    res = paired_bootstrap(base, cand, seed=3)
    assert res["mean_diff"] == pytest.approx(0.10)
    assert res["ci"][0] > 0 and res["p_worse"] < 0.01


def test_noise_interval_contains_zero():
    base = bern(9, 200, 0.7)
    cand = flipped(base, ones_to_zero=6, zeros_to_one=6)
    res = paired_bootstrap(base, cand, seed=3)
    assert res["mean_diff"] == 0
    assert res["ci"][0] < 0 < res["ci"][1]
    assert 0.2 < res["p_worse"] < 0.8


def test_paired_is_deterministic_and_seeded():
    base = bern(10, 100, 0.6)
    cand = flipped(base, ones_to_zero=8, zeros_to_one=3)
    assert paired_bootstrap(base, cand, seed=1) == paired_bootstrap(base, cand, seed=1)
    assert paired_bootstrap(base, cand, seed=1) != paired_bootstrap(base, cand, seed=2)


def test_paired_confidence_and_resamples_parameters_are_used():
    base = bern(11, 100, 0.6)
    cand = flipped(base, ones_to_zero=10, zeros_to_one=4)
    narrow = paired_bootstrap(base, cand, confidence=0.8, n_resamples=4000)["ci"]
    wide = paired_bootstrap(base, cand, confidence=0.99, n_resamples=4000)["ci"]
    assert wide[0] < narrow[0] and wide[1] > narrow[1]


@pytest.mark.parametrize("a, b", [([1, 0], [1]), ([], []), ([1], []), (["x"], [1])])
def test_paired_validation(a, b):
    with pytest.raises(ValueError):
        paired_bootstrap(a, b)


@pytest.mark.parametrize("kwargs", [{"n_resamples": 50}, {"confidence": 1.0}])
def test_paired_parameter_validation(kwargs):
    with pytest.raises(ValueError):
        paired_bootstrap([1, 0], [0, 1], **kwargs)


# --- min_sample_size ---------------------------------------------------------------------------

@pytest.mark.parametrize("margin, kwargs, expected", [
    (0.05, {}, 385),
    (0.1, {}, 97),
    (0.05, {"p": 0.9}, 139),
    (0.05, {"confidence": 0.99}, 664),
    (0.02, {}, 2401),
    (0.1, {"p": 0.5, "confidence": 0.9}, 68),
])
def test_min_sample_size_known_values(margin, kwargs, expected):
    assert min_sample_size(margin, **kwargs) == expected


def test_min_sample_size_properties():
    assert min_sample_size(0.03) > min_sample_size(0.05) > min_sample_size(0.1)
    assert min_sample_size(0.05, p=0.5) >= min_sample_size(0.05, p=0.8) >= min_sample_size(0.05, p=0.95)
    assert min_sample_size(0.05, p=0.2) == min_sample_size(0.05, p=0.8)
    assert isinstance(min_sample_size(0.05), int)


@pytest.mark.parametrize("args, kwargs", [((0,), {}), ((1,), {}), ((-0.1,), {}), ((1.5,), {}), ((0.05,), {"p": 0}),
                                           ((0.05,), {"p": 1}), ((0.05,), {"confidence": 1}), ((0.05,), {"confidence": 0})])
def test_min_sample_size_validation(args, kwargs):
    with pytest.raises(ValueError):
        min_sample_size(*args, **kwargs)


# --- regression_gate ---------------------------------------------------------------------------

def test_gate_is_inconclusive_on_tiny_sets_even_for_huge_drops():
    base = [1] * 10
    cand = [0] * 10
    res = regression_gate(base, cand)
    assert res == {"decision": "inconclusive", "reason": "too-few-cases", "mean_diff": None, "ci": None, "n": 10}


def test_gate_min_cases_boundary_and_parameter():
    base, cand = [1] * 29, [0] * 29
    assert regression_gate(base, cand)["decision"] == "inconclusive"
    base, cand = [1] * 30 + [0] * 2, [0] * 30 + [0] * 2
    assert regression_gate(base, cand)["decision"] == "fail"
    assert regression_gate([1] * 10, [0] * 10, min_cases=10)["decision"] == "fail"
    assert regression_gate([1] * 10, [0] * 10, min_cases=11)["decision"] == "inconclusive"


@pytest.mark.parametrize("seed", range(10))
def test_gate_does_not_fail_on_noise(seed):
    base = bern(100 + seed, 200, 0.7)
    cand = flipped(base, ones_to_zero=5, zeros_to_one=5)
    res = regression_gate(base, cand)
    assert res["decision"] == "pass" and res["reason"] == "no-significant-regression"
    assert res["mean_diff"] == 0 and res["n"] == 200


@pytest.mark.parametrize("seed", range(5))
def test_gate_tolerates_a_slightly_negative_but_noisy_difference(seed):
    base = bern(200 + seed, 200, 0.7)
    cand = flipped(base, ones_to_zero=6, zeros_to_one=4)   # -1 п.п., у межах шуму
    res = regression_gate(base, cand)
    assert res["decision"] == "pass"
    assert res["mean_diff"] == pytest.approx(-0.01)


@pytest.mark.parametrize("seed", range(10))
def test_gate_catches_a_real_15_point_drop(seed):
    base = bern(300 + seed, 200, 0.7)
    cand = flipped(base, ones_to_zero=30)
    res = regression_gate(base, cand)
    assert res["decision"] == "fail" and res["reason"] == "significant-regression"
    assert res["mean_diff"] == pytest.approx(-0.15)
    assert res["ci"][1] < 0


def test_gate_catches_a_small_but_consistent_drop_because_comparison_is_paired():
    base = bern(7, 200, 0.7)
    cand = flipped(base, ones_to_zero=10)       # -5 п.п. на тих самих кейсах
    assert regression_gate(base, cand)["decision"] == "fail"


def test_gate_passes_on_improvement():
    base = bern(12, 200, 0.6)
    res = regression_gate(base, flipped(base, zeros_to_one=25))
    assert res["decision"] == "pass" and res["mean_diff"] > 0.1


def test_gate_tolerance_allows_a_known_small_regression():
    base = bern(7, 200, 0.7)
    cand = flipped(base, ones_to_zero=10)       # -0.05, верхня межа CI близько -0.02
    assert regression_gate(base, cand, tolerance=0.0)["decision"] == "fail"
    assert regression_gate(base, cand, tolerance=0.1)["decision"] == "pass"


def test_gate_is_deterministic_and_reports_interval():
    base = bern(13, 150, 0.7)
    cand = flipped(base, ones_to_zero=12, zeros_to_one=2)
    a = regression_gate(base, cand, seed=4)
    assert a == regression_gate(base, cand, seed=4)
    assert a["ci"][0] < a["mean_diff"] < a["ci"][1]
    assert a["ci"] == paired_bootstrap(base, cand, seed=4)["ci"]


def test_gate_works_with_graded_scores():
    rng = random.Random(5)
    base = [rng.choice([3, 4, 5]) / 5 for _ in range(100)]
    cand = [max(0.0, x - 0.2) for x in base]
    assert regression_gate(base, cand)["decision"] == "fail"
    assert regression_gate(base, [x + 0.2 for x in base])["decision"] == "pass"


@pytest.mark.parametrize("kwargs, a, b", [({}, [1] * 40, [1] * 39), ({}, [], []), ({"tolerance": -0.01}, [1] * 40, [1] * 40),
                                          ({"min_cases": 0}, [1] * 40, [1] * 40)])
def test_gate_validation(kwargs, a, b):
    with pytest.raises(ValueError):
        regression_gate(a, b, **kwargs)
