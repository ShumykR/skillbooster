from math import comb

import pytest

from solution import evaluate_trajectory, pass_at_k, pass_hat_k, run_agent_eval


def traj(*tools, final="done", **args_by_index):
    """traj("search", "read") або traj(("search", {"q": "x"}), "read")."""
    steps = []
    for t in tools:
        if isinstance(t, tuple):
            steps.append({"tool": t[0], "args": t[1]})
        else:
            steps.append({"tool": t, "args": {}})
    return {"steps": steps, "final": final}


# --- evaluate_trajectory: обовʼязкові й заборонені -----------------------------------------------

def test_clean_trajectory_is_ok():
    spec = {"required": ["search", "answer"], "forbidden": ["delete_db"]}
    assert evaluate_trajectory(traj("search", "read", "answer"), spec) == {"ok": True, "violations": []}


def test_empty_spec_accepts_anything_including_no_steps():
    assert evaluate_trajectory(traj(), {}) == {"ok": True, "violations": []}
    assert evaluate_trajectory(traj("a", "b"), {})["ok"] is True


def test_missing_required_tool():
    res = evaluate_trajectory(traj("search"), {"required": ["search", "answer", "cite"]})
    assert res == {"ok": False, "violations": ["missing-tool:answer", "missing-tool:cite"]}


def test_forbidden_tool_reported_once_even_if_called_many_times():
    res = evaluate_trajectory(traj("delete_db", "search", "delete_db", "delete_db"), {"forbidden": ["delete_db", "send_email"]})
    assert res == {"ok": False, "violations": ["forbidden-tool:delete_db"]}


def test_violations_are_unique_and_sorted_alphabetically():
    spec = {"required": ["z_last", "a_first"], "forbidden": ["bad"], "max_calls": 1}
    res = evaluate_trajectory(traj("bad", "bad"), spec)
    assert res["violations"] == sorted(set(res["violations"]))
    assert res["violations"] == ["forbidden-tool:bad", "missing-tool:a_first", "missing-tool:z_last", "too-many-calls"]


# --- порядок -----------------------------------------------------------------------------------

def test_order_satisfied_when_a_precedes_b():
    spec = {"order": [["read_file", "write_file"]]}
    assert evaluate_trajectory(traj("read_file", "write_file"), spec)["ok"] is True


def test_order_violated_when_b_comes_first():
    spec = {"order": [["read_file", "write_file"]]}
    res = evaluate_trajectory(traj("write_file", "read_file"), spec)
    assert res == {"ok": False, "violations": ["order:read_file>write_file"]}


def test_order_violated_when_a_is_absent_but_b_is_present():
    res = evaluate_trajectory(traj("write_file"), {"order": [["read_file", "write_file"]]})
    assert res["violations"] == ["order:read_file>write_file"]


def test_order_is_vacuous_when_b_is_absent():
    assert evaluate_trajectory(traj("read_file"), {"order": [["read_file", "write_file"]]})["ok"] is True
    assert evaluate_trajectory(traj("search"), {"order": [["read_file", "write_file"]]})["ok"] is True


def test_every_call_of_b_needs_an_earlier_a_not_just_the_first():
    # перший write має read перед собою, і цього достатньо для всіх наступних: a раніше b
    spec = {"order": [["read", "write"]]}
    assert evaluate_trajectory(traj("read", "write", "write"), spec)["ok"] is True
    # а тут write іде ДО першого read, хоча read далі є
    assert evaluate_trajectory(traj("write", "read", "write"), spec)["violations"] == ["order:read>write"]


def test_partial_order_allows_unrelated_tools_in_between_and_multiple_pairs():
    spec = {"order": [["plan", "act"], ["act", "verify"]]}
    assert evaluate_trajectory(traj("plan", "search", "act", "log", "verify"), spec)["ok"] is True
    res = evaluate_trajectory(traj("act", "verify", "plan"), spec)
    assert res["violations"] == ["order:plan>act"]
    res = evaluate_trajectory(traj("verify", "act", "plan"), spec)
    assert res["violations"] == ["order:act>verify", "order:plan>act"]


# --- зайві виклики -----------------------------------------------------------------------------

def test_max_calls_boundary():
    spec = {"max_calls": 3}
    assert evaluate_trajectory(traj("a", "b", "c"), spec)["ok"] is True
    assert evaluate_trajectory(traj("a", "b", "c", "d"), spec)["violations"] == ["too-many-calls"]


def test_max_calls_zero():
    assert evaluate_trajectory(traj(), {"max_calls": 0})["ok"] is True
    assert evaluate_trajectory(traj("a"), {"max_calls": 0})["violations"] == ["too-many-calls"]


def test_repeated_identical_calls_detected_by_tool_and_args():
    spec = {"max_repeats": 2}
    same = traj(("search", {"q": "x", "n": 1}), ("search", {"n": 1, "q": "x"}), ("search", {"q": "x", "n": 1}))
    assert evaluate_trajectory(same, spec)["violations"] == ["repeated-call:search"]


def test_repeats_boundary_and_different_args_do_not_count():
    spec = {"max_repeats": 2}
    ok = traj(("search", {"q": "x"}), ("search", {"q": "x"}), ("search", {"q": "y"}), ("search", {"q": "z"}))
    assert evaluate_trajectory(ok, spec)["ok"] is True
    assert evaluate_trajectory(traj("ping", "ping"), {"max_repeats": 1})["violations"] == ["repeated-call:ping"]
    assert evaluate_trajectory(traj("ping", "ping"), {"max_repeats": 2})["ok"] is True


def test_repeated_call_code_is_one_per_tool():
    spec = {"max_repeats": 1}
    t = traj(("a", {"x": 1}), ("a", {"x": 1}), ("a", {"x": 1}), ("b", {}), ("b", {}))
    assert evaluate_trajectory(t, spec)["violations"] == ["repeated-call:a", "repeated-call:b"]


def test_steps_without_args_count_as_empty_args():
    t = {"steps": [{"tool": "ping"}, {"tool": "ping", "args": {}}], "final": ""}
    assert evaluate_trajectory(t, {"max_repeats": 1})["violations"] == ["repeated-call:ping"]


# --- успіх задачі ------------------------------------------------------------------------------

def test_success_callback_receives_final_text():
    seen = []

    def success(final):
        seen.append(final)
        return "42" in final

    assert evaluate_trajectory(traj("a", final="answer is 42"), {}, success=success)["ok"] is True
    assert evaluate_trajectory(traj("a", final="no idea"), {}, success=success)["violations"] == ["task-failed"]
    assert seen == ["answer is 42", "no idea"]


def test_missing_final_is_empty_string():
    seen = []
    evaluate_trajectory({"steps": []}, {}, success=lambda f: seen.append(f) or True)
    assert seen == [""]


def test_success_exception_counts_as_failure_not_crash():
    def boom(final):
        raise RuntimeError("checker broke")

    assert evaluate_trajectory(traj("a"), {}, success=boom) == {"ok": False, "violations": ["task-failed"]}


def test_right_answer_with_forbidden_tool_still_fails():
    res = evaluate_trajectory(traj("delete_db", final="42"), {"forbidden": ["delete_db"]}, success=lambda f: f == "42")
    assert res == {"ok": False, "violations": ["forbidden-tool:delete_db"]}


def test_wrong_answer_with_perfect_path_still_fails():
    res = evaluate_trajectory(traj("search", final="wrong"), {"required": ["search"]}, success=lambda f: f == "42")
    assert res == {"ok": False, "violations": ["task-failed"]}


def test_input_is_not_mutated():
    t = traj(("a", {"x": [1]}), "b")
    spec = {"required": ["a"], "order": [["a", "b"]], "forbidden": ["z"]}
    import copy
    t0, s0 = copy.deepcopy(t), copy.deepcopy(spec)
    evaluate_trajectory(t, spec)
    assert t == t0 and spec == s0


@pytest.mark.parametrize("bad_traj", [{}, {"steps": "abc"}, {"steps": [{"args": {}}]}, {"steps": [{"tool": 5}]},
                                       {"steps": ["search"]}, None, []])
def test_malformed_trajectory_is_value_error(bad_traj):
    with pytest.raises(ValueError):
        evaluate_trajectory(bad_traj, {})


def test_unknown_spec_key_is_value_error():
    with pytest.raises(ValueError):
        evaluate_trajectory(traj("a"), {"requird": ["a"]})


# --- pass@k / pass^k ---------------------------------------------------------------------------

def test_pass_at_k_known_values():
    assert pass_at_k(5, 2, 1) == pytest.approx(0.4)
    assert pass_at_k(5, 2, 3) == pytest.approx(0.9)   # 1 - C(3,3)/C(5,3)
    assert pass_at_k(10, 1, 5) == pytest.approx(0.5)  # 1 - C(9,5)/C(10,5)
    assert pass_at_k(10, 3, 2) == pytest.approx(1 - comb(7, 2) / comb(10, 2))


def test_pass_hat_k_known_values():
    assert pass_hat_k(5, 2, 1) == pytest.approx(0.4)
    assert pass_hat_k(5, 2, 3) == 0.0                 # C(2,3) = 0
    assert pass_hat_k(5, 4, 3) == pytest.approx(0.4)  # C(4,3)/C(5,3)
    assert pass_hat_k(10, 8, 2) == pytest.approx(comb(8, 2) / comb(10, 2))


def test_edges_all_or_nothing():
    for k in (1, 3, 5):
        assert pass_at_k(5, 0, k) == 0.0 and pass_hat_k(5, 0, k) == 0.0
        assert pass_at_k(5, 5, k) == 1.0 and pass_hat_k(5, 5, k) == 1.0


def test_pass_at_k_is_one_when_failures_fewer_than_k():
    assert pass_at_k(5, 3, 3) == 1.0   # n-c = 2 < 3
    assert pass_at_k(5, 4, 2) == 1.0


def test_k_equals_one_is_plain_success_rate_for_both():
    for n, c in [(5, 0), (5, 3), (8, 8), (10, 7)]:
        assert pass_at_k(n, c, 1) == pytest.approx(c / n)
        assert pass_hat_k(n, c, 1) == pytest.approx(c / n)


def test_reliability_never_exceeds_rate_and_capability_never_below():
    for n in range(1, 9):
        for c in range(n + 1):
            for k in range(1, n + 1):
                lo, hi = pass_hat_k(n, c, k), pass_at_k(n, c, k)
                assert 0.0 <= lo <= c / n + 1e-12 <= hi + 2e-12 <= 1.0 + 3e-12


def test_monotonic_in_k():
    n, c = 9, 4
    at = [pass_at_k(n, c, k) for k in range(1, n + 1)]
    hat = [pass_hat_k(n, c, k) for k in range(1, n + 1)]
    assert at == sorted(at)
    assert hat == sorted(hat, reverse=True)


def test_naive_independence_formula_is_not_the_estimator():
    # 1-(1-c/n)^k дає 0.784, незміщена оцінка 0.9; (c/n)^k дає 0.064, а не 0.0
    assert pass_at_k(5, 2, 3) != pytest.approx(1 - (1 - 2 / 5) ** 3)
    assert pass_hat_k(5, 2, 3) != pytest.approx((2 / 5) ** 3)


@pytest.mark.parametrize("n, c, k", [(5, 6, 1), (5, -1, 1), (5, 2, 0), (5, 2, 6), (0, 0, 1), (5.0, 2, 1), (5, 2.0, 1),
                                      (5, 2, 1.5), (True, 1, 1), (5, True, 1)])
def test_pass_k_argument_validation(n, c, k):
    with pytest.raises(ValueError):
        pass_at_k(n, c, k)
    with pytest.raises(ValueError):
        pass_hat_k(n, c, k)


# --- run_agent_eval ----------------------------------------------------------------------------

SPEC_SEARCH = {"required": ["search"], "forbidden": ["delete_db"], "max_calls": 3}


def make_agent(plan):
    """plan[(input, attempt)] -> траєкторія або виняток; записує виклики."""
    calls = []

    def agent(task_input, attempt):
        calls.append((task_input, attempt))
        r = plan[(task_input, attempt)]
        if isinstance(r, Exception):
            raise r
        return r

    agent.calls = calls
    return agent


def test_run_agent_eval_counts_and_metrics():
    good, bad_forbidden, bad_missing = traj("search", final="ok"), traj("search", "delete_db", final="ok"), traj("read", final="ok")
    plan = {("q1", i): (good if i in (0, 1) else bad_forbidden if i == 2 else bad_missing) for i in range(5)}
    plan.update({("q2", i): good for i in range(5)})
    agent = make_agent(plan)
    tasks = [{"id": "t1", "input": "q1", "spec": SPEC_SEARCH}, {"id": "t2", "input": "q2", "spec": SPEC_SEARCH}]
    res = run_agent_eval(agent, tasks, n=5, ks=(1, 3))

    assert agent.calls == [("q1", i) for i in range(5)] + [("q2", i) for i in range(5)]
    r1 = res["tasks"]["t1"]
    assert (r1["n"], r1["c"]) == (5, 2)
    assert r1["pass_at_k"][1] == pytest.approx(0.4) and r1["pass_at_k"][3] == pytest.approx(0.9)
    assert r1["pass_hat_k"][1] == pytest.approx(0.4) and r1["pass_hat_k"][3] == 0.0
    assert r1["violations"] == {"forbidden-tool:delete_db": 1, "missing-tool:search": 2}
    assert list(r1["violations"]) == sorted(r1["violations"])
    r2 = res["tasks"]["t2"]
    assert r2["c"] == 5 and r2["violations"] == {} and r2["pass_hat_k"][3] == 1.0
    assert res["pass_at_k"][1] == pytest.approx((0.4 + 1.0) / 2)
    assert res["pass_at_k"][3] == pytest.approx((0.9 + 1.0) / 2)
    assert res["pass_hat_k"][1] == pytest.approx((0.4 + 1.0) / 2)
    assert res["pass_hat_k"][3] == pytest.approx((0.0 + 1.0) / 2)


def test_agent_exception_is_a_failed_run_with_code():
    plan = {("q", 0): traj("search"), ("q", 1): RuntimeError("tool crashed"), ("q", 2): traj("search")}
    res = run_agent_eval(make_agent(plan), [{"id": "t", "input": "q", "spec": {}}], n=3, ks=(1,))
    t = res["tasks"]["t"]
    assert t["c"] == 2 and t["violations"] == {"agent-error": 1}
    assert t["pass_at_k"][1] == pytest.approx(2 / 3)


def test_malformed_trajectory_from_agent_is_agent_error_not_crash():
    plan = {("q", 0): {"oops": 1}, ("q", 1): traj("search")}
    res = run_agent_eval(make_agent(plan), [{"id": "t", "input": "q", "spec": {}}], n=2, ks=(1,))
    assert res["tasks"]["t"]["violations"] == {"agent-error": 1} and res["tasks"]["t"]["c"] == 1


def test_success_callback_is_used_per_task():
    plan = {("q", i): traj("search", final="42" if i % 2 == 0 else "nope") for i in range(4)}
    task = {"id": "t", "input": "q", "spec": {}, "success": lambda f: f == "42"}
    res = run_agent_eval(make_agent(plan), [task], n=4, ks=(1, 2))
    t = res["tasks"]["t"]
    assert t["c"] == 2 and t["violations"] == {"task-failed": 2}
    assert t["pass_at_k"][2] == pytest.approx(1 - comb(2, 2) / comb(4, 2))
    assert t["pass_hat_k"][2] == pytest.approx(comb(2, 2) / comb(4, 2))


def test_default_ks_and_n():
    plan = {("q", i): traj("a") for i in range(5)}
    res = run_agent_eval(make_agent(plan), [{"id": "t", "input": "q", "spec": {}}])
    assert set(res["pass_at_k"]) == {1, 3} and res["tasks"]["t"]["n"] == 5


def test_k_larger_than_n_fails_before_any_run():
    agent = make_agent({})
    with pytest.raises(ValueError):
        run_agent_eval(agent, [{"id": "t", "input": "q", "spec": {}}], n=2, ks=(1, 3))
    assert agent.calls == []


@pytest.mark.parametrize("kwargs", [{"n": 0}, {"n": -1}, {"ks": (0,)}])
def test_bad_parameters(kwargs):
    with pytest.raises(ValueError):
        run_agent_eval(make_agent({}), [{"id": "t", "input": "q", "spec": {}}], **kwargs)


def test_empty_task_list_is_value_error():
    with pytest.raises(ValueError):
        run_agent_eval(make_agent({}), [], n=3, ks=(1,))


def test_reliability_gap_is_visible_in_aggregate():
    # агент «іноді» вміє: pass@3 високий, pass^3 низький
    plan = {("q", i): (traj("search") if i % 2 == 0 else traj("read")) for i in range(6)}
    res = run_agent_eval(make_agent(plan), [{"id": "t", "input": "q", "spec": {"required": ["search"]}}], n=6, ks=(1, 3))
    assert res["pass_at_k"][3] > 0.9 > 0.2 > res["pass_hat_k"][3]
