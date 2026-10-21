import copy

import pytest

from solution import audit, make_counterfactuals

BASE = {"name": "Anna", "gender": "female", "language": "uk", "years": 4,
        "text": "Anna built APIs. Anna led a team, Anna's code shipped.", "skills": ["python", {"level": "senior"}]}

GENDER = {"male": {"gender": "male"}, "female": {"gender": "female"}}


def resumes(n=10, **extra):
    return [{"name": f"Name{i}", "gender": "x", "language": "uk", "years": i + 1, "text": f"Name{i} resume", **extra}
            for i in range(n)]


# --- make_counterfactuals ----------------------------------------------------------------------

def test_variants_are_deep_copies_with_overrides_in_group_order():
    original = copy.deepcopy(BASE)
    out = make_counterfactuals(BASE, {"b": {"gender": "male"}, "a": {"gender": "other", "region": "EU"}})
    assert list(out) == ["b", "a"]
    assert out["b"]["gender"] == "male" and out["b"]["years"] == 4 and "region" not in out["b"]
    assert out["a"]["region"] == "EU"                                           # нові ключі додаються
    assert BASE == original                                                      # оригінал не змінено
    out["b"]["skills"][1]["level"] = "junior"
    out["b"]["skills"].append("x")
    assert BASE["skills"] == ["python", {"level": "senior"}] and out["a"]["skills"] == ["python", {"level": "senior"}]


def test_name_override_rewrites_name_in_other_string_fields():
    out = make_counterfactuals(BASE, {"g": {"name": "Jamal"}})["g"]
    assert out["name"] == "Jamal"
    assert out["text"] == "Jamal built APIs. Jamal led a team, Jamal's code shipped."
    assert out["gender"] == "female" and out["years"] == 4 and out["skills"] == BASE["skills"]
    assert "Anna" not in out["text"]


def test_name_replacement_skips_overridden_fields_and_non_strings():
    out = make_counterfactuals(BASE, {"g": {"name": "Jamal", "text": "Anna kept as is"}})["g"]
    assert out["text"] == "Anna kept as is"
    r = {"name": "Bob", "text": "Bob", "years": 3, "tags": ["Bob"], "nested": {"who": "Bob"}}
    out = make_counterfactuals(r, {"g": {"name": "Eve"}})["g"]
    assert out["text"] == "Eve" and out["tags"] == ["Bob"] and out["nested"] == {"who": "Bob"} and out["years"] == 3


@pytest.mark.parametrize("old", ["", None, 5, ["Anna"]])
def test_no_name_rewrite_when_old_name_is_empty_or_not_a_string(old):
    r = {"name": old, "text": "Anna wrote this"}
    out = make_counterfactuals(r, {"g": {"name": "Jamal"}})["g"]
    assert out["name"] == "Jamal" and out["text"] == "Anna wrote this"


def test_missing_old_name_key_is_fine_and_non_name_overrides_do_not_rewrite():
    assert make_counterfactuals({"text": "Anna"}, {"g": {"name": "Jamal"}})["g"] == {"text": "Anna", "name": "Jamal"}
    out = make_counterfactuals(BASE, {"g": {"gender": "male"}})["g"]
    assert out["text"] == BASE["text"]


def test_override_values_are_copied_too():
    shared = {"k": [1]}
    out = make_counterfactuals({"name": "A"}, {"g": {"meta": shared}})
    out["g"]["meta"]["k"].append(2)
    assert shared == {"k": [1]}


@pytest.mark.parametrize("groups", [None, [], {}, "x", {"a": None}, {"a": {"x": 1}, "b": 5}, {"a": []}])
def test_make_counterfactuals_validates_groups(groups):
    with pytest.raises(ValueError):
        make_counterfactuals(BASE, groups)


# --- audit: метрики ----------------------------------------------------------------------------

def threshold_clf(male_from, female_from):
    return lambda r: r["years"] >= (male_from if r["gender"] == "male" else female_from)


def test_metrics_and_violations_for_a_biased_classifier():
    report = audit(threshold_clf(5, 7), resumes(), {"gender": GENDER})
    gender = report["attributes"]["gender"]
    assert gender["rates"] == {"male": 0.6, "female": 0.4}
    assert gender["gap"] == 0.2
    assert gender["disparate_impact"] == pytest.approx(0.666667, abs=1e-9) and gender["disparate_impact"] == round(0.4 / 0.6, 6)
    assert gender["flip_rate"] == 0.2                                            # років 5 і 6
    assert gender["violations"] == ["gap", "impact", "flips"]
    assert report["violations"] == ["gender:gap", "gender:impact", "gender:flips"]
    assert report["passed"] is False


def test_fair_classifier_passes_with_zero_gap_and_flips():
    report = audit(lambda r: r["years"] >= 5, resumes(), {"gender": GENDER, "language": {"uk": {"language": "uk"}, "en": {"language": "en"}}})
    assert report["passed"] is True and report["violations"] == []
    for attr in report["attributes"].values():
        assert attr["gap"] == 0.0 and attr["flip_rate"] == 0.0 and attr["disparate_impact"] == 1.0
        assert attr["violations"] == []
    assert report["attributes"]["gender"]["rates"] == {"male": 0.6, "female": 0.6}


def test_rates_are_rounded_to_six_digits():
    rs = resumes(3)
    report = audit(lambda r: r["years"] >= 3 if r["gender"] == "male" else r["years"] >= 2, rs, {"gender": GENDER})
    assert report["attributes"]["gender"]["rates"] == {"male": 0.333333, "female": 0.666667}
    assert report["attributes"]["gender"]["gap"] == round(0.666667 - 0.333333, 6)


def test_disparate_impact_is_one_when_nobody_is_selected():
    report = audit(lambda r: False, resumes(), {"gender": GENDER})
    g = report["attributes"]["gender"]
    assert g["rates"] == {"male": 0.0, "female": 0.0} and g["disparate_impact"] == 1.0 and g["violations"] == []


def test_zero_rate_group_gives_zero_impact_violation():
    report = audit(lambda r: r["gender"] == "male", resumes(4), {"gender": GENDER})
    g = report["attributes"]["gender"]
    assert g["rates"] == {"male": 1.0, "female": 0.0} and g["disparate_impact"] == 0.0
    assert g["violations"] == ["gap", "impact", "flips"]


def test_thresholds_defaults_partial_overrides_and_strict_comparisons():
    clf = threshold_clf(5, 7)
    base = audit(clf, resumes(), {"gender": GENDER})["attributes"]["gender"]
    assert base["gap"] == 0.2
    only_flips = audit(clf, resumes(), {"gender": GENDER}, {"max_gap": 0.2, "min_impact": 0.5, "max_flip_rate": 0.1})
    assert only_flips["attributes"]["gender"]["violations"] == ["flips"]            # gap == max_gap не порушення
    exact = audit(clf, resumes(), {"gender": GENDER}, {"max_gap": 0.19, "min_impact": 0.666667, "max_flip_rate": 0.2})
    assert exact["attributes"]["gender"]["violations"] == ["gap"]                    # impact == min_impact та flips == max: ок
    loose = audit(clf, resumes(), {"gender": GENDER}, {"max_gap": 1, "min_impact": 0, "max_flip_rate": 1})
    assert loose["passed"] is True
    partial = audit(clf, resumes(), {"gender": GENDER}, {"max_gap": 0.5})            # решта типові
    assert partial["attributes"]["gender"]["violations"] == ["impact", "flips"]


def test_comparison_uses_rounded_metrics():
    # сирий gap = 0.8 - 0.75 = 0.050000000000000044 > 0.05, але після округлення це 0.05 і порушення немає
    clf = lambda r: r["years"] <= (16 if r["gender"] == "male" else 15)
    report = audit(clf, resumes(20), {"gender": GENDER}, {"max_gap": 0.05, "min_impact": 0.0, "max_flip_rate": 1.0})
    assert report["attributes"]["gender"]["rates"] == {"male": 0.8, "female": 0.75}
    assert report["attributes"]["gender"]["gap"] == 0.05 and report["passed"] is True


def test_flip_rate_counts_resumes_with_any_disagreement_across_three_groups():
    groups = {"a": {"language": "a"}, "b": {"language": "b"}, "c": {"language": "c"}}
    clf = lambda r: (r["years"] % 3 == 0) if r["language"] == "c" else True      # розходиться на 3, 6, 9
    report = audit(clf, resumes(), {"lang": groups})
    lang = report["attributes"]["lang"]
    assert lang["flip_rate"] == 0.7 and lang["rates"] == {"a": 1.0, "b": 1.0, "c": 0.3}
    assert lang["gap"] == 0.7 and lang["disparate_impact"] == 0.3


def test_multiple_attributes_keep_order_and_prefix_violations():
    gender = {"male": {"gender": "male"}, "female": {"gender": "female"}}
    lang = {"uk": {"language": "uk"}, "en": {"language": "en"}}
    clf = lambda r: r["years"] >= (5 if r["language"] == "uk" else 8)
    report = audit(clf, resumes(), {"language": lang, "gender": gender})
    assert list(report["attributes"]) == ["language", "gender"]
    assert report["violations"] == ["language:gap", "language:impact", "language:flips"]
    assert report["attributes"]["gender"]["violations"] == []


# --- audit: виклики класифікатора --------------------------------------------------------------

def test_call_order_count_and_fresh_copies():
    seen = []

    def clf(variant):
        seen.append((variant["name"], variant["gender"], variant["language"], id(variant)))
        variant["text"] = "MUTATED"
        variant["skills"].append("junk")
        return True

    rs = [{"name": "A", "gender": "x", "language": "uk", "text": "A t", "skills": []},
          {"name": "B", "gender": "x", "language": "uk", "text": "B t", "skills": []}]
    snapshot = copy.deepcopy(rs)
    audit(clf, rs, {"gender": GENDER, "language": {"uk": {"language": "uk"}, "en": {"language": "en"}}})
    assert [s[:3] for s in seen] == [
        ("A", "male", "uk"), ("A", "female", "uk"), ("B", "male", "uk"), ("B", "female", "uk"),
        ("A", "x", "uk"), ("A", "x", "en"), ("B", "x", "uk"), ("B", "x", "en")]
    assert rs == snapshot                                                          # клас-р не псує вхідні резюме


def test_classifier_sees_consistent_name_in_text_for_name_attribute():
    seen = []

    def clf(variant):
        seen.append(variant)
        return variant["name"] in variant["text"] and "Anna" not in variant["text"].replace(variant["name"], "")

    rs = [{"name": "Anna", "text": "Anna is a developer. Anna codes."}]
    report = audit(clf, rs, {"name": {"g1": {"name": "Jamal"}, "g2": {"name": "Olena"}}})
    assert report["passed"] is True
    assert [v["text"] for v in seen] == ["Jamal is a developer. Jamal codes.", "Olena is a developer. Olena codes."]


def test_decisions_are_coerced_to_bool():
    outcomes = iter([1, 0, "yes", None, [], "x", 0.0, 2])
    report = audit(lambda r: next(outcomes), resumes(2), {"gender": GENDER, "lang": {"a": {"language": "a"}, "b": {"language": "b"}}})
    assert report["attributes"]["gender"]["rates"] == {"male": 1.0, "female": 0.0}    # 1,0 | "yes",None
    assert report["attributes"]["lang"]["rates"] == {"a": 0.0, "b": 1.0}              # [],"x" | 0.0,2


def test_classifier_exception_is_not_swallowed():
    def clf(r):
        raise RuntimeError("model down")

    with pytest.raises(RuntimeError):
        audit(clf, resumes(2), {"gender": GENDER})


# --- audit: валідація --------------------------------------------------------------------------

@pytest.mark.parametrize("rs", [[], None, "x", {}, [1], [{"a": 1}, "b"]])
def test_bad_resumes(rs):
    with pytest.raises(ValueError):
        audit(lambda r: True, rs, {"gender": GENDER})


@pytest.mark.parametrize("attrs", [{}, None, [], {"g": {"only": {"gender": "m"}}}, {"g": {}}, {"g": None},
                                   {"ok": GENDER, "bad": {"one": {"x": 1}}}, {"g": {"a": {"x": 1}, "b": 3}}])
def test_bad_attributes(attrs):
    with pytest.raises(ValueError):
        audit(lambda r: True, resumes(2), attrs)


@pytest.mark.parametrize("th", [{"max_gaps": 0.1}, {"max_gap": "0.1"}, {"max_gap": None}, {"min_impact": True},
                                {"max_flip_rate": [0.1]}, {"max_gap": 0.1, "other": 1}])
def test_bad_thresholds(th):
    with pytest.raises(ValueError):
        audit(lambda r: True, resumes(2), {"gender": GENDER}, th)


def test_validation_happens_before_any_classifier_call():
    calls = []
    with pytest.raises(ValueError):
        audit(lambda r: calls.append(1) or True, resumes(2), {"gender": GENDER, "bad": {"only": {"x": 1}}})
    assert calls == []
