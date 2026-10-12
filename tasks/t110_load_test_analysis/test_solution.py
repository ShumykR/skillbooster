import pytest

from solution import check_thresholds, find_saturation, little_law, percentile, required_instances, summarize

TEN = list(range(1, 11))


@pytest.mark.parametrize("p, expected", [(10, 1), (50, 5), (51, 6), (90, 9), (95, 10), (99, 10), (100, 10)])
def test_percentile_nearest_rank(p, expected):
    assert percentile(TEN, p) == expected


def test_percentile_is_exact_at_rank_boundaries():
    values = list(range(1, 21))
    assert percentile(values, 95) == 19, "ceil(0.95 * 20) = 19 без похибки float"
    assert percentile(values, 99.5) == 20
    assert percentile(list(range(1, 101)), 95) == 95
    assert percentile([5], 1) == 5
    assert percentile(list(range(1, 26)), 28) == 7, "ceil(0.28 * 25) = 7, а float дає 8"
    assert percentile(list(range(1, 51)), 14) == 7


def test_percentile_sorts_and_does_not_mutate():
    data = [9, 1, 3, 7, 5]
    assert percentile(data, 50) == 5
    assert data == [9, 1, 3, 7, 5]


@pytest.mark.parametrize("values, p", [([], 50), ([1], 0), ([1], 101), ([1], -5)])
def test_percentile_validation(values, p):
    with pytest.raises(ValueError):
        percentile(values, p)


def samples(latencies, bad=()):
    return [{"latency": l, "ok": i not in bad} for i, l in enumerate(latencies)]


def test_summarize():
    s = summarize(samples([i / 100 for i in range(1, 101)], bad={0, 99}))
    assert s == {"count": 100, "errors": 2, "error_rate": 0.02, "p50": 0.5, "p95": 0.95, "p99": 0.99, "max": 1.0}


def test_summarize_includes_failed_requests_in_latency_and_rounds_rate():
    s = summarize(samples([0.1, 0.1, 5.0], bad={2}))
    assert s["max"] == 5.0 and s["error_rate"] == 0.3333 and s["errors"] == 1
    with pytest.raises(ValueError):
        summarize([])


def test_check_thresholds():
    summary = summarize(samples([i / 100 for i in range(1, 101)]))
    assert check_thresholds(summary, {"p95": 0.95, "error_rate": 0}) == {"passed": True, "failed": []}, "<= включно"
    assert check_thresholds(summary, {"p95": 0.9, "p99": 0.5, "error_rate": 0.0}) == {"passed": False, "failed": ["p95", "p99"]}
    assert check_thresholds(summary, {"p99": 0.5, "p95": 0.9})["failed"] == ["p95", "p99"], "відсортовано"
    assert check_thresholds(summary, {}) == {"passed": True, "failed": []}
    with pytest.raises(ValueError):
        check_thresholds(summary, {"p42": 1})


STEPS = [
    {"vus": 10, "rps": 100, "p95": 0.05, "error_rate": 0},
    {"vus": 20, "rps": 195, "p95": 0.06, "error_rate": 0},
    {"vus": 40, "rps": 380, "p95": 0.08, "error_rate": 0.001},
    {"vus": 80, "rps": 400, "p95": 0.2, "error_rate": 0.002},
    {"vus": 160, "rps": 390, "p95": 0.9, "error_rate": 0.05},
]


def test_errors_are_the_first_reason_to_fail():
    assert find_saturation(STEPS, p95_limit=0.5) == {"saturated_at": 160, "reason": "errors", "max_sustainable": 80, "peak_rps": 400}


def test_latency_limit():
    assert find_saturation(STEPS, p95_limit=0.15) == {"saturated_at": 80, "reason": "latency", "max_sustainable": 40, "peak_rps": 380}


def test_throughput_plateau():
    assert find_saturation(STEPS, p95_limit=0.5, gain_min=0.1) == {"saturated_at": 80, "reason": "plateau", "max_sustainable": 40, "peak_rps": 380}


def test_errors_beat_latency_and_latency_beats_plateau():
    step = [{"vus": 1, "rps": 100, "p95": 0.1, "error_rate": 0}, {"vus": 2, "rps": 100, "p95": 9, "error_rate": 0.5}]
    assert find_saturation(step, p95_limit=1)["reason"] == "errors"
    step[1]["error_rate"] = 0
    assert find_saturation(step, p95_limit=1)["reason"] == "latency"
    step[1]["p95"] = 0.2
    assert find_saturation(step, p95_limit=1)["reason"] == "plateau"


def test_limits_are_inclusive():
    steps = [{"vus": 1, "rps": 100, "p95": 0.5, "error_rate": 0.01}, {"vus": 2, "rps": 110, "p95": 0.5, "error_rate": 0.01}]
    result = find_saturation(steps, p95_limit=0.5, error_limit=0.01, gain_min=0.1)
    assert result == {"saturated_at": None, "reason": None, "max_sustainable": 2, "peak_rps": 110}


def test_first_step_can_already_be_bad():
    steps = [{"vus": 5, "rps": 50, "p95": 2, "error_rate": 0}]
    assert find_saturation(steps, p95_limit=1) == {"saturated_at": 5, "reason": "latency", "max_sustainable": None, "peak_rps": 0.0}


def test_healthy_system_never_saturates():
    steps = [{"vus": 10, "rps": 100, "p95": 0.05, "error_rate": 0}, {"vus": 20, "rps": 200, "p95": 0.06, "error_rate": 0}]
    assert find_saturation(steps, p95_limit=1) == {"saturated_at": None, "reason": None, "max_sustainable": 20, "peak_rps": 200}


def test_first_bad_step_wins_even_if_later_steps_recover():
    steps = [{"vus": 1, "rps": 100, "p95": 0.1, "error_rate": 0}, {"vus": 2, "rps": 200, "p95": 5, "error_rate": 0},
             {"vus": 3, "rps": 400, "p95": 0.1, "error_rate": 0}]
    assert find_saturation(steps, p95_limit=1)["saturated_at"] == 2


def test_zero_previous_throughput_is_not_a_plateau():
    steps = [{"vus": 1, "rps": 0, "p95": 0.1, "error_rate": 0}, {"vus": 2, "rps": 0, "p95": 0.1, "error_rate": 0}]
    assert find_saturation(steps, p95_limit=1)["reason"] is None


@pytest.mark.parametrize("steps", [[], [{"vus": 2, "rps": 1, "p95": 0, "error_rate": 0}, {"vus": 2, "rps": 1, "p95": 0, "error_rate": 0}],
                                   [{"vus": 3, "rps": 1, "p95": 0, "error_rate": 0}, {"vus": 2, "rps": 1, "p95": 0, "error_rate": 0}]])
def test_find_saturation_validation(steps):
    with pytest.raises(ValueError):
        find_saturation(steps, p95_limit=1)


def test_littles_law():
    assert little_law(200, 0.25) == 50
    assert little_law(0, 5) == 0


@pytest.mark.parametrize("target, per, headroom, expected", [
    (1000, 300, 0.3, 5), (630, 300, 0.3, 3), (631, 300, 0.3, 4), (0, 300, 0.3, 0), (100, 100, 0, 1), (101, 100, 0, 2), (100, 100, 0.5, 2), (42, 12, 0.3, 5), (84, 12, 0.3, 10)])
def test_required_instances(target, per, headroom, expected):
    assert required_instances(target, per, headroom) == expected


def test_required_instances_defaults_and_validation():
    assert required_instances(630, 300) == 3
    for args in ((-1, 10), (10, 0), (10, 10, 1), (10, 10, -0.1)):
        with pytest.raises(ValueError):
            required_instances(*args)
