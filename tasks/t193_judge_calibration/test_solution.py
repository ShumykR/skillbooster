import pytest

from solution import agreement_report, cohens_kappa, length_bias, position_bias, trust_decision

SCORES = {"good": 2, "ok": 1, "bad": 0}


def quality_judge(a, b):
    """Неупереджений суддя: порівнює «якість» з таблиці."""
    sa, sb = SCORES[a], SCORES[b]
    return "A" if sa > sb else "B" if sb > sa else "tie"


class Recorder:
    def __init__(self, fn):
        self.fn = fn
        self.calls = []

    def __call__(self, a, b):
        self.calls.append((a, b))
        return self.fn(a, b)


# --- cohens_kappa ------------------------------------------------------------------------------

def test_kappa_known_values():
    assert cohens_kappa([1, 1, 0, 0], [1, 0, 0, 0]) == 0.5
    human = ["y"] * 25 + ["n"] * 25
    judge = ["y"] * 20 + ["n"] * 5 + ["y"] * 10 + ["n"] * 15
    assert cohens_kappa(human, judge) == 0.4                         # po = 0.7, pe = 0.5
    assert cohens_kappa([1, 2, 3, 1], [1, 2, 3, 1]) == 1.0
    assert cohens_kappa([1, 0, 1, 0], [0, 1, 0, 1]) == -1.0
    assert cohens_kappa(["a", "a"], ["b", "b"]) == 0.0


def test_kappa_constant_identical_labels_is_one_and_rounding():
    assert cohens_kappa(["x"] * 5, ["x"] * 5) == 1.0
    k = cohens_kappa([1, 1, 1, 0, 0, 0, 1], [1, 1, 0, 0, 0, 1, 1])
    # po = 5/7, p_h(1) = 4/7, p_j(1) = 4/7 -> pe = 16/49 + 9/49 = 25/49
    assert k == round((5 / 7 - 25 / 49) / (1 - 25 / 49), 6)


def test_kappa_handles_labels_that_appear_in_only_one_rater():
    assert cohens_kappa(["a", "b", "a", "b"], ["a", "c", "a", "c"]) == round((0.5 - 0.25) / 0.75, 6)


def test_kappa_penalizes_agreement_by_chance_on_imbalanced_data():
    human = [1] * 9 + [0]
    always_one = [1] * 10
    assert cohens_kappa(human, always_one) == 0.0                    # accuracy 0.9, але це випадковість
    assert agreement_report(human, always_one)["accuracy"] == 0.9


@pytest.mark.parametrize("human, judge", [([], []), ([1], [1, 2]), ([1, 2], [1]), (None, [1]), ([1], None), ("ab", "ab"),
                                          ((1, 2), (1, 2))])
def test_kappa_and_report_validate_input(human, judge):
    with pytest.raises(ValueError):
        cohens_kappa(human, judge)
    with pytest.raises(ValueError):
        agreement_report(human, judge)


# --- agreement_report --------------------------------------------------------------------------

def test_agreement_report_shape_and_sorted_confusion():
    human = ["spam", "ham", "spam", "ham", "ham"]
    judge = ["spam", "spam", "ham", "ham", "ham"]
    report = agreement_report(human, judge)
    assert report == {"n": 5, "accuracy": 0.6, "kappa": cohens_kappa(human, judge),
                      "confusion": {"ham": {"ham": 2, "spam": 1}, "spam": {"ham": 1, "spam": 1}}}
    assert list(report["confusion"]) == ["ham", "spam"] and list(report["confusion"]["ham"]) == ["ham", "spam"]


def test_confusion_omits_zero_counts_and_sorts_by_str_with_mixed_labels():
    report = agreement_report([2, 10, 2, "x"], [2, 10, 10, "x"])
    assert list(report["confusion"]) == [10, 2, "x"]                 # str: "10" < "2" < "x"
    assert report["confusion"][2] == {2: 1, 10: 1}
    assert report["confusion"][10] == {10: 1}


def test_accuracy_is_rounded():
    report = agreement_report([1, 1, 1], [1, 1, 0])
    assert report["accuracy"] == 0.666667


# --- position_bias -----------------------------------------------------------------------------

PAIRS = [("good", "bad"), ("ok", "bad"), ("good", "ok")]


def test_fair_judge_has_no_position_bias():
    result = position_bias(quality_judge, PAIRS)
    assert result == {"n": 3, "consistent": 3, "consistency_rate": 1.0, "flips": 0, "flip_rate": 0.0,
                      "first_position_rate": 0.5, "tie_rate": 0.0}


def test_judge_that_always_picks_first_position():
    result = position_bias(lambda a, b: "A", PAIRS)
    assert result == {"n": 3, "consistent": 0, "consistency_rate": 0.0, "flips": 3, "flip_rate": 1.0,
                      "first_position_rate": 1.0, "tie_rate": 0.0}
    assert position_bias(lambda a, b: "B", PAIRS)["first_position_rate"] == 0.0


def test_always_tie_is_consistent_without_flips():
    result = position_bias(lambda a, b: "tie", PAIRS)
    assert result == {"n": 3, "consistent": 3, "consistency_rate": 1.0, "flips": 0, "flip_rate": 0.0,
                      "first_position_rate": 0.0, "tie_rate": 1.0}


def test_tie_in_one_order_is_inconsistent_but_not_a_flip():
    verdicts = iter(["tie", "A", "A", "B"])                          # пара 1: tie, A(= y) ; пара 2: A(= x), B(= x)
    result = position_bias(lambda a, b: next(verdicts), [("p", "q"), ("r", "s")])
    assert result["consistent"] == 1 and result["flips"] == 0
    assert result["consistency_rate"] == 0.5 and result["tie_rate"] == 0.25
    assert result["first_position_rate"] == round(2 / 3, 6)          # рішучі: A, A, B


def test_flip_requires_two_decisive_and_different_winners():
    verdicts = iter(["A", "A", "A", "B", "B", "B", "tie", "tie"])
    result = position_bias(lambda a, b: next(verdicts), [("p", "q"), ("r", "s"), ("t", "u"), ("v", "w")])
    # p,q: A -> p; A на (q,p) -> q: flip. r,s: A -> r; B на (s,r) -> r: консистентно. t,u: B -> u; B на (u,t) -> t: flip. v,w: tie,tie
    assert result["flips"] == 2 and result["consistent"] == 2
    assert result["flip_rate"] == 0.5 and result["consistency_rate"] == 0.5


def test_judge_is_called_twice_per_pair_in_both_orders():
    rec = Recorder(quality_judge)
    position_bias(rec, PAIRS)
    assert rec.calls == [("good", "bad"), ("bad", "good"), ("ok", "bad"), ("bad", "ok"), ("good", "ok"), ("ok", "good")]


def test_rates_are_rounded():
    verdicts = iter(["A", "B", "A", "A", "tie", "tie"])
    result = position_bias(lambda a, b: next(verdicts), [("a", "b"), ("c", "d"), ("e", "f")])
    assert result["consistency_rate"] == round(2 / 3, 6)             # a,b: A->a, B->a: так; c,d: A->c, A->d: ні; e,f: tie,tie: так
    assert result["first_position_rate"] == 0.75                      # рішучі: A, B, A, A
    assert result["tie_rate"] == round(2 / 6, 6)


@pytest.mark.parametrize("pairs", [[], None, "ab"])
def test_position_bias_validates_pairs(pairs):
    with pytest.raises(ValueError):
        position_bias(quality_judge, pairs)


@pytest.mark.parametrize("bad", ["a", "", None, 1, "TIE", "C"])
def test_unknown_verdict_is_value_error(bad):
    with pytest.raises(ValueError):
        position_bias(lambda a, b: bad, PAIRS)
    with pytest.raises(ValueError):
        length_bias(lambda a, b: bad, [("ab", "abcd")])


# --- length_bias -------------------------------------------------------------------------------

LPAIRS = [("short answer", "a much longer padded answer with filler"), ("ok", "okay okay okay")]


def test_judge_that_prefers_longer_or_shorter():
    longer = lambda a, b: "A" if len(a) > len(b) else "B"
    shorter = lambda a, b: "A" if len(a) < len(b) else "B"
    assert length_bias(longer, LPAIRS) == {"calls": 4, "decisive": 4, "longer_wins": 4, "longer_win_rate": 1.0}
    assert length_bias(shorter, LPAIRS) == {"calls": 4, "decisive": 4, "longer_wins": 0, "longer_win_rate": 0.0}


def test_position_biased_judge_is_not_length_biased():
    assert length_bias(lambda a, b: "A", LPAIRS)["longer_win_rate"] == 0.5
    assert length_bias(lambda a, b: "B", LPAIRS)["longer_wins"] == 2


def test_ties_are_not_decisive_and_empty_decisive_gives_half():
    result = length_bias(lambda a, b: "tie", LPAIRS)
    assert result == {"calls": 4, "decisive": 0, "longer_wins": 0, "longer_win_rate": 0.5}
    verdicts = iter(["tie", "B", "A", "tie"])                           # пара 1: tie; (long, short) B = short; пара 2: (ok, okay..) A = ok; tie
    result = length_bias(lambda a, b: next(verdicts), LPAIRS)
    assert result["decisive"] == 2 and result["longer_wins"] == 0 and result["longer_win_rate"] == 0.0


def test_length_bias_call_order_and_rounding():
    rec = Recorder(lambda a, b: "A" if len(a) >= len(b) else "tie")
    pairs = [("aa", "b"), ("c", "dd"), ("ee", "f")]
    result = length_bias(rec, pairs)
    assert rec.calls == [("aa", "b"), ("b", "aa"), ("c", "dd"), ("dd", "c"), ("ee", "f"), ("f", "ee")]
    assert result == {"calls": 6, "decisive": 3, "longer_wins": 3, "longer_win_rate": 1.0}
    verdicts = iter(["A", "A", "B", "A", "A", "tie"])                   # (aa,b):A=aa(longer) ; (b,aa):A=b ; (c,dd):B=dd ; (dd,c):A=dd ; (ee,f):A=ee ; tie
    result = length_bias(lambda a, b: next(verdicts), pairs)
    assert result["decisive"] == 5 and result["longer_wins"] == 4 and result["longer_win_rate"] == 0.8


@pytest.mark.parametrize("pairs", [[], None, [("aa", "bb")], [("a", 5)], [(1, "ab")], [("a", "bb"), ("cc", "dd")]])
def test_length_bias_validates_pairs(pairs):
    with pytest.raises(ValueError):
        length_bias(lambda a, b: "A", pairs)


def test_validation_happens_before_any_judge_call():
    rec = Recorder(lambda a, b: "A")
    with pytest.raises(ValueError):
        length_bias(rec, [("ab", "abc"), ("xx", "yy")])
    assert rec.calls == []


# --- trust_decision ----------------------------------------------------------------------------

GOOD = {"n": 50, "kappa": 0.8, "consistency_rate": 0.95, "longer_win_rate": 0.55}


def test_trusted_when_everything_is_fine():
    assert trust_decision(GOOD) == {"trusted": True, "reasons": []}


@pytest.mark.parametrize("change, reason", [
    ({"n": 29}, "too-few-samples"), ({"kappa": 0.59}, "low-agreement"), ({"consistency_rate": 0.89}, "position-bias"),
    ({"longer_win_rate": 0.66}, "length-bias"), ({"longer_win_rate": 0.34}, "length-bias"),
])
def test_each_reason_alone(change, reason):
    assert trust_decision({**GOOD, **change}) == {"trusted": False, "reasons": [reason]}


def test_all_reasons_in_documented_order():
    report = {"n": 5, "kappa": 0.1, "consistency_rate": 0.5, "longer_win_rate": 0.9}
    assert trust_decision(report) == {"trusted": False, "reasons": ["too-few-samples", "low-agreement", "position-bias", "length-bias"]}


def test_thresholds_are_strict_and_configurable():
    edge = {"n": 30, "kappa": 0.6, "consistency_rate": 0.9, "longer_win_rate": 0.75}
    assert trust_decision(edge, max_length_skew=0.25)["trusted"] is True
    assert trust_decision(edge, max_length_skew=0.24)["reasons"] == ["length-bias"]
    assert trust_decision(edge, max_length_skew=0.25, min_kappa=0.61)["reasons"] == ["low-agreement"]
    assert trust_decision(edge, max_length_skew=0.25, min_consistency=0.91)["reasons"] == ["position-bias"]
    assert trust_decision(edge, max_length_skew=0.25, min_samples=31)["reasons"] == ["too-few-samples"]


@pytest.mark.parametrize("report", [
    None, [], {}, {"n": 50, "kappa": 0.8, "consistency_rate": 0.95},
    {**GOOD, "kappa": "0.8"}, {**GOOD, "n": None}, {**GOOD, "consistency_rate": True}, {**GOOD, "longer_win_rate": [0.5]},
])
def test_report_validation(report):
    with pytest.raises(ValueError):
        trust_decision(report)


def test_end_to_end_a_biased_judge_is_not_trusted():
    human = ["A", "B", "A", "B", "A", "B"] * 6
    judge = ["A"] * 36                                                    # завжди перша позиція
    report = agreement_report(human, judge)
    pos = position_bias(lambda a, b: "A", PAIRS)
    ln = length_bias(lambda a, b: "A", LPAIRS)
    decision = trust_decision({"n": report["n"], "kappa": report["kappa"], "consistency_rate": pos["consistency_rate"],
                               "longer_win_rate": ln["longer_win_rate"]})
    assert decision == {"trusted": False, "reasons": ["low-agreement", "position-bias"]}
