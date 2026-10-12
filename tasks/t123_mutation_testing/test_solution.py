import sys

import pytest

from solution import generate_mutants, mutation_report


def summary(source):
    return [(m["line"], m["op"], m["description"]) for m in generate_mutants(source)]


# ---------- generate_mutants ---------------------------------------------------------


def test_small_function():
    got = generate_mutants("def is_adult(age):\n    return age >= 18\n")
    assert [(m["id"], m["line"], m["op"], m["description"]) for m in got] == [
        (1, 2, "return", "return -> return None"), (2, 2, "cmp", ">= -> >"), (3, 2, "const", "18 -> 19")]
    assert [m["source"] for m in got] == [
        "def is_adult(age):\n    return None", "def is_adult(age):\n    return age > 18", "def is_adult(age):\n    return age >= 19"]


def test_all_operators_and_their_order():
    source = "def f(a, b, c):\n    if not a and b or c:\n        return a + b * 2\n    x = 0\n    x -= 1\n    return 1 < a <= b\n"
    assert summary(source) == [
        (2, "bool", "or -> and"), (2, "bool", "and -> or"), (2, "not", "not removed"),
        (3, "return", "return -> return None"), (3, "arith", "+ -> -"), (3, "arith", "* -> /"), (3, "const", "2 -> 3"),
        (4, "const", "0 -> 1"),
        (5, "arith", "- -> +"), (5, "const", "1 -> 2"),
        (6, "return", "return -> return None"), (6, "cmp", "< -> <="), (6, "cmp", "<= -> <"), (6, "const", "1 -> 2"),
    ]
    assert [m["id"] for m in generate_mutants(source)] == list(range(1, 15))


def test_each_mutant_changes_exactly_one_thing():
    source = "def f(a, b):\n    return a + b > 0 and not a\n"
    sources = {m["description"]: m["source"] for m in generate_mutants(source)}
    assert sources["+ -> -"] == "def f(a, b):\n    return a - b > 0 and (not a)"
    assert sources["> -> >="] == "def f(a, b):\n    return a + b >= 0 and (not a)"
    assert sources["and -> or"] == "def f(a, b):\n    return a + b > 0 or (not a)" or sources["and -> or"].count("or") == 1
    assert sources["not removed"] == "def f(a, b):\n    return a + b > 0 and a"
    assert sources["0 -> 1"] == "def f(a, b):\n    return a + b > 1 and (not a)"


def test_chained_comparison_gives_one_mutant_per_operator():
    assert [d for _, _, d in summary("ok = a < b <= c\n")] == ["< -> <=", "<= -> <"]


def test_booleans_and_negative_numbers():
    assert summary("def f():\n    return True\n") == [(2, "return", "return -> return None"), (2, "const", "True -> False")]
    got = generate_mutants("x = -1\n")
    assert [(m["description"], m["source"]) for m in got] == [("1 -> 2", "x = -2")]
    assert [m["description"] for m in generate_mutants("flag = False\n")] == ["False -> True"]


def test_division_multiplication_and_augmented_assignment():
    assert [d for _, _, d in summary("y = a / b\n")] == ["/ -> *"]
    assert [d for _, _, d in summary("y = a * b\n")] == ["* -> /"]
    assert [d for _, _, d in summary("y += a\n")] == ["+ -> -"]
    assert [d for _, _, d in summary("y *= a\n")] == ["* -> /"]


@pytest.mark.parametrize("source", [
    "def f():\n    return None\n",
    "def f():\n    return\n",
    "x = 'text'\n",
    "x = 1.5\n",
    "y = a // b % c\n",
    "ok = a in b and c is d or e is not f\n".replace(" and ", " + ").replace(" or ", " + ") if False else "ok = a in b\n",
    "ok = a is None\n",
    "",
])
def test_nothing_to_mutate(source):
    assert generate_mutants(source) == []


def test_syntax_error_is_raised():
    with pytest.raises(SyntaxError):
        generate_mutants("def broken(:\n")


def test_mutated_sources_are_valid_python():
    source = "def f(a, b):\n    if not a or b > 3:\n        return a * 2\n    return b - 1\n"
    for m in generate_mutants(source):
        compile(m["source"], "<m>", "exec")


# ---------- mutation_report ------------------------------------------------------------

CLAMP = "def clamp(x, lo, hi):\n    if x < lo:\n        return lo\n    if x > hi:\n        return hi\n    return x\n"


def weak(ns):
    return ns["clamp"](5, 0, 10) == 5


def strong(ns):
    c = ns["clamp"]
    return c(-5, 0, 10) == 0 and c(15, 0, 10) == 10 and c(5, 0, 10) == 5 and c(0, 0, 10) == 0 and c(10, 0, 10) == 10


def test_weak_tests_leave_survivors_strong_tests_leave_only_equivalent_ones():
    r = mutation_report(CLAMP, weak)
    assert (r["total"], r["killed"], r["survived"], r["score"]) == (5, 1, 4, 0.2)
    assert [s["id"] for s in r["survivors"]] == [1, 2, 3, 4]
    assert r["survivors"][0] == {"id": 1, "line": 2, "op": "cmp", "description": "< -> <="}
    r = mutation_report(CLAMP, strong)
    assert (r["total"], r["killed"], r["survived"], r["score"]) == (5, 3, 2, 0.6)
    assert [(s["line"], s["description"]) for s in r["survivors"]] == [(2, "< -> <="), (4, "> -> >=")], "еквівалентні мутанти"


def test_infinite_loops_are_killed_by_the_step_limit():
    source = "def count(n):\n    i = 0\n    while i < n:\n        i += 1\n    return i\n"
    before = sys.gettrace()
    r = mutation_report(source, lambda ns: ns["count"](3) == 3, max_steps=3000)
    assert sys.gettrace() is before, "трасувальник відновлено"
    assert (r["total"], r["killed"]) == (5, 4)
    assert r["survivors"] == [{"id": 1, "line": 2, "op": "const", "description": "0 -> 1"}]


def test_exceptions_in_mutants_count_as_killed():
    r = mutation_report("def f(x):\n    return 2 * x\n", lambda ns: ns["f"](0) == 0)
    assert r["total"] == 3 and r["killed"] == 2
    assert r["survivors"] == [{"id": 3, "line": 2, "op": "const", "description": "2 -> 3"}]


def test_trace_is_restored_even_when_the_test_raises():
    before = sys.gettrace()

    def test(ns):
        if ns["f"](1) != 2:
            raise RuntimeError("boom")
        return True

    r = mutation_report("def f(x):\n    return x + 1\n", test)
    assert sys.gettrace() is before and r["killed"] == r["total"]


def test_the_original_must_pass():
    with pytest.raises(ValueError):
        mutation_report(CLAMP, lambda ns: False)

    def boom(ns):
        raise AssertionError

    with pytest.raises(ValueError):
        mutation_report(CLAMP, boom)
    with pytest.raises(ValueError):
        mutation_report(CLAMP, lambda ns: 1)


def test_no_mutants_means_a_perfect_score():
    assert mutation_report("x = 'a'\n", lambda ns: True) == {"total": 0, "killed": 0, "survived": 0, "score": 1.0, "survivors": []}


def test_every_mutant_runs_in_a_fresh_namespace():
    seen = []

    def test(ns):
        seen.append(id(ns))
        ns["marker"] = True
        return ns["f"](2) == 3

    mutation_report("def f(x):\n    return x + 1\n", test)
    assert len(seen) > 2 and len(set(seen)) == len(seen), "кожен мутант отримує новий словник"


def test_score_is_rounded_to_four_places():
    source = "def f(x):\n    return x + 1 + 2 + 3\n"
    r = mutation_report(source, lambda ns: ns["f"](0) == 6)
    assert r["score"] == round(r["killed"] / r["total"], 4)


def test_step_limit_is_what_stops_slow_equivalent_mutants():
    source = "def f(n):\n    s = 0\n    for i in range(n):\n        if i > 5000:\n            s += 1\n    return s\n"

    def test(ns):
        return ns["f"](1000) == 0

    generous = mutation_report(source, test)
    assert "> -> >=" in [s["description"] for s in generous["survivors"]], "еквівалентний мутант виживає при щедрому ліміті"
    strict = mutation_report(source, test, max_steps=500)
    assert strict["survived"] == 0, "1000 ітерацій перевищують 500 подій: timeout вважається вбивством"


def test_previous_tracer_is_restored():

    def mine(frame, event, arg):
        return None

    sys.settrace(mine)
    try:
        mutation_report("def f(x):\n    return x + 1\n", lambda ns: ns["f"](1) == 2)
        assert sys.gettrace() is mine
    finally:
        sys.settrace(None)


def test_only_true_counts_as_passing():
    def test(ns):
        return True if ns["f"](1) == 2 else 1

    r = mutation_report("def f(x):\n    return x + 1\n", test)
    assert r["survived"] == 0 and r["total"] == 3
