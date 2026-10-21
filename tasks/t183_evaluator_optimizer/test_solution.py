import copy

import pytest

from solution import run_harness


class Script:
    """Мок-LLM: віддає заготовлені відповіді по черзі й запамʼятовує запити."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []

    def __call__(self, request):
        self.requests.append(copy.deepcopy(request))
        reply = self.replies[len(self.requests) - 1]
        if isinstance(reply, Exception):
            raise reply
        return reply


class Verifier:
    """Мок-верифікатор: patch -> (failed, total); рахує виклики."""

    def __init__(self, table, errors=None):
        self.table = table
        self.calls = []
        self.errors = errors or {}

    def __call__(self, patch):
        self.calls.append(patch)
        outcome = self.table[patch]
        if isinstance(outcome, Exception):
            raise outcome
        failed, total = outcome
        return {"passed": total - failed, "failed": failed, "total": total, "errors": self.errors.get(patch, [])}


def p(patch, cost=0.1):
    return {"patch": patch, "cost": cost}


def run(replies, table, **kw):
    prop, ver = Script(replies), Verifier(table)
    return run_harness("fix bug", prop, ver, **kw), prop, ver


def reasons(result):
    return [e["reason"] for e in result["trajectory"]]


# --- успіх і зупинка ---------------------------------------------------------------------------

def test_stops_on_green_tests_without_extra_proposals():
    res, prop, ver = run([p("a"), p("b"), p("c")], {"a": (3, 5), "b": (0, 5), "c": (0, 5)})
    assert res["status"] == "success" and res["patch"] == "b"
    assert res["iterations"] == 2
    assert len(prop.requests) == 2 and ver.calls == ["a", "b"]
    assert reasons(res) == ["baseline", "solved"]
    assert res["trajectory"][-1]["accepted"] is True


def test_first_attempt_can_solve():
    res, prop, _ = run([p("a")], {"a": (0, 4)})
    assert (res["status"], res["patch"], res["iterations"]) == ("success", "a", 1)
    assert reasons(res) == ["solved"]


def test_request_contents_and_feedback_chain():
    res, prop, _ = run([p("a"), p("b"), p("c")], {"a": (3, 5), "b": (2, 5), "c": (0, 5)})
    r1, r2, r3 = prop.requests
    assert r1 == {"task": "fix bug", "attempt": 1, "base_patch": None, "feedback": None}
    assert r2["attempt"] == 2 and r2["base_patch"] == "a"
    assert r2["feedback"] == {"passed": 2, "failed": 3, "total": 5, "errors": []}
    assert r3["base_patch"] == "b" and r3["feedback"]["failed"] == 2


def test_feedback_carries_verifier_errors():
    prop = Script([p("a"), p("b")])
    ver = Verifier({"a": (1, 2), "b": (0, 2)}, errors={"a": ["test_x: AssertionError"]})
    run_harness("t", prop, ver)
    assert prop.requests[1]["feedback"]["errors"] == ["test_x: AssertionError"]


# --- відкат при регресії -----------------------------------------------------------------------

def test_regression_is_rolled_back_and_not_used_as_base():
    res, prop, _ = run([p("a"), p("worse"), p("c")], {"a": (2, 5), "worse": (4, 5), "c": (0, 5)})
    assert reasons(res) == ["baseline", "regression", "solved"]
    assert prop.requests[2]["base_patch"] == "a"            # не "worse"
    assert prop.requests[2]["feedback"]["failed"] == 4     # але агент бачить, чому вона погана
    assert [e["accepted"] for e in res["trajectory"]] == [True, False, True]


def test_returned_patch_is_best_not_last():
    res, _, _ = run([p("a"), p("b"), p("worse")], {"a": (3, 5), "b": (1, 5), "worse": (5, 5)}, max_iters=3)
    assert res["status"] == "max_iters"
    assert res["patch"] == "b"


def test_equal_failures_do_not_replace_best():
    res, prop, _ = run([p("a"), p("b"), p("c")], {"a": (2, 5), "b": (2, 5), "c": (1, 5)}, max_iters=3)
    assert reasons(res) == ["baseline", "no_improvement", "improved"]
    assert prop.requests[2]["base_patch"] == "a"
    assert res["patch"] == "c"


def test_baseline_with_failures_is_accepted_even_if_all_fail():
    res, _, _ = run([p("a")], {"a": (5, 5)}, max_iters=1)
    assert res["patch"] == "a" and res["status"] == "max_iters"


# --- ліміти ------------------------------------------------------------------------------------

def test_max_iters_limit():
    res, prop, ver = run([p(f"p{i}") for i in range(10)], {f"p{i}": (9 - i, 20) for i in range(10)}, max_iters=3)
    assert res["status"] == "max_iters" and res["iterations"] == 3
    assert len(prop.requests) == 3 and len(ver.calls) == 3
    assert res["patch"] == "p2"


def test_budget_limit_stops_before_next_proposal():
    res, prop, _ = run([p(f"p{i}", 0.4) for i in range(10)], {f"p{i}": (9 - i, 20) for i in range(10)}, max_cost=1.0)
    # вартість перед ітераціями: 0, 0.4, 0.8 (< 1.0), після третьої 1.2: четверта не стартує
    assert res["status"] == "budget" and res["iterations"] == 3
    assert len(prop.requests) == 3
    assert res["cost"] == pytest.approx(1.2)


def test_budget_boundary_is_inclusive():
    res, prop, _ = run([p("a", 0.5), p("b", 0.5), p("c", 0.5)], {"a": (3, 5), "b": (2, 5), "c": (1, 5)}, max_cost=1.0)
    assert res["status"] == "budget" and len(prop.requests) == 2
    assert res["cost"] == pytest.approx(1.0)


def test_response_that_crosses_budget_is_still_verified():
    res, _, ver = run([p("a", 5.0)], {"a": (0, 3)}, max_cost=1.0)
    assert res["status"] == "success" and ver.calls == ["a"]


def test_zero_budget_makes_no_calls():
    res, prop, ver = run([p("a")], {"a": (0, 1)}, max_cost=0)
    assert res["status"] == "no_valid_patch" and res["patch"] is None
    assert prop.requests == [] and ver.calls == []


def test_max_iters_has_priority_over_budget():
    res, _, _ = run([p("a", 2.0)], {"a": (3, 5)}, max_iters=1, max_cost=1.0)
    assert res["status"] == "max_iters"


def test_cost_is_summed_and_missing_cost_is_zero():
    res, _, _ = run([{"patch": "a"}, p("b", 0.25), p("c", 0.5)], {"a": (3, 5), "b": (2, 5), "c": (1, 5)}, max_iters=3)
    assert res["cost"] == pytest.approx(0.75)
    assert [e["cost"] for e in res["trajectory"]] == [0.0, 0.25, 0.5]


@pytest.mark.parametrize("bad", [-0.1, "0.1", None, True])
def test_invalid_cost_is_value_error(bad):
    with pytest.raises(ValueError):
        run([{"patch": "a", "cost": bad}], {"a": (1, 2)})


# --- дублікати й зациклення --------------------------------------------------------------------

def test_duplicate_patch_is_not_verified_again():
    res, _, ver = run([p("a"), p("a"), p("b")], {"a": (3, 5), "b": (0, 5)})
    assert ver.calls == ["a", "b"]
    assert reasons(res) == ["baseline", "duplicate", "solved"]
    assert res["trajectory"][1]["failed"] is None and res["trajectory"][1]["accepted"] is False


def test_two_duplicates_in_a_row_mean_stalled():
    res, prop, ver = run([p("a"), p("a"), p("a"), p("b")], {"a": (3, 5), "b": (0, 5)})
    assert res["status"] == "stalled" and res["patch"] == "a"
    assert len(prop.requests) == 3 and ver.calls == ["a"]


def test_duplicates_must_be_consecutive_to_stall():
    res, _, _ = run([p("a"), p("a"), p("b"), p("a"), p("c")],
                    {"a": (3, 5), "b": (4, 5), "c": (0, 5)}, max_iters=5)
    assert res["status"] == "success" and res["patch"] == "c"
    assert reasons(res) == ["baseline", "duplicate", "regression", "duplicate", "solved"]


def test_rejected_patch_is_still_a_duplicate_later():
    res, _, ver = run([p("a"), p("worse"), p("worse"), p("c")],
                      {"a": (2, 5), "worse": (4, 5), "c": (0, 5)})
    assert ver.calls == ["a", "worse", "c"]
    assert reasons(res)[2] == "duplicate"


# --- помилки моделі й верифікатора -------------------------------------------------------------

def test_propose_exception_consumes_iteration_and_continues():
    res, prop, _ = run([RuntimeError("llm down"), p("a")], {"a": (0, 2)})
    assert reasons(res) == ["propose_error", "solved"]
    assert res["trajectory"][0]["patch"] is None and res["trajectory"][0]["cost"] == 0.0
    assert res["iterations"] == 2


def test_propose_errors_exhaust_iterations():
    res, _, _ = run([RuntimeError("x")] * 3, {}, max_iters=3)
    assert res["status"] == "no_valid_patch" and res["patch"] is None and res["iterations"] == 3


@pytest.mark.parametrize("reply", [{"patch": ""}, {"patch": None}, {"patch": 5}, {"patch": ["x"]}, {}])
def test_bad_proposal_is_not_verified(reply):
    res, _, ver = run([dict(reply, cost=0.2), p("a")], {"a": (0, 2)})
    assert ver.calls == ["a"]
    assert reasons(res) == ["bad_proposal", "solved"]
    assert res["trajectory"][0]["cost"] == pytest.approx(0.2)
    assert res["cost"] == pytest.approx(0.3)


def test_verify_exception_fails_closed():
    res, prop, ver = run([p("a"), p("b")], {"a": RuntimeError("sandbox crashed"), "b": (0, 3)})
    assert reasons(res) == ["verify_error", "solved"]
    assert res["trajectory"][0]["accepted"] is False
    assert prop.requests[1]["base_patch"] is None


def test_verify_exception_on_last_iteration_yields_no_patch():
    res, _, _ = run([p("a")], {"a": RuntimeError("boom")}, max_iters=1)
    assert res["status"] == "no_valid_patch" and res["patch"] is None


def test_zero_tests_is_not_success():
    res, prop, _ = run([p("a"), p("b")], {"a": (0, 0), "b": (0, 4)})
    assert reasons(res) == ["no_tests", "solved"]
    assert res["patch"] == "b"
    assert prop.requests[1]["base_patch"] is None


def test_only_zero_tests_never_succeeds():
    res, _, _ = run([p("a"), p("b")], {"a": (0, 0), "b": (0, 0)}, max_iters=2)
    assert res["status"] == "no_valid_patch" and res["patch"] is None


# --- журнал ------------------------------------------------------------------------------------

def test_trajectory_shape():
    res, _, _ = run([p("a", 0.3), p("b", 0.2)], {"a": (2, 5), "b": (0, 5)})
    assert res["trajectory"] == [
        {"iter": 1, "patch": "a", "cost": 0.3, "passed": 3, "failed": 2, "total": 5, "accepted": True, "reason": "baseline"},
        {"iter": 2, "patch": "b", "cost": 0.2, "passed": 5, "failed": 0, "total": 5, "accepted": True, "reason": "solved"},
    ]
    assert set(res) == {"status", "patch", "iterations", "cost", "trajectory"}


def test_result_is_a_copy_and_requests_are_not_mutated_later():
    seen = []

    def propose(req):
        seen.append(req)
        return p("a" if req["attempt"] == 1 else "b")

    ver = Verifier({"a": (2, 3), "b": (0, 3)})
    res = run_harness("t", propose, ver)
    res["trajectory"].clear()
    first = copy.deepcopy(seen[0])
    run_harness("t", propose, Verifier({"a": (2, 3), "b": (0, 3)}))
    assert seen[0] == first
    assert seen[1]["feedback"] == {"passed": 1, "failed": 2, "total": 3, "errors": []}


def test_feedback_is_a_copy_of_verifier_result():
    shared = {"passed": 1, "failed": 2, "total": 3, "errors": ["e"]}

    def verify(patch):
        return shared if patch == "a" else {"passed": 3, "failed": 0, "total": 3, "errors": []}

    def propose(req):
        if req["feedback"] is not None:
            req["feedback"]["errors"].append("tampered by agent")
        return p("a" if req["attempt"] == 1 else "b")

    run_harness("t", propose, verify)
    assert shared["errors"] == ["e"]


def test_feedback_survives_non_verified_iteration():
    res, prop, _ = run([p("a"), RuntimeError("x"), p("b")], {"a": (3, 5), "b": (0, 5)})
    assert prop.requests[2]["feedback"]["failed"] == 3
    assert prop.requests[2]["base_patch"] == "a"


def test_agent_cannot_tamper_with_feedback_via_request():
    seen = []

    def propose(req):
        seen.append(copy.deepcopy(req))
        if req["attempt"] == 2:
            req["feedback"]["failed"] = 0
            req["feedback"]["errors"].append("tampered")
            return {"patch": ""}
        return p("a" if req["attempt"] == 1 else "b")

    run_harness("t", propose, Verifier({"a": (3, 5), "b": (0, 5)}))
    assert seen[2]["feedback"] == {"passed": 2, "failed": 3, "total": 5, "errors": []}
