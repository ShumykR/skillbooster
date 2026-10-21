import copy

import pytest

from solution import AgentFSM, IllegalTransition


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


class World:
    """Мок-середовище: інструменти фіксують побічні ефекти, щоб бачити, що виконалось."""

    def __init__(self):
        self.log = []
        self.clock = Clock()
        self.escalations = []

    def tools(self):
        def search(query):
            self.log.append(("search", query))
            return f"found:{query}"

        def write_note(text):
            self.log.append(("write_note", text))
            return len(text)

        def delete_file(path):
            self.log.append(("delete_file", path))
            return "deleted"

        def explode(**kw):
            raise RuntimeError("db down")

        return {
            "search": {"kind": "read", "fn": search},
            "write_note": {"kind": "write", "fn": write_note},
            "delete_file": {"kind": "irreversible", "fn": delete_file},
            "explode": {"kind": "write", "fn": explode},
            "explode_irr": {"kind": "irreversible", "fn": explode},
        }

    def fsm(self, **kw):
        kw.setdefault("on_escalate", self.escalations.append)
        return AgentFSM(self.tools(), clock=self.clock, **kw)


@pytest.fixture
def w():
    return World()


def acting(w, **kw):
    f = w.fsm(**kw)
    f.finish_planning(["look around", "act"])
    assert f.state == "acting"
    return f


def waiting(w, **kw):
    f = acting(w, **kw)
    res = f.call("delete_file", {"path": "/data/a.txt"})
    assert res == {"status": "pending_approval", "call_id": "c1"}
    return f


# --- конструктор і початковий стан -------------------------------------------------------------

def test_initial_state_and_history(w):
    f = w.fsm()
    assert f.state == "planning" and f.pending is None and f.history == []


@pytest.mark.parametrize("spec", [{"kind": "danger", "fn": print}, {"kind": "read"}, {"fn": print},
                                  {"kind": "read", "fn": "not callable"}])
def test_invalid_tool_spec_is_value_error(w, spec):
    with pytest.raises(ValueError):
        AgentFSM({"t": spec}, clock=w.clock)


# --- planning ----------------------------------------------------------------------------------

def test_planning_allows_only_read_tools(w):
    f = w.fsm()
    assert f.call("search", {"query": "x"}) == {"status": "ok", "result": "found:x"}
    for tool, args in (("write_note", {"text": "hi"}), ("delete_file", {"path": "/a"})):
        assert f.call(tool, args) == {"status": "denied", "reason": "not_allowed_in_state"}
    assert w.log == [("search", "x")]
    assert f.state == "planning" and f.pending is None


@pytest.mark.parametrize("plan", [[], None, "plan", [""], ["ok", ""], ["ok", 5], ("a",)])
def test_finish_planning_validates_plan(w, plan):
    f = w.fsm()
    with pytest.raises(ValueError):
        f.finish_planning(plan)
    assert f.state == "planning"


def test_finish_planning_only_from_planning(w):
    f = acting(w)
    with pytest.raises(IllegalTransition):
        f.finish_planning(["again"])


def test_planning_cannot_be_completed(w):
    f = w.fsm()
    with pytest.raises(IllegalTransition):
        f.complete("done")


# --- acting ------------------------------------------------------------------------------------

def test_acting_executes_read_and_write(w):
    f = acting(w)
    assert f.call("search", {"query": "q"})["result"] == "found:q"
    assert f.call("write_note", {"text": "abc"}) == {"status": "ok", "result": 3}
    assert w.log[:2] == [("search", "q"), ("write_note", "abc")]


def test_missing_required_args_is_an_executor_error_and_fails_closed(w):
    f = acting(w)
    assert f.call("search") == {"status": "error", "error": "TypeError"}
    assert f.state == "failed"


def test_irreversible_call_is_gated_not_executed(w):
    f = acting(w)
    res = f.call("delete_file", {"path": "/important"})
    assert res == {"status": "pending_approval", "call_id": "c1"}
    assert f.state == "waiting_approval"
    assert ("delete_file", "/important") not in w.log
    assert w.log == []
    pending = f.pending
    assert pending == {"call_id": "c1", "tool": "delete_file", "args": {"path": "/important"}, "requested_at": 1000.0}


def test_call_ids_are_sequential_across_requests(w):
    f = acting(w)
    assert f.call("delete_file", {"path": "/a"})["call_id"] == "c1"
    f.reject("c1", "alice")
    assert f.call("delete_file", {"path": "/b"})["call_id"] == "c2"


def test_args_are_snapshotted_at_request_time(w):
    f = acting(w)
    args = {"path": "/safe.txt"}
    f.call("delete_file", args)
    args["path"] = "/etc/passwd"       # агент підміняє аргументи після запиту
    f.pending["args"]["path"] = "/x"   # копія: зовнішня зміна не діє
    f.approve("c1", "alice")
    assert w.log == [("delete_file", "/safe.txt")]


def test_complete_from_acting(w):
    f = acting(w)
    f.complete("all done")
    assert f.state == "done"
    with pytest.raises(ValueError):
        acting(World()).complete("")
    with pytest.raises(ValueError):
        acting(World()).complete(None)


# --- waiting_approval, approve/reject ----------------------------------------------------------

def test_all_calls_are_denied_while_waiting(w):
    f = waiting(w, max_denials=100)
    for tool, args in (("search", {"query": "x"}), ("write_note", {"text": "x"}), ("delete_file", {"path": "/b"}),
                       ("nope", {})):
        assert f.call(tool, args) == {"status": "denied", "reason": "waiting_approval"}
    assert f.state == "waiting_approval" and w.log == []
    assert f.pending["call_id"] == "c1"


def test_approve_executes_stored_call_and_returns_to_acting(w):
    f = waiting(w)
    w.clock.t += 10
    res = f.approve("c1", "alice")
    assert res == {"status": "ok", "result": "deleted"}
    assert f.state == "acting" and f.pending is None
    assert w.log == [("delete_file", "/data/a.txt")]
    assert f.call("search", {"query": "after"})["status"] == "ok"


def test_approve_twice_is_illegal_and_does_not_re_execute(w):
    f = waiting(w)
    f.approve("c1", "alice")
    with pytest.raises(IllegalTransition):
        f.approve("c1", "alice")
    assert w.log.count(("delete_file", "/data/a.txt")) == 1


def test_approve_wrong_or_stale_call_id(w):
    f = waiting(w)
    for bad in ("c2", "", None, "c1 "):
        with pytest.raises(IllegalTransition):
            f.approve(bad, "alice")
    assert f.state == "waiting_approval" and w.log == []
    f.reject("c1", "alice")
    f.call("delete_file", {"path": "/b"})
    with pytest.raises(IllegalTransition):
        f.approve("c1", "alice")  # старий id не підтверджує новий запит


def test_approve_outside_waiting_is_illegal(w):
    f = acting(w)
    with pytest.raises(IllegalTransition):
        f.approve("c1", "alice")
    with pytest.raises(IllegalTransition):
        f.reject("c1", "alice")


@pytest.mark.parametrize("approver", ["agent", "Agent", "MODEL", "assistant", "Assistant"])
def test_agent_cannot_approve_itself(w, approver):
    f = waiting(w)
    assert f.approve("c1", approver) == {"status": "denied", "reason": "self_approval"}
    assert f.state == "waiting_approval" and w.log == []
    assert f.pending is not None


@pytest.mark.parametrize("approver", ["", None, 5, ["alice"]])
def test_approver_must_be_non_empty_string(w, approver):
    f = waiting(w)
    with pytest.raises(ValueError):
        f.approve("c1", approver)
    with pytest.raises(ValueError):
        f.reject("c1", approver)
    assert f.state == "waiting_approval"


def test_reject_returns_to_acting_without_executing(w):
    f = waiting(w)
    assert f.reject("c1", "alice") == {"status": "rejected", "call_id": "c1"}
    assert f.state == "acting" and f.pending is None and w.log == []
    assert f.call("search", {"query": "x"})["status"] == "ok"


def test_reject_wrong_id(w):
    f = waiting(w)
    with pytest.raises(IllegalTransition):
        f.reject("c9", "alice")


def test_complete_is_illegal_while_waiting(w):
    f = waiting(w)
    with pytest.raises(IllegalTransition):
        f.complete("done")


# --- тайм-аут і ескалація ----------------------------------------------------------------------

def test_tick_before_timeout_changes_nothing(w):
    f = waiting(w, approval_timeout=300)
    w.clock.t += 299.9
    assert f.tick() == "waiting_approval"
    assert w.escalations == [] and f.pending is not None


def test_tick_at_exact_timeout_escalates_once(w):
    f = waiting(w, approval_timeout=300)
    w.clock.t += 300
    assert f.tick() == "failed"
    assert f.tick() == "failed"
    assert w.escalations == [{"reason": "approval_timeout", "call_id": "c1", "tool": "delete_file",
                              "args": {"path": "/data/a.txt"}, "waited": 300}]
    assert f.pending is None and w.log == []
    assert f.history[-1] == {"from": "waiting_approval", "to": "failed", "reason": "approval_timeout"}


def test_tick_is_noop_in_other_states(w):
    f = w.fsm()
    assert f.tick() == "planning"
    f = acting(w)
    w.clock.t += 10_000
    assert f.tick() == "acting"
    assert w.escalations == []


def test_approve_after_expiry_is_denied_and_escalates(w):
    f = waiting(w, approval_timeout=60)
    w.clock.t += 61
    assert f.approve("c1", "alice") == {"status": "denied", "reason": "expired"}
    assert f.state == "failed" and w.log == []
    assert len(w.escalations) == 1 and w.escalations[0]["waited"] == 61
    assert f.tick() == "failed" and len(w.escalations) == 1


def test_approve_just_before_expiry_works(w):
    f = waiting(w, approval_timeout=60)
    w.clock.t += 59.99
    assert f.approve("c1", "alice")["status"] == "ok"
    assert w.escalations == []


def test_escalation_callback_failure_does_not_block_failed_state(w):
    def boom(event):
        raise RuntimeError("pager down")

    f = waiting(w, approval_timeout=5, on_escalate=boom)
    w.clock.t += 5
    assert f.tick() == "failed"


def test_timeout_without_callback(w):
    f = AgentFSM(w.tools(), clock=w.clock, approval_timeout=5)
    f.finish_planning(["x"])
    f.call("delete_file", {"path": "/a"})
    w.clock.t += 5
    assert f.tick() == "failed"


def test_timeout_is_measured_from_request_time(w):
    f = acting(w, approval_timeout=100)
    w.clock.t += 500   # довго діяв до запиту
    f.call("delete_file", {"path": "/a"})
    w.clock.t += 99
    assert f.tick() == "waiting_approval"
    w.clock.t += 1
    assert f.tick() == "failed"


def test_self_approval_attempt_does_not_reset_the_timer(w):
    f = waiting(w, approval_timeout=100)
    w.clock.t += 60
    f.approve("c1", "agent")
    w.clock.t += 40
    assert f.tick() == "failed"


# --- відмови, лічильник, термінальні стани -----------------------------------------------------

def test_unknown_tool_and_bad_args(w):
    f = acting(w)
    assert f.call("rm_rf", {}) == {"status": "denied", "reason": "unknown_tool"}
    assert f.call(None, {}) == {"status": "denied", "reason": "unknown_tool"}
    assert f.call("search", ["x"]) == {"status": "denied", "reason": "bad_args"}
    assert f.state == "failed"  # третя відмова (max_denials=3)


def test_denials_below_limit_keep_state(w):
    f = acting(w)
    f.call("nope")
    f.call("nope")
    assert f.state == "acting"
    assert f.call("search", {"query": "ok"})["status"] == "ok"


def test_too_many_denials_fails_the_agent(w):
    f = w.fsm(max_denials=2)
    assert f.call("write_note", {"text": "x"})["reason"] == "not_allowed_in_state"
    assert f.state == "planning"
    assert f.call("nope")["reason"] == "unknown_tool"
    assert f.state == "failed"
    assert f.history[-1] == {"from": "planning", "to": "failed", "reason": "too_many_denials"}
    assert f.call("search", {"query": "x"}) == {"status": "denied", "reason": "terminal_state"}


def test_denials_while_waiting_count_and_clear_pending(w):
    f = waiting(w, max_denials=2)
    f.call("search", {"query": "x"})
    f.call("search", {"query": "x"})
    assert f.state == "failed" and f.pending is None
    with pytest.raises(IllegalTransition):
        f.approve("c1", "alice")


def test_denials_are_cumulative_not_consecutive(w):
    f = w.fsm(max_denials=3)
    f.call("nope")
    f.call("search", {"query": "ok"})
    f.call("nope")
    f.call("search", {"query": "ok"})
    assert f.state == "planning"
    f.call("nope")
    assert f.state == "failed"


def test_terminal_state_denials_do_not_count_and_nothing_executes(w):
    f = acting(w)
    f.complete("done")
    for _ in range(5):
        assert f.call("search", {"query": "x"}) == {"status": "denied", "reason": "terminal_state"}
    assert f.call("delete_file", {"path": "/a"}) == {"status": "denied", "reason": "terminal_state"}
    assert f.state == "done" and w.log == []
    assert f.history[-1]["to"] == "done"


def test_executor_error_fails_closed(w):
    f = acting(w)
    assert f.call("explode") == {"status": "error", "error": "RuntimeError"}
    assert f.state == "failed"
    assert f.history[-1] == {"from": "acting", "to": "failed", "reason": "executor_error"}
    assert f.call("search", {"query": "x"})["reason"] == "terminal_state"


def test_executor_error_after_approval_fails_closed(w):
    f = acting(w)
    assert f.call("explode_irr", {})["status"] == "pending_approval"
    assert f.approve("c1", "alice") == {"status": "error", "error": "RuntimeError"}
    assert f.state == "failed" and f.pending is None


def test_fail_from_any_non_terminal_state(w):
    for build in (lambda: w.fsm(), lambda: acting(World()), lambda: waiting(World())):
        f = build()
        f.fail("operator stop")
        assert f.state == "failed"
        assert f.history[-1]["reason"] == "operator stop" and f.pending is None
        with pytest.raises(IllegalTransition):
            f.fail("again")


def test_fail_from_done_is_illegal(w):
    f = acting(w)
    f.complete("ok")
    with pytest.raises(IllegalTransition):
        f.fail("late")


# --- історія -----------------------------------------------------------------------------------

def test_history_records_every_transition_in_order(w):
    f = w.fsm()
    f.finish_planning(["a"])
    f.call("delete_file", {"path": "/a"})
    f.reject("c1", "alice")
    f.call("delete_file", {"path": "/b"})
    f.approve("c2", "alice")
    f.complete("fin")
    assert f.history == [
        {"from": "planning", "to": "acting", "reason": "plan_ready"},
        {"from": "acting", "to": "waiting_approval", "reason": "approval_requested"},
        {"from": "waiting_approval", "to": "acting", "reason": "rejected"},
        {"from": "acting", "to": "waiting_approval", "reason": "approval_requested"},
        {"from": "waiting_approval", "to": "acting", "reason": "approved"},
        {"from": "acting", "to": "done", "reason": "completed"},
    ]


def test_history_and_pending_are_copies(w):
    f = waiting(w)
    f.history.append({"x": 1})
    f.history[0]["to"] = "hacked"
    assert f.history[0]["to"] == "acting"
    snapshot = copy.deepcopy(f.pending)
    f.pending["tool"] = "search"
    assert f.pending == snapshot
