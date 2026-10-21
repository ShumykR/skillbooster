import copy
import math

import pytest

from solution import apply_mitigations, cheapest_attack, choose_mitigations, success_probability


def leaf(id, cost, prob):
    return {"id": id, "cost": cost, "prob": prob}


def node(id, type, *children):
    return {"id": id, "type": type, "children": list(children)}


TREE = node(
    "root", "OR",
    node("A", "AND", leaf("phish", 100, 0.3), leaf("bypass_mfa", 400, 0.1)),
    node("B", "OR", leaf("sqli", 300, 0.2), leaf("leaked_key", 50, 0.05)),
    node("C", "AND", leaf("insider_hire", 1000, 0.5), leaf("exfil", 10, 0.9)),
)

MITS = [
    {"id": "m_keyscan", "cost": 20, "blocks": ["leaked_key"]},
    {"id": "m_waf", "cost": 80, "blocks": ["sqli"]},
    {"id": "m_mfa", "cost": 150, "blocks": ["bypass_mfa"]},
    {"id": "m_phish", "cost": 90, "blocks": ["phish"]},
    {"id": "m_hr", "cost": 200, "blocks": ["insider_hire"]},
    {"id": "m_trust", "cost": 120, "blocks": ["exfil"]},
]


# --- cheapest_attack -----------------------------------------------------------------------------

def test_cheapest_attack_basic():
    assert cheapest_attack(TREE) == {"cost": 50, "leaves": ["leaked_key"]}


def test_cheapest_attack_after_blocking_leaves():
    assert cheapest_attack(TREE, ["leaked_key"]) == {"cost": 300, "leaves": ["sqli"]}
    assert cheapest_attack(TREE, ["leaked_key", "sqli"]) == {"cost": 500, "leaves": ["bypass_mfa", "phish"]}
    assert cheapest_attack(TREE, ["leaked_key", "sqli", "phish"]) == {"cost": 1010, "leaves": ["exfil", "insider_hire"]}
    assert cheapest_attack(TREE, ["leaked_key", "sqli", "phish", "exfil"]) is None
    assert cheapest_attack(TREE, {"leaked_key", "sqli", "bypass_mfa", "insider_hire"}) is None


def test_and_needs_every_child_and_or_needs_one():
    t = node("r", "AND", leaf("a", 1, 1), node("o", "OR", leaf("b", 5, 1), leaf("c", 2, 1)))
    assert cheapest_attack(t) == {"cost": 3, "leaves": ["a", "c"]}
    assert cheapest_attack(t, ["c"]) == {"cost": 6, "leaves": ["a", "b"]}
    assert cheapest_attack(t, ["a"]) is None
    assert cheapest_attack(t, ["b", "c"]) is None


def test_root_can_be_a_leaf():
    assert cheapest_attack(leaf("x", 7, 0.5)) == {"cost": 7, "leaves": ["x"]}
    assert cheapest_attack(leaf("x", 7, 0.5), ["x"]) is None
    assert success_probability(leaf("x", 7, 0.5)) == 0.5


def test_tie_break_or_prefers_smaller_leaf_list_and_leaves_sorted():
    t = node("r", "OR", leaf("z", 10, 1), leaf("m", 10, 1), leaf("b", 11, 1))
    assert cheapest_attack(t) == {"cost": 10, "leaves": ["m"]}
    t = node("r", "OR",
             node("p", "AND", leaf("y", 5, 1), leaf("a", 5, 1)),
             node("q", "AND", leaf("c", 5, 1), leaf("b", 5, 1)))
    assert cheapest_attack(t) == {"cost": 10, "leaves": ["a", "y"]}


def test_cost_types_and_zero_cost():
    t = node("r", "AND", leaf("a", 0, 1), leaf("b", 0.5, 1))
    assert cheapest_attack(t) == {"cost": 0.5, "leaves": ["a", "b"]}
    t = node("r", "OR", leaf("a", 0, 1), leaf("b", 1, 1))
    assert cheapest_attack(t) == {"cost": 0, "leaves": ["a"]}


def test_inputs_are_not_mutated():
    snapshot = copy.deepcopy(TREE)
    cheapest_attack(TREE, ["sqli"])
    success_probability(TREE, ["sqli"])
    apply_mitigations(TREE, MITS, ["m_waf"])
    choose_mitigations(TREE, MITS, 100)
    assert TREE == snapshot


# --- success_probability -------------------------------------------------------------------------

def test_success_probability_values():
    a, b, c = 0.3 * 0.1, 1 - (1 - 0.2) * (1 - 0.05), 0.5 * 0.9
    assert math.isclose(success_probability(TREE), 1 - (1 - a) * (1 - b) * (1 - c), rel_tol=1e-12)
    assert math.isclose(success_probability(TREE, ["leaked_key"]), 1 - (1 - a) * (1 - 0.2) * (1 - c), rel_tol=1e-12)
    assert success_probability(TREE, ["leaked_key", "sqli", "phish", "exfil"]) == 0
    assert success_probability(TREE, ["leaked_key", "sqli", "bypass_mfa", "insider_hire"]) == 0


def test_probability_edge_values():
    t = node("r", "OR", leaf("a", 1, 1.0), leaf("b", 1, 0.0))
    assert success_probability(t) == 1.0
    assert success_probability(t, ["a"]) == 0.0
    t = node("r", "AND", leaf("a", 1, 1.0), leaf("b", 1, 0.5))
    assert success_probability(t) == 0.5


# --- apply_mitigations ---------------------------------------------------------------------------

def test_apply_mitigations_report():
    r = apply_mitigations(TREE, MITS, ["m_waf", "m_keyscan"])
    assert r["blocked_leaves"] == ["leaked_key", "sqli"]
    assert r["cheapest_before"] == {"cost": 50, "leaves": ["leaked_key"]}
    assert r["cheapest_after"] == {"cost": 500, "leaves": ["bypass_mfa", "phish"]}
    assert math.isclose(r["prob_before"], success_probability(TREE), rel_tol=1e-12)
    assert math.isclose(r["prob_after"], success_probability(TREE, ["leaked_key", "sqli"]), rel_tol=1e-12)
    assert r["prob_after"] < r["prob_before"]


def test_apply_no_mitigations_and_full_block():
    r = apply_mitigations(TREE, MITS, [])
    assert r["blocked_leaves"] == [] and r["cheapest_after"] == r["cheapest_before"]
    r = apply_mitigations(TREE, MITS, ["m_keyscan", "m_waf", "m_phish", "m_trust"])
    assert r["cheapest_after"] is None and r["prob_after"] == 0


def test_mitigation_blocking_one_and_branch_is_enough_for_that_branch():
    r = apply_mitigations(TREE, MITS, ["m_trust"])  # C мертва, але B усе ще дешева
    assert r["cheapest_after"] == {"cost": 50, "leaves": ["leaked_key"]}
    assert r["prob_after"] < r["prob_before"]


def test_overlapping_and_repeated_mitigations_are_deduplicated_in_blocked_leaves():
    mits = [{"id": "x", "cost": 1, "blocks": ["a", "b"]}, {"id": "y", "cost": 1, "blocks": ["b"]}]
    t = node("r", "OR", leaf("a", 1, 1), leaf("b", 1, 1))
    assert apply_mitigations(t, mits, ["x", "y"])["blocked_leaves"] == ["a", "b"]


# --- choose_mitigations --------------------------------------------------------------------------

def test_choose_cheapest_full_cover():
    r = choose_mitigations(TREE, MITS, 310)
    assert r == {"feasible": True, "chosen": ["m_keyscan", "m_phish", "m_trust", "m_waf"], "total_cost": 310,
                 "attack_cost_after": None, "blocked_leaves": ["exfil", "leaked_key", "phish", "sqli"]}
    assert choose_mitigations(TREE, MITS, 5000)["total_cost"] == 310  # більший бюджет не змушує витрачати


def test_choose_when_budget_is_one_short_maximizes_attacker_cost():
    r = choose_mitigations(TREE, MITS, 309)
    assert r == {"feasible": False, "chosen": ["m_keyscan", "m_phish", "m_waf"], "total_cost": 190,
                 "attack_cost_after": 1010, "blocked_leaves": ["leaked_key", "phish", "sqli"]}


def test_choose_small_budgets():
    assert choose_mitigations(TREE, MITS, 0) == {"feasible": False, "chosen": [], "total_cost": 0,
                                                  "attack_cost_after": 50, "blocked_leaves": []}
    r = choose_mitigations(TREE, MITS, 19.9)
    assert r["chosen"] == [] and r["attack_cost_after"] == 50
    r = choose_mitigations(TREE, MITS, 20)  # рівно вартість m_keyscan
    assert (r["chosen"], r["total_cost"], r["attack_cost_after"]) == (["m_keyscan"], 20, 300)
    r = choose_mitigations(TREE, MITS, 100)
    assert (r["chosen"], r["attack_cost_after"]) == (["m_keyscan", "m_waf"], 500)


def test_choose_prefers_fewer_mitigations_at_equal_cost():
    t = node("r", "OR", leaf("x", 1, 1), leaf("y", 1, 1))
    mits = [{"id": "mx", "cost": 10, "blocks": ["x"]}, {"id": "my", "cost": 10, "blocks": ["y"]},
            {"id": "mxy", "cost": 20, "blocks": ["x", "y"]}]
    r = choose_mitigations(t, mits, 20)
    assert r["chosen"] == ["mxy"] and r["feasible"] is True


def test_choose_lexicographic_tie_break():
    t = leaf("x", 1, 1)
    mits = [{"id": "b", "cost": 5, "blocks": ["x"]}, {"id": "a", "cost": 5, "blocks": ["x"]}]
    assert choose_mitigations(t, mits, 5)["chosen"] == ["a"]


def test_choose_prefers_cheaper_among_equal_attacker_cost():
    t = node("r", "OR", leaf("x", 1, 1), leaf("y", 100, 1))
    mits = [{"id": "m_exp", "cost": 50, "blocks": ["x"]}, {"id": "m_cheap", "cost": 30, "blocks": ["x"]}]
    r = choose_mitigations(t, mits, 100)
    assert r["chosen"] == ["m_cheap"] and r["attack_cost_after"] == 100 and r["feasible"] is False


def test_choose_does_not_buy_useless_mitigations():
    t = node("r", "AND", leaf("x", 1, 1), leaf("y", 1, 1))
    mits = [{"id": "mx", "cost": 5, "blocks": ["x"]}, {"id": "my", "cost": 1, "blocks": ["y"]}]
    r = choose_mitigations(t, mits, 100)
    assert r["chosen"] == ["my"] and r["total_cost"] == 1 and r["feasible"] is True


def test_choose_with_no_mitigations():
    r = choose_mitigations(TREE, [], 100)
    assert r == {"feasible": False, "chosen": [], "total_cost": 0, "attack_cost_after": 50, "blocked_leaves": []}


def test_choose_zero_cost_mitigation_is_free():
    t = leaf("x", 1, 1)
    r = choose_mitigations(t, [{"id": "free", "cost": 0, "blocks": ["x"]}], 0)
    assert r["feasible"] is True and r["chosen"] == ["free"] and r["total_cost"] == 0


def test_choose_float_costs_and_budget():
    t = leaf("x", 1, 1)
    mits = [{"id": "m", "cost": 0.25, "blocks": ["x"]}]
    assert choose_mitigations(t, mits, 0.25)["feasible"] is True
    assert choose_mitigations(t, mits, 0.24)["feasible"] is False


# --- валідація -----------------------------------------------------------------------------------

BAD_TREES = {
    "dup_id": node("r", "OR", leaf("a", 1, 1), leaf("a", 2, 1)),
    "dup_with_node": node("r", "OR", node("a", "OR", leaf("b", 1, 1)), leaf("a", 2, 1)),
    "bad_type": node("r", "XOR", leaf("a", 1, 1)),
    "lowercase_type": node("r", "or", leaf("a", 1, 1)),
    "empty_children": node("r", "OR"),
    "negative_cost": node("r", "OR", leaf("a", -1, 1)),
    "bool_cost": node("r", "OR", leaf("a", True, 1)),
    "str_cost": node("r", "OR", leaf("a", "5", 1)),
    "inf_cost": node("r", "OR", leaf("a", math.inf, 1)),
    "nan_cost": node("r", "OR", leaf("a", math.nan, 1)),
    "prob_gt1": node("r", "OR", leaf("a", 1, 1.01)),
    "prob_neg": node("r", "OR", leaf("a", 1, -0.1)),
    "prob_str": node("r", "OR", leaf("a", 1, "0.5")),
    "prob_bool": node("r", "OR", leaf("a", 1, True)),
    "empty_id": node("r", "OR", leaf("", 1, 1)),
    "int_id": node("r", "OR", leaf(5, 1, 1)),
    "missing_cost": node("r", "OR", {"id": "a", "prob": 0.5}),
    "missing_prob": node("r", "OR", {"id": "a", "cost": 1}),
}


@pytest.mark.parametrize("name", sorted(BAD_TREES))
def test_invalid_tree_is_rejected_by_every_function(name):
    t = BAD_TREES[name]
    with pytest.raises(ValueError):
        cheapest_attack(t)
    with pytest.raises(ValueError):
        success_probability(t)
    with pytest.raises(ValueError):
        apply_mitigations(t, [], [])
    with pytest.raises(ValueError):
        choose_mitigations(t, [], 10)


def test_unknown_or_internal_blocked_ids_rejected():
    with pytest.raises(ValueError):
        cheapest_attack(TREE, ["nope"])
    with pytest.raises(ValueError):
        cheapest_attack(TREE, ["A"])  # вузол, а не листок
    with pytest.raises(ValueError):
        success_probability(TREE, ["root"])


@pytest.mark.parametrize("mits", [
    [{"id": "m", "cost": 1, "blocks": ["nope"]}],
    [{"id": "m", "cost": 1, "blocks": ["A"]}],
    [{"id": "m", "cost": 1, "blocks": []}],
    [{"id": "m", "cost": -1, "blocks": ["sqli"]}],
    [{"id": "m", "cost": True, "blocks": ["sqli"]}],
    [{"id": "m", "cost": 1, "blocks": ["sqli"]}, {"id": "m", "cost": 2, "blocks": ["phish"]}],
])
def test_invalid_mitigations(mits):
    with pytest.raises(ValueError):
        choose_mitigations(TREE, mits, 10)
    with pytest.raises(ValueError):
        apply_mitigations(TREE, mits, [])


def test_invalid_budget_applied_and_too_many_mitigations():
    for budget in (-1, "10", None, True, math.inf):
        with pytest.raises(ValueError):
            choose_mitigations(TREE, MITS, budget)
    with pytest.raises(ValueError):
        apply_mitigations(TREE, MITS, ["unknown"])
    many = [{"id": f"m{i:02d}", "cost": 1, "blocks": ["sqli"]} for i in range(17)]
    with pytest.raises(ValueError):
        choose_mitigations(TREE, many, 100)
    ok = [{"id": f"m{i:02d}", "cost": 1, "blocks": ["sqli"]} for i in range(16)]
    assert choose_mitigations(TREE, ok, 100)["chosen"] == []  # жодна не допомагає: B ще має leaked_key


def test_choose_prefers_cheaper_total_over_fewer_mitigations():
    t = node("r", "OR", leaf("x", 1, 1), leaf("y", 1, 1))
    mits = [{"id": "mx", "cost": 10, "blocks": ["x"]}, {"id": "my", "cost": 10, "blocks": ["y"]},
            {"id": "mxy", "cost": 30, "blocks": ["x", "y"]}]
    r = choose_mitigations(t, mits, 100)
    assert r["chosen"] == ["mx", "my"] and r["total_cost"] == 20
