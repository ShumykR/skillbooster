import copy
import json
import threading

import pytest

from solution import MERGER_SYSTEM, PLANNER_SYSTEM, SINGLE_SYSTEM, cost_report, run, run_single

TASK = "TASK-MARKER-XYZ: підготуй звіт про ринок"

ROLES = {
    "researcher": {"system": "SYS-RESEARCHER", "budget": 200},
    "writer": {"system": "SYS-WRITER", "budget": 200},
    "critic": {"system": "SYS-CRITIC"},
}
SYS_TO_ROLE = {v["system"]: k for k, v in ROLES.items()}


def plan_json(*subs):
    return json.dumps({"subtasks": list(subs)})


def sub(sid, role, deps=None, goal=None):
    d = {"id": sid, "role": role, "goal": goal or f"goal-{sid}"}
    if deps is not None:
        d["depends_on"] = deps
    return d


def default_worker(user, role):
    goal = user.split("\n")[0][len("Goal: "):]
    return f"OUT<{goal}>", 30, 20  # 50 токенів


class MockLLM:
    """Мок-LLM: маршрутизує за system-промптом; записує всі виклики."""

    def __init__(self, plan, workers=None, merge=("FINAL-ANSWER", 20, 10), plan_usage=(10, 10), single=("S", 5, 5)):
        self.plan = plan
        self.workers = workers or {}
        self.merge = merge
        self.plan_usage = plan_usage
        self.calls = []

    def __call__(self, messages, **kw):
        system, user = messages[0]["content"], messages[-1]["content"]
        self.calls.append({"messages": copy.deepcopy(messages), "system": system, "user": user})
        if system == PLANNER_SYSTEM:
            if isinstance(self.plan, Exception):
                raise self.plan
            return {"content": self.plan, "usage": {"prompt_tokens": self.plan_usage[0],
                                                    "completion_tokens": self.plan_usage[1]}}
        if system == MERGER_SYSTEM:
            if isinstance(self.merge, Exception):
                raise self.merge
            text, p, c = self.merge
            return {"content": text, "usage": {"prompt_tokens": p, "completion_tokens": c}}
        role = SYS_TO_ROLE[system]
        fn = self.workers.get(role, default_worker)
        out = fn(user, role)
        if isinstance(out, Exception):
            raise out
        text, p, c = out
        return {"content": text, "usage": {"prompt_tokens": p, "completion_tokens": c}}

    def worker_calls(self):
        return [c for c in self.calls if c["system"] in SYS_TO_ROLE]

    def worker_call_for(self, goal):
        found = [c for c in self.worker_calls() if c["user"].split("\n")[0] == f"Goal: {goal}"]
        assert len(found) == 1, goal
        return found[0]


def go(llm, **kw):
    kw.setdefault("total_budget", 100_000)
    return run(TASK, llm, copy.deepcopy(ROLES), **kw)


def go_guarded(llm, timeout=5, **kw):
    """Те саме, але зациклення (напр. цикл у плані без перевірки) валить тест, а не вішає pytest."""
    box = {}

    def target():
        try:
            box["result"] = go(llm, **kw)
        except BaseException as e:  # noqa: BLE001
            box["error"] = e

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(timeout)
    assert not t.is_alive(), "run() не завершився: зациклення"
    if "error" in box:
        raise box["error"]
    return box["result"]


THREE = plan_json(sub("a", "researcher"), sub("b", "researcher"), sub("c", "writer", ["a", "b"]))


# --- щасливий шлях -----------------------------------------------------------------------------

def test_happy_path_result_shape_and_tokens():
    llm = MockLLM(THREE)
    r = go(llm)
    assert r["status"] == "ok" and r["error"] is None
    assert r["answer"] == "FINAL-ANSWER"
    assert list(r["subtasks"]) == ["a", "b", "c"]
    for sid, role in (("a", "researcher"), ("b", "researcher"), ("c", "writer")):
        st = r["subtasks"][sid]
        assert st["status"] == "done" and st["role"] == role and st["chain"] == [role]
        assert st["output"] == f"OUT<goal-{sid}>" and st["tokens"] == 50 and st["error"] is None
    assert r["waves"] == [["a", "b"], ["c"]]
    assert r["tokens"] == {"total": 20 + 150 + 30, "orchestrator": 50, "by_role": {"researcher": 100, "writer": 50}}
    assert len(llm.calls) == 5


def test_planner_prompt_contains_task_roles_and_limit():
    llm = MockLLM(THREE)
    go(llm, max_subtasks=5)
    first = llm.calls[0]
    assert first["system"] == PLANNER_SYSTEM
    assert TASK in first["user"]
    assert "critic, researcher, writer" in first["user"]
    assert "5" in first["user"]


def test_merge_prompt_lists_results_in_plan_order():
    llm = MockLLM(THREE)
    go(llm)
    merge = llm.calls[-1]
    assert merge["system"] == MERGER_SYSTEM
    expected = ("Task: " + TASK + "\n\nResults:\n[a] (researcher) OUT<goal-a>\n[b] (researcher) OUT<goal-b>\n"
                "[c] (writer) OUT<goal-c>")
    assert merge["user"] == expected


def test_roles_argument_is_not_mutated_and_runs_are_deterministic():
    roles = copy.deepcopy(ROLES)
    r1 = run(TASK, MockLLM(THREE), roles, total_budget=10_000)
    assert roles == ROLES
    r2 = run(TASK, MockLLM(THREE), roles, total_budget=10_000)
    assert r1 == r2


# --- ізоляція контексту воркерів ---------------------------------------------------------------

def test_worker_context_is_isolated():
    llm = MockLLM(THREE)
    go(llm)
    a = llm.worker_call_for("goal-a")
    assert a["messages"] == [{"role": "system", "content": "SYS-RESEARCHER"},
                             {"role": "user", "content": "Goal: goal-a"}]
    c = llm.worker_call_for("goal-c")
    assert c["messages"][0] == {"role": "system", "content": "SYS-WRITER"}
    assert c["user"] == "Goal: goal-c\n\nInputs:\n[a] OUT<goal-a>\n[b] OUT<goal-b>"
    for call in llm.worker_calls():
        blob = json.dumps(call["messages"], ensure_ascii=False)
        assert "TASK-MARKER-XYZ" not in blob and PLANNER_SYSTEM not in blob and "FINAL-ANSWER" not in blob


def test_worker_sees_only_declared_dependencies():
    plan = plan_json(sub("a", "researcher"), sub("b", "researcher"), sub("c", "writer", ["a"]))
    llm = MockLLM(plan)
    go(llm)
    c = llm.worker_call_for("goal-c")
    assert "OUT<goal-a>" in c["user"] and "OUT<goal-b>" not in c["user"]


def test_wave_mates_do_not_see_each_other():
    llm = MockLLM(plan_json(sub("a", "researcher"), sub("b", "writer")))
    r = go(llm)
    assert r["waves"] == [["a", "b"]]
    assert "OUT<goal-a>" not in llm.worker_call_for("goal-b")["user"]


def test_max_parallel_limits_wave_size():
    plan = plan_json(*[sub(x, "researcher") for x in "abcde"])
    r = go(MockLLM(plan), max_parallel=2)
    assert r["waves"] == [["a", "b"], ["c", "d"], ["e"]]
    r = go(MockLLM(plan), max_parallel=10)
    assert r["waves"] == [["a", "b", "c", "d", "e"]]


def test_waves_follow_dependency_layers():
    plan = plan_json(sub("a", "researcher"), sub("b", "writer", ["a"]), sub("c", "researcher"),
                     sub("d", "critic", ["b", "c"]))
    r = go(MockLLM(plan))
    assert r["waves"] == [["a", "c"], ["b"], ["d"]]
    assert r["status"] == "ok"


def test_later_wave_sees_results_of_earlier_wave_even_with_parallel_limit_one():
    plan = plan_json(sub("a", "researcher"), sub("b", "researcher"), sub("c", "writer", ["b"]))
    llm = MockLLM(plan)
    r = go(llm, max_parallel=1)
    assert r["waves"] == [["a"], ["b"], ["c"]]
    assert "OUT<goal-a>" not in llm.worker_call_for("goal-b")["user"]
    assert "OUT<goal-b>" in llm.worker_call_for("goal-c")["user"]


# --- некоректні плани --------------------------------------------------------------------------

BAD_PLANS = [
    "not json at all",
    "[]",
    json.dumps({"subtasks": []}),
    json.dumps({"subtasks": "x"}),
    json.dumps({}),
    plan_json(*[sub(str(i), "researcher") for i in range(7)]),
    plan_json(sub("a", "researcher"), sub("a", "writer")),
    plan_json(sub("", "researcher")),
    plan_json(sub("a", "hacker")),
    plan_json({"id": "a", "role": "writer", "goal": "  "}),
    plan_json({"id": "a", "role": "writer"}),
    plan_json(sub("a", "writer", ["zzz"])),
    plan_json(sub("a", "writer", ["a"])),
    plan_json(sub("a", "writer", ["b"]), sub("b", "writer", ["a"])),
    plan_json(sub("a", "writer", ["c"]), sub("b", "writer", ["a"]), sub("c", "writer", ["b"])),
    plan_json("not-an-object"),
]


@pytest.mark.parametrize("bad", BAD_PLANS)
def test_invalid_plan_fails_without_calling_workers(bad):
    llm = MockLLM(bad)
    r = go_guarded(llm, max_subtasks=6)
    assert r["status"] == "failed" and r["answer"] == ""
    assert r["error"].startswith("invalid-plan")
    assert len(llm.calls) == 1
    assert r["tokens"] == {"total": 20, "orchestrator": 20, "by_role": {}}
    assert r["subtasks"] == {} and r["waves"] == []


def test_plan_exactly_at_limit_is_valid():
    plan = plan_json(*[sub(str(i), "researcher") for i in range(6)])
    assert go(MockLLM(plan), max_subtasks=6)["status"] == "ok"


def test_planner_exception():
    llm = MockLLM(RuntimeError("down"))
    r = go(llm)
    assert r["status"] == "failed" and r["error"] == "plan-llm-error"
    assert r["tokens"]["total"] == 0 and len(llm.calls) == 1


@pytest.mark.parametrize("kw", [{"total_budget": 0}, {"max_subtasks": 0}, {"max_parallel": 0}, {"max_handoffs": -1}])
def test_bad_arguments(kw):
    with pytest.raises(ValueError):
        go(MockLLM(THREE), **kw)


# --- збої воркерів -----------------------------------------------------------------------------

def test_failed_worker_skips_dependents_but_merge_still_runs():
    def flaky(user, role):
        if user.startswith("Goal: goal-a"):
            return RuntimeError("boom")
        return default_worker(user, role)

    llm = MockLLM(THREE, workers={"researcher": flaky})
    r = go(llm)
    assert r["status"] == "partial"
    assert r["subtasks"]["a"]["status"] == "failed" and r["subtasks"]["a"]["error"] == "llm-error"
    assert r["subtasks"]["b"]["status"] == "done"
    c = r["subtasks"]["c"]
    assert c["status"] == "skipped" and c["error"] == "dependency-failed" and c["tokens"] == 0 and c["chain"] == []
    assert r["waves"] == [["a", "b"]]
    assert all(call["user"].split("\n")[0] != "Goal: goal-c" for call in llm.calls)
    merge = llm.calls[-1]
    assert merge["system"] == MERGER_SYSTEM
    assert "[a] FAILED: llm-error" in merge["user"] and "[b] (researcher) OUT<goal-b>" in merge["user"]
    assert "[c] FAILED: dependency-failed" in merge["user"]
    assert r["answer"] == "FINAL-ANSWER"


def test_dependency_failure_cascades_through_chain():
    plan = plan_json(sub("a", "researcher"), sub("b", "writer", ["a"]), sub("c", "critic", ["b"]),
                     sub("d", "critic"))

    def boom(user, role):
        return RuntimeError("x") if "goal-a" in user else default_worker(user, role)

    r = go(MockLLM(plan, workers={"researcher": boom}))
    assert [r["subtasks"][s]["status"] for s in "abcd"] == ["failed", "skipped", "skipped", "done"]
    assert r["status"] == "partial"


def test_all_workers_failed_means_no_merge():
    llm = MockLLM(THREE, workers={"researcher": lambda u, r: RuntimeError("x")})
    r = go(llm)
    assert r["status"] == "failed" and r["error"] == "no-results" and r["answer"] == ""
    assert all(call["system"] != MERGER_SYSTEM for call in llm.calls)


def test_worker_budget_exceeded_discards_output_but_counts_tokens():
    def hungry(user, role):
        return ("SECRET-BIG-OUTPUT", 100, 101) if "goal-a" in user else default_worker(user, role)

    llm = MockLLM(THREE, workers={"researcher": hungry})
    r = go(llm)
    a = r["subtasks"]["a"]
    assert a["status"] == "failed" and a["error"] == "worker-budget-exceeded"
    assert a["output"] is None and a["tokens"] == 201
    assert r["tokens"]["by_role"]["researcher"] == 251
    assert "SECRET-BIG-OUTPUT" not in llm.calls[-1]["user"]


def test_worker_budget_boundary_is_inclusive():
    r = go(MockLLM(plan_json(sub("a", "researcher")),
                   workers={"researcher": lambda u, role: ("EXACT", 100, 100)}))
    assert r["subtasks"]["a"]["status"] == "done"


def test_role_without_budget_is_unlimited():
    r = go(MockLLM(plan_json(sub("a", "critic")), workers={"critic": lambda u, role: ("HUGE", 50_000, 50_000)}))
    assert r["subtasks"]["a"]["status"] == "done"


# --- загальний бюджет --------------------------------------------------------------------------

def test_total_budget_exhaustion_skips_remaining_workers_and_merge():
    # план 20, кожен воркер 50. Бюджет 160: a -> 70, b -> 120, c(залежить) не потрібен: залежності немає
    plan = plan_json(sub("a", "researcher"), sub("b", "researcher"), sub("c", "writer"), sub("d", "writer"))
    llm = MockLLM(plan)
    r = go(llm, total_budget=160, max_parallel=4)
    assert [r["subtasks"][s]["status"] for s in "abcd"] == ["done", "done", "done", "skipped"]
    assert r["subtasks"]["d"]["error"] == "total-budget-exhausted" and r["subtasks"]["d"]["chain"] == []
    assert r["tokens"]["total"] == 170
    assert r["status"] == "failed" and r["error"] == "budget-exhausted-before-merge" and r["answer"] == ""
    assert all(call["system"] != MERGER_SYSTEM for call in llm.calls)


def test_total_budget_check_is_greater_or_equal():
    plan = plan_json(sub("a", "researcher"), sub("b", "researcher"))
    # після плану (20) і a (50) витрачено рівно 70 == бюджет: b не викликається
    llm = MockLLM(plan)
    r = go(llm, total_budget=70)
    assert r["subtasks"]["a"]["status"] == "done" and r["subtasks"]["b"]["status"] == "skipped"
    assert r["error"] == "budget-exhausted-before-merge"
    # на 1 більше: b викликається
    r = go(MockLLM(plan), total_budget=71)
    assert r["subtasks"]["b"]["status"] == "done"
    assert r["error"] == "budget-exhausted-before-merge"  # 120 >= 71


def test_budget_exhausted_by_dependency_chain_marks_dependents():
    plan = plan_json(sub("a", "researcher"), sub("b", "writer", ["a"]))
    r = go(MockLLM(plan), total_budget=60)
    assert r["subtasks"]["a"]["status"] == "done"
    assert r["subtasks"]["b"]["status"] == "skipped" and r["subtasks"]["b"]["error"] == "total-budget-exhausted"


def test_merge_runs_when_budget_not_exhausted():
    llm = MockLLM(THREE)
    r = go(llm, total_budget=201)
    assert r["status"] == "ok" and r["tokens"]["total"] == 200


# --- handoff -----------------------------------------------------------------------------------

def handoff(to, context):
    return "HANDOFF " + json.dumps({"to": to, "context": context})


def test_handoff_passes_context_not_history():
    def research(user, role):
        return handoff("writer", "підсумок: ринок виріс на 10%"), 30, 20

    llm = MockLLM(plan_json(sub("a", "researcher")), workers={"researcher": research})
    r = go(llm)
    st = r["subtasks"]["a"]
    assert st["status"] == "done" and st["chain"] == ["researcher", "writer"] and st["role"] == "researcher"
    assert st["output"] == "OUT<goal-a>" and st["tokens"] == 100
    assert r["tokens"]["by_role"] == {"researcher": 50, "writer": 50}
    first, second = llm.worker_calls()
    assert second["messages"] == [
        {"role": "system", "content": "SYS-WRITER"},
        {"role": "user", "content": "Goal: goal-a\n\nHandoff from researcher: підсумок: ринок виріс на 10%"},
    ]
    assert "SYS-RESEARCHER" not in json.dumps(second["messages"]) and "HANDOFF" not in second["user"]


def test_handoff_target_also_gets_inputs():
    def research2(user, role):
        text, p, c = default_worker(user, role)
        return (handoff("writer", "ctx") if "goal-b" in user else text), p, c

    llm = MockLLM(plan_json(sub("a", "researcher"), sub("b", "researcher", ["a"])), workers={"researcher": research2})
    go(llm)
    last = llm.worker_calls()[-1]
    assert last["user"] == "Goal: goal-b\n\nHandoff from researcher: ctx\n\nInputs:\n[a] OUT<goal-a>"


@pytest.mark.parametrize("reply", [
    "HANDOFF not-json",
    "HANDOFF " + json.dumps({"to": "hacker", "context": "x"}),
    "HANDOFF " + json.dumps({"context": "x"}),
    "HANDOFF " + json.dumps({"to": "writer"}),
    "HANDOFF " + json.dumps({"to": "researcher", "context": "x"}),  # сама на себе
    "HANDOFF [1, 2]",
])
def test_bad_handoff_fails_subtask(reply):
    llm = MockLLM(plan_json(sub("a", "researcher"), sub("b", "critic")),
                  workers={"researcher": lambda u, r: (reply, 30, 20)})
    r = go(llm)
    assert r["subtasks"]["a"]["status"] == "failed" and r["subtasks"]["a"]["error"] == "bad-handoff"
    assert r["subtasks"]["a"]["output"] is None
    assert r["status"] == "partial"


def test_handoff_cycle_is_rejected():
    def ping(user, role):
        return handoff("writer", "to writer"), 30, 20

    def pong(user, role):
        return handoff("researcher", "back"), 30, 20

    llm = MockLLM(plan_json(sub("a", "researcher")), workers={"researcher": ping, "writer": pong})
    r = go(llm)
    st = r["subtasks"]["a"]
    assert st["error"] == "bad-handoff" and st["chain"] == ["researcher", "writer"] and st["tokens"] == 100
    assert len(llm.worker_calls()) == 2


def test_max_handoffs_limit():
    hops = {"researcher": "writer", "writer": "critic", "critic": "researcher"}

    def chain(user, role):
        return handoff(hops[role], "next"), 30, 20

    def run_with(limit):
        llm = MockLLM(plan_json(sub("a", "researcher")),
                      workers={"researcher": chain, "writer": chain,
                               "critic": lambda u, r: ("DONE-BY-CRITIC", 30, 20)})
        return go(llm, max_handoffs=limit)

    r = run_with(2)
    assert r["subtasks"]["a"]["status"] == "done" and r["subtasks"]["a"]["chain"] == ["researcher", "writer", "critic"]
    assert r["subtasks"]["a"]["output"] == "DONE-BY-CRITIC"
    r = run_with(1)
    assert r["subtasks"]["a"]["error"] == "bad-handoff" and r["subtasks"]["a"]["chain"] == ["researcher", "writer"]
    r = run_with(0)
    assert r["subtasks"]["a"]["error"] == "bad-handoff" and r["subtasks"]["a"]["chain"] == ["researcher"]


def test_handoff_respects_total_budget_and_role_budget():
    def to_writer(user, role):
        return handoff("writer", "ctx"), 30, 20

    llm = MockLLM(plan_json(sub("a", "researcher")), workers={"researcher": to_writer})
    r = go(llm, total_budget=70)  # план 20 + researcher 50 = 70: handoff-виклику немає
    st = r["subtasks"]["a"]
    assert st["status"] == "failed" and st["error"] == "total-budget-exhausted" and st["chain"] == ["researcher"]
    assert len(llm.worker_calls()) == 1

    llm = MockLLM(plan_json(sub("a", "researcher")),
                  workers={"researcher": to_writer, "writer": lambda u, r: ("BIG", 150, 100)})
    st = go(llm)["subtasks"]["a"]
    assert st["status"] == "failed" and st["error"] == "worker-budget-exceeded" and st["chain"] == ["researcher", "writer"]


# --- злиття ------------------------------------------------------------------------------------

def test_merge_exception():
    llm = MockLLM(THREE, merge=RuntimeError("down"))
    r = go(llm)
    assert r["status"] == "failed" and r["error"] == "merge-llm-error" and r["answer"] == ""
    assert r["tokens"]["total"] == 20 + 150


def test_merge_tokens_go_to_orchestrator():
    r = go(MockLLM(THREE, merge=("X", 100, 100), plan_usage=(7, 3)))
    assert r["tokens"]["orchestrator"] == 10 + 200
    assert r["tokens"]["by_role"] == {"researcher": 100, "writer": 50}


# --- один агент проти багатьох -----------------------------------------------------------------

def test_run_single_makes_one_call():
    llm_calls = []

    def llm(messages, **kw):
        llm_calls.append(messages)
        return {"content": "ONE-SHOT", "usage": {"prompt_tokens": 40, "completion_tokens": 60}}

    s = run_single(TASK, llm)
    assert s == {"answer": "ONE-SHOT", "tokens": 100}
    assert llm_calls == [[{"role": "system", "content": SINGLE_SYSTEM}, {"role": "user", "content": TASK}]]


def test_cost_report():
    multi = go(MockLLM(THREE))  # 200 токенів, оркестратор 50
    rep = cost_report(multi, {"answer": "x", "tokens": 100})
    assert rep == {"multi_tokens": 200, "single_tokens": 100, "overhead": 2.0, "cheaper": "single",
                   "orchestrator_share": 0.25}
    rep = cost_report(multi, {"answer": "x", "tokens": 300})
    assert rep["cheaper"] == "multi" and rep["overhead"] == 0.67
    rep = cost_report(multi, {"answer": "x", "tokens": 200})
    assert rep["cheaper"] == "equal" and rep["overhead"] == 1.0


def test_cost_report_edge_cases():
    with pytest.raises(ValueError):
        cost_report(go(MockLLM(THREE)), {"answer": "x", "tokens": 0})
    failed = go(MockLLM("not json"), total_budget=100)
    rep = cost_report(failed, {"answer": "x", "tokens": 10})
    assert rep["multi_tokens"] == 20 and rep["orchestrator_share"] == 1.0
    empty = go(MockLLM(RuntimeError("x")))
    assert cost_report(empty, {"answer": "x", "tokens": 10})["orchestrator_share"] == 0.0
