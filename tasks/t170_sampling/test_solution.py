import math
import random

import pytest

from solution import filter_top_k, filter_top_p, log_softmax, sample, softmax

LOGITS = [2.0, 1.0, 0.5, 0.0, -1.0]
N = 10_000


def ref_softmax(logits, t=1.0):
    exps = [math.exp(x / t) for x in logits]
    s = sum(exps)
    return [e / s for e in exps]


class FixedRng:
    """Підроблений генератор: повертає заготовлені u, інших методів немає."""

    def __init__(self, *values):
        self.values = list(values)
        self.calls = 0

    def random(self):
        self.calls += 1
        return self.values.pop(0) if self.values else 0.5


class CountingRng(random.Random):
    def __init__(self, seed):
        super().__init__(seed)
        self.calls = 0

    def random(self):
        self.calls += 1
        return super().random()


def freqs(n=N, seed=12345, **kw):
    rng = random.Random(seed)
    counts = [0] * len(LOGITS)
    for _ in range(n):
        counts[sample(LOGITS, rng, **kw)[0]] += 1
    return [c / n for c in counts]


# --- softmax / logprobs ------------------------------------------------------------------------

def test_softmax_matches_definition_and_sums_to_one():
    p = softmax(LOGITS)
    assert sum(p) == pytest.approx(1.0)
    assert p == pytest.approx(ref_softmax(LOGITS))
    assert p == sorted(p, reverse=True)


@pytest.mark.parametrize("t", [0.1, 0.5, 2.0, 10.0])
def test_temperature_scales_logits(t):
    assert softmax(LOGITS, t) == pytest.approx(ref_softmax(LOGITS, t))


def test_temperature_sharpens_and_flattens():
    assert softmax(LOGITS, 0.2)[0] > softmax(LOGITS, 1.0)[0] > softmax(LOGITS, 5.0)[0]
    assert max(softmax(LOGITS, 1000.0)) - min(softmax(LOGITS, 1000.0)) < 0.01


def test_softmax_is_numerically_stable():
    assert softmax([1000.0, 1000.0]) == pytest.approx([0.5, 0.5])
    assert softmax([-1000.0, -1001.0]) == pytest.approx(ref_softmax([0.0, -1.0]))
    assert softmax([1e4, 0.0]) == pytest.approx([1.0, 0.0])
    assert softmax([0.0, float("-inf"), 0.0]) == pytest.approx([0.5, 0.0, 0.5])


def test_logprobs_are_log_of_probabilities_and_stable():
    lp = log_softmax(LOGITS)
    assert lp == pytest.approx([math.log(p) for p in softmax(LOGITS)])
    assert log_softmax([1000.0, 1000.0]) == pytest.approx([math.log(0.5)] * 2)
    assert log_softmax([-1000.0, 0.0])[0] == pytest.approx(-1000.0, rel=1e-9)  # без underflow до -inf
    assert log_softmax([0.0, float("-inf")]) == [0.0, float("-inf")]
    assert log_softmax(LOGITS, 0.5) == pytest.approx([math.log(p) for p in softmax(LOGITS, 0.5)])


@pytest.mark.parametrize("bad", [[], [float("nan"), 1.0], [float("inf"), 1.0], [float("-inf")] * 3])
def test_invalid_logits_rejected(bad):
    for fn in (softmax, log_softmax):
        with pytest.raises(ValueError):
            fn(bad)
    with pytest.raises(ValueError):
        sample(bad, random.Random(1))


@pytest.mark.parametrize("t", [0, 0.0, -1.0, float("nan")])
def test_softmax_requires_positive_temperature(t):
    with pytest.raises(ValueError):
        softmax(LOGITS, t)
    with pytest.raises(ValueError):
        log_softmax(LOGITS, t)


# --- фільтри -----------------------------------------------------------------------------------

def test_top_k_keeps_largest_and_renormalizes():
    p = [0.5, 0.3, 0.15, 0.05]
    assert filter_top_k(p, 2) == pytest.approx([0.625, 0.375, 0.0, 0.0])
    assert filter_top_k(p, 1) == pytest.approx([1.0, 0.0, 0.0, 0.0])
    assert filter_top_k(p, 4) == pytest.approx(p)
    assert filter_top_k(p, 100) == pytest.approx(p)
    assert filter_top_k([0.05, 0.5, 0.15, 0.3], 2) == pytest.approx([0.0, 0.625, 0.0, 0.375])


def test_top_k_ties_are_resolved_by_lower_index():
    assert filter_top_k([0.25, 0.25, 0.25, 0.25], 2) == pytest.approx([0.5, 0.5, 0.0, 0.0])
    assert filter_top_k([0.1, 0.3, 0.3, 0.3], 2) == pytest.approx([0.0, 0.5, 0.5, 0.0])


@pytest.mark.parametrize("k", [0, -1, 1.5, "2", True, None])
def test_top_k_rejects_bad_k(k):
    with pytest.raises(ValueError):
        filter_top_k([0.5, 0.5], k)


def test_top_p_keeps_smallest_prefix_reaching_p():
    p = [0.5, 0.3, 0.15, 0.05]
    assert filter_top_p(p, 0.5) == pytest.approx([1.0, 0.0, 0.0, 0.0])      # накопичена сума рівно p
    assert filter_top_p(p, 0.51) == pytest.approx([0.625, 0.375, 0.0, 0.0])
    assert filter_top_p(p, 0.75) == pytest.approx([0.625, 0.375, 0.0, 0.0])
    assert filter_top_p(p, 0.9) == pytest.approx([0.5 / 0.95, 0.3 / 0.95, 0.15 / 0.95, 0.0])
    assert filter_top_p(p, 1.0) == pytest.approx(p)


def test_top_p_always_keeps_at_least_one_token_and_sorts_by_probability():
    assert filter_top_p([0.2, 0.7, 0.1], 0.01) == pytest.approx([0.0, 1.0, 0.0])
    assert filter_top_p([0.2, 0.7, 0.1], 0.8) == pytest.approx([0.2 / 0.9, 0.7 / 0.9, 0.0])


def test_top_p_ties_by_lower_index():
    assert filter_top_p([0.25, 0.25, 0.25, 0.25], 0.5) == pytest.approx([0.5, 0.5, 0.0, 0.0])


@pytest.mark.parametrize("p", [0, 0.0, -0.1, 1.01, float("nan")])
def test_top_p_rejects_bad_p(p):
    with pytest.raises(ValueError):
        filter_top_p([0.5, 0.5], p)


def test_filters_do_not_mutate_input():
    p = [0.5, 0.3, 0.2]
    filter_top_k(p, 1)
    filter_top_p(p, 0.5)
    assert p == [0.5, 0.3, 0.2]


# --- sample: точна детермінована поведінка -----------------------------------------------------

def test_inverse_cdf_with_exact_boundaries():
    logits = [0.0, 0.0]  # ймовірності 0.5 / 0.5
    assert sample(logits, FixedRng(0.0))[0] == 0
    assert sample(logits, FixedRng(0.49))[0] == 0
    assert sample(logits, FixedRng(0.5))[0] == 1  # u < накопичена сума: строго
    assert sample(logits, FixedRng(0.999999))[0] == 1


def test_one_random_call_per_sample_in_ascending_index_order():
    rng = FixedRng(0.1, 0.9)
    logits = [math.log(0.2), math.log(0.8)]
    assert sample(logits, rng)[0] == 0
    assert sample(logits, rng)[0] == 1
    assert rng.calls == 2


def test_returned_logprob_is_from_original_distribution():
    logits = [2.0, 1.0, 0.0]
    full = log_softmax(logits)
    idx, lp = sample(logits, FixedRng(0.0), temperature=0.3, top_k=1)
    assert idx == 0 and lp == pytest.approx(full[0])
    idx, lp = sample(logits, FixedRng(0.99), temperature=1.0)
    assert idx == 2 and lp == pytest.approx(full[2])


def test_top_k_is_applied_before_drawing_and_renormalized():
    logits = [math.log(0.5), math.log(0.3), math.log(0.2)]
    # після top_k=2: [0.625, 0.375]; u = 0.7 > 0.625 -> індекс 1 (без перенормування було б 0.7 < 0.8 -> 1 теж, тож беремо u = 0.99)
    assert sample(logits, FixedRng(0.62), top_k=2)[0] == 0
    assert sample(logits, FixedRng(0.63), top_k=2)[0] == 1
    assert sample(logits, FixedRng(0.9999), top_k=2)[0] == 1  # ніколи індекс 2


def test_top_p_then_draw_never_returns_filtered_token():
    logits = [math.log(0.5), math.log(0.3), math.log(0.15), math.log(0.05)]
    for u in (0.0, 0.3, 0.62, 0.63, 0.9999999):
        assert sample(logits, FixedRng(u), top_p=0.75)[0] in (0, 1)
    assert sample(logits, FixedRng(0.63), top_p=0.75)[0] == 1


def test_top_k_and_top_p_combined_in_that_order():
    logits = [math.log(0.4), math.log(0.3), math.log(0.2), math.log(0.1)]
    # top_k=3 -> [0.444, 0.333, 0.222, 0]; top_p=0.7 -> 0.444+0.333=0.777 >= 0.7: лишаються два
    for u in (0.0, 0.5, 0.9999):
        assert sample(logits, FixedRng(u), top_k=3, top_p=0.7)[0] in (0, 1)
    assert sample(logits, FixedRng(0.57), top_k=3, top_p=0.7)[0] == 0
    assert sample(logits, FixedRng(0.58), top_k=3, top_p=0.7)[0] == 1


def test_temperature_changes_the_draw():
    logits = [math.log(0.6), math.log(0.4)]
    assert sample(logits, FixedRng(0.7), temperature=1.0)[0] == 1
    assert sample(logits, FixedRng(0.7), temperature=0.3)[0] == 0  # ширший пік: P(0) ~ 0.79


def test_zero_probability_tokens_are_never_drawn():
    logits = [0.0, float("-inf"), 0.0]
    for u in (0.0, 0.49, 0.5, 0.9999999):
        assert sample(logits, FixedRng(u))[0] in (0, 2)
    assert sample(logits, FixedRng(0.5))[0] == 2


# --- greedy ------------------------------------------------------------------------------------

def test_temperature_zero_is_argmax_and_does_not_touch_rng():
    rng = FixedRng()
    assert sample([0.1, 3.0, 2.0], rng, temperature=0)[0] == 1
    assert sample([0.1, 3.0, 2.0], rng, temperature=0, top_k=2, top_p=0.1)[0] == 1
    assert rng.calls == 0


def test_greedy_ties_go_to_lowest_index_and_return_logprob():
    idx, lp = sample([1.0, 3.0, 3.0, 0.0], FixedRng(), temperature=0)
    assert idx == 1
    assert lp == pytest.approx(log_softmax([1.0, 3.0, 3.0, 0.0])[1])


def test_negative_temperature_rejected():
    with pytest.raises(ValueError):
        sample(LOGITS, random.Random(1), temperature=-0.5)


# --- статистика на 10 000 вибірках -------------------------------------------------------------

def test_sampling_frequencies_match_softmax():
    f = freqs()
    expected = ref_softmax(LOGITS)
    for got, want in zip(f, expected):
        assert abs(got - want) < 0.03, (f, expected)


def test_low_temperature_concentrates_and_high_temperature_flattens():
    cold, hot = freqs(temperature=0.3), freqs(temperature=5.0)
    assert cold[0] > 0.9
    assert max(hot) < 0.3 and min(hot) > 0.1  # майже рівномірно
    assert all(abs(a - b) < 0.03 for a, b in zip(hot, ref_softmax(LOGITS, 5.0)))
    expected = ref_softmax(LOGITS, 0.3)
    assert all(abs(a - b) < 0.03 for a, b in zip(cold, expected))


def test_top_k_statistics():
    f = freqs(top_k=2)
    assert f[2] == f[3] == f[4] == 0.0
    p = ref_softmax(LOGITS)
    assert abs(f[0] - p[0] / (p[0] + p[1])) < 0.03


def test_top_p_statistics():
    f = freqs(top_p=0.7)
    p = ref_softmax(LOGITS)  # [0.56, 0.21, 0.13, 0.08, 0.03]: 0.56 + 0.21 = 0.77 >= 0.7
    assert f[2] == f[3] == f[4] == 0.0
    assert abs(f[0] - p[0] / (p[0] + p[1])) < 0.03


def test_same_seed_same_sequence_and_one_random_per_sample():
    def run(seed):
        rng = CountingRng(seed)
        return [sample(LOGITS, rng, temperature=0.8, top_k=4, top_p=0.95)[0] for _ in range(200)], rng.calls

    a, calls = run(7)
    assert a == run(7)[0]
    assert a != run(8)[0]
    assert calls == 200


def test_top_p_is_applied_to_the_renormalized_result_of_top_k():
    logits = [math.log(0.4), math.log(0.3), math.log(0.2), math.log(0.1)]
    # top_k=2 -> [0.571, 0.429]; top_p=0.55 вистачає одного токена. Якщо спершу top_p, лишилось би два
    for u in (0.0, 0.7, 0.9999):
        assert sample(logits, FixedRng(u), top_k=2, top_p=0.55)[0] == 0


def test_rounding_fallback_returns_last_token_with_positive_probability():
    logits = [0.0] * 10 + [float("-inf")]
    u = math.nextafter(1.0, 0.0)  # сума десяти 0.1 у float це 0.9999999999999999, тож u < сума хибне
    assert sample(logits, FixedRng(u))[0] == 9
