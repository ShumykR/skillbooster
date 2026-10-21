import copy

import pytest

from solution import Crash, DurableRun, NonDeterminismError


# --- підроблені журнал і зовнішня система -------------------------------------------------------

class FakeJournal:
    """Журнал у памʼяті; може впасти ДО запису (`before`) або ПІСЛЯ запису (`after`) події."""

    def __init__(self):
        self.events = []
        self.appends = 0                # кількість викликів append за життя журналу
        self.crash_on = {}              # {номер виклику append: "before" | "after"}

    def append(self, event):
        self.appends += 1
        mode = self.crash_on.get(self.appends)
        if mode == "before":
            raise Crash(f"before append #{self.appends}")
        self.events.append(event)       # зберігаємо сам обʼєкт: мутація студентом буде видна
        if mode == "after":
            raise Crash(f"after append #{self.appends}")

    def read(self):
        return copy.deepcopy(self.events)


class Service:
    """Зовнішня система з дедуплікацією за idempotency_key і підрахунком побічних ефектів."""

    def __init__(self, journal=None):
        self.journal = journal
        self.store = {}                 # key -> результат (дедуплікація)
        self.effect_log = []            # ключі, для яких ефект справді виконано
        self.invocations = []           # (tool, key) для кожного виклику інструмента
        self.llm_calls = 0
        self.crash_plan = {}            # {номер виклику інструмента (з 1): "before_effect" | "after_effect"}
        self.wal_violations = []
        self.flaky = set()

    def _do(self, tool, key, make_result):
        self.invocations.append((tool, key))
        n = len(self.invocations)
        if self.journal is not None:
            seq = int(key.rsplit(":", 1)[1])
            started = [e for e in self.journal.events if e.get("type") == "step_started" and e.get("seq") == seq
                       and e.get("run_id") == key.rsplit(":", 1)[0]]
            if not started:
                self.wal_violations.append(key)
        if self.crash_plan.get(n) == "before_effect":
            raise Crash(f"{tool} crashed before effect")
        if key in self.flaky:
            self.flaky.discard(key)
            raise RuntimeError("transient")
        if key not in self.store:
            self.store[key] = make_result(len(self.store) + 1)
            self.effect_log.append(key)
        result = copy.deepcopy(self.store[key])
        if self.crash_plan.get(n) == "after_effect":
            raise Crash(f"{tool} crashed after effect")
        return result

    def charge(self, order, amount, idempotency_key):
        return self._do("charge", idempotency_key, lambda i: {"id": f"ch-{i}", "order": order, "amount": amount})

    def send_email(self, to, body, idempotency_key):
        return self._do("send_email", idempotency_key, lambda i: {"id": f"mail-{i}", "to": to})

    def tools(self):
        return {"charge": self.charge, "send_email": self.send_email}

    def llm(self):
        self.llm_calls += 1
        return f"plan-{self.llm_calls}"


def make_agent(svc):
    def agent(run):
        plan = run.once("plan", svc.llm)
        a = run.call("charge", {"order": 1, "amount": 10})
        b = run.call("send_email", {"to": "x@example.com", "body": f"charged {a['id']} ({plan})"})
        c = run.call("charge", {"order": 2, "amount": 5})
        return {"plan": plan, "a": a, "b": b, "c": c}
    return agent


def new_world(run_id="r1"):
    journal = FakeJournal()
    svc = Service(journal)
    return journal, svc, (lambda: DurableRun(run_id, journal, svc.tools())), make_agent(svc)


def baseline():
    journal, svc, mk, agent = new_world()
    result = mk().run(agent)
    return result, journal.appends, svc


def only_once(svc, expected_keys):
    assert sorted(svc.effect_log) == sorted(expected_keys)
    assert len(svc.effect_log) == len(set(svc.effect_log))


KEYS = ["r1:1", "r1:2", "r1:3"]


# --- щасливий шлях ------------------------------------------------------------------------------

def test_happy_path_result_effects_and_keys():
    result, appends, svc = baseline()
    assert result == {"plan": "plan-1", "a": {"id": "ch-1", "order": 1, "amount": 10},
                      "b": {"id": "mail-2", "to": "x@example.com"}, "c": {"id": "ch-3", "order": 2, "amount": 5}}
    only_once(svc, KEYS)
    assert [k for _, k in svc.invocations] == KEYS
    assert appends == 1 + 3 * 2 + 1       # once + 3 кроки по 2 події + run_completed
    assert svc.wal_violations == []


def test_identical_calls_are_different_steps_with_different_keys():
    journal, svc, mk, _ = new_world()

    def agent(run):
        return [run.call("charge", {"order": 1, "amount": 10}) for _ in range(3)]

    result = mk().run(agent)
    assert [r["id"] for r in result] == ["ch-1", "ch-2", "ch-3"]
    assert [k for _, k in svc.invocations] == ["r1:0", "r1:1", "r1:2"]
    only_once(svc, ["r1:0", "r1:1", "r1:2"])


def test_rerun_after_completion_calls_nothing():
    journal, svc, mk, agent = new_world()
    first = mk().run(agent)
    calls = {"agent": 0}
    invocations = len(svc.invocations)
    appends = journal.appends

    def spy_agent(run):
        calls["agent"] += 1
        return agent(run)

    again = mk().run(spy_agent)
    assert again == first
    assert calls["agent"] == 0
    assert len(svc.invocations) == invocations and svc.llm_calls == 1
    assert journal.appends == appends


def test_same_instance_can_run_again_after_completion():
    journal, svc, mk, agent = new_world()
    run = mk()
    first = run.run(agent)
    assert run.run(agent) == first
    only_once(svc, KEYS)


def test_completed_result_is_returned_as_copy():
    journal, svc, mk, agent = new_world()
    mk().run(agent)
    r1 = mk().run(agent)
    r1["a"]["id"] = "HACKED"
    assert mk().run(agent)["a"]["id"] == "ch-1"


# --- падіння на кожному кроці -------------------------------------------------------------------

def recover(journal, svc, mk, agent, limit=40):
    """Рестарти процесу, доки агент не завершиться."""
    for _ in range(limit):
        try:
            return mk().run(agent)
        except Crash:
            continue
    raise AssertionError("агент не завершився")


@pytest.mark.parametrize("mode", ["before", "after"])
def test_crash_at_every_journal_append_point(mode):
    expected, total, _ = baseline()
    for k in range(1, total + 1):
        journal, svc, mk, agent = new_world()
        journal.crash_on = {k: mode}
        with pytest.raises(Crash):
            mk().run(agent)
        journal.crash_on = {}
        result = mk().run(agent)
        assert {x: v for x, v in result.items() if x != "plan"} == {x: v for x, v in expected.items() if x != "plan"}, (k, mode)
        assert result["plan"] == f"plan-{svc.llm_calls}", (k, mode)
        only_once(svc, KEYS)
        assert svc.wal_violations == []
        # одна обробка падіння: усі ключі викликані не більше двох разів, завершені кроки не повторюються
        counts = {}
        for _, key in svc.invocations:
            counts[key] = counts.get(key, 0) + 1
        assert all(c <= 2 for c in counts.values()), (k, mode, counts)
        assert sum(counts.values()) <= 4, (k, mode, counts)
        # після відновлення повторний запуск нічого не виконує
        before = (len(svc.invocations), journal.appends)
        assert mk().run(agent) == result
        assert (len(svc.invocations), journal.appends) == before


@pytest.mark.parametrize("mode", ["before_effect", "after_effect"])
@pytest.mark.parametrize("n", [1, 2, 3])
def test_crash_inside_tool_call(n, mode):
    expected, _, _ = baseline()
    journal, svc, mk, agent = new_world()
    svc.crash_plan = {n: mode}
    with pytest.raises(Crash):
        mk().run(agent)
    started = [e["seq"] for e in journal.events if e["type"] == "step_started"]
    completed = [e["seq"] for e in journal.events if e["type"] == "step_completed"]
    crashed_seq = n                                   # seq 0 це once, виклики мають seq 1, 2, 3
    assert crashed_seq in started and crashed_seq not in completed
    svc.crash_plan = {}
    assert mk().run(agent) == expected
    only_once(svc, KEYS)
    invoked = [k for _, k in svc.invocations]
    assert invoked.count(f"r1:{n}") == 2             # крок, що впав, повторено з ТИМ САМИМ ключем
    assert all(invoked.count(k) == 1 for k in KEYS if k != f"r1:{n}")
    assert svc.wal_violations == []


def test_chain_of_crashes_after_every_append():
    expected, total, _ = baseline()
    journal, svc, mk, agent = new_world()
    journal.crash_on = {i: "after" for i in range(1, total + 1)}
    assert recover(journal, svc, mk, agent) == expected
    only_once(svc, KEYS)
    assert svc.llm_calls == 1


def test_chain_of_crashes_before_append_and_in_tools():
    expected, total, _ = baseline()
    journal, svc, mk, agent = new_world()
    journal.crash_on = {i: "before" for i in range(1, 60, 2)}
    svc.crash_plan = {i: ("before_effect" if i % 2 else "after_effect") for i in range(1, 12, 3)}
    result = recover(journal, svc, mk, agent, limit=80)
    assert {k: v for k, v in result.items() if k != "plan"} == {k: v for k, v in expected.items() if k != "plan"}
    assert result["plan"] == f"plan-{svc.llm_calls}"
    only_once(svc, KEYS)
    assert svc.wal_violations == []


def test_long_agent_with_crash_after_every_append():
    journal = FakeJournal()
    svc = Service(journal)
    journal.crash_on = {i: "after" for i in range(1, 70)}

    def agent(run):
        total = 0
        for i in range(25):
            total += run.call("charge", {"order": i, "amount": i})["order"]
        return total

    mk = lambda: DurableRun("long", journal, svc.tools())
    assert recover(journal, svc, mk, agent, limit=100) == sum(range(25))
    only_once(svc, [f"long:{i}" for i in range(25)])


# --- once (чекпоінти недетермінованих значень) ---------------------------------------------------

def test_once_value_survives_crash_after_it_was_recorded():
    journal, svc, mk, agent = new_world()
    journal.crash_on = {2: "before"}          # падіння на step_started першого виклику
    with pytest.raises(Crash):
        mk().run(agent)
    journal.crash_on = {}
    result = mk().run(agent)
    assert svc.llm_calls == 1                 # значення плану взято з журналу
    assert result["plan"] == "plan-1"


@pytest.mark.parametrize("mode, expected_calls", [("before", 2), ("after", 1)])
def test_once_crash_around_its_own_record(mode, expected_calls):
    journal, svc, mk, agent = new_world()
    journal.crash_on = {1: mode}
    with pytest.raises(Crash):
        mk().run(agent)
    journal.crash_on = {}
    result = mk().run(agent)
    assert svc.llm_calls == expected_calls
    assert result["plan"] == f"plan-{expected_calls}"
    only_once(svc, KEYS)


def test_once_shares_step_numbering_with_calls():
    journal, svc, mk, _ = new_world()

    def agent(run):
        run.once("t", lambda: 1)
        run.call("charge", {"order": 1, "amount": 1})
        run.once("u", lambda: 2)
        run.call("charge", {"order": 2, "amount": 2})

    mk().run(agent)
    assert [k for _, k in svc.invocations] == ["r1:1", "r1:3"]


# --- копії, а не посилання ----------------------------------------------------------------------

def test_agent_mutating_results_and_args_does_not_corrupt_the_journal():
    journal, svc, mk, _ = new_world()
    svc.crash_plan = {3: "before_effect"}
    seen = []

    def agent(run):
        v = run.once("v", lambda: {"items": [1]})
        seen.append(copy.deepcopy(v))
        v["items"].append("mutated")
        args = {"order": 1, "amount": 10}
        a = run.call("charge", args)
        seen.append(copy.deepcopy(a))
        a["id"] = "HACKED"
        args["amount"] = 0
        run.call("send_email", {"to": "x", "body": "b"})
        run.call("charge", {"order": 3, "amount": 3})
        return "done"

    with pytest.raises(Crash):
        mk().run(agent)
    svc.crash_plan = {}
    assert mk().run(agent) == "done"
    assert seen[0] == {"items": [1]} and seen[2] == {"items": [1]}      # once на replay без наслідків мутації
    assert seen[1]["id"] == "ch-1" and seen[3]["id"] == "ch-1"          # результат кроку на replay без HACKED


def test_run_result_recorded_as_copy():
    journal, svc, mk, _ = new_world()
    holder = {"x": [1]}

    def agent(run):
        return holder

    first = mk().run(agent)
    first["x"].append(2)
    assert mk().run(agent) == {"x": [1]}


# --- недетермінізм ------------------------------------------------------------------------------

def half_done_journal():
    """Журнал агента, що впав перед записом run_completed: усі кроки є, результату немає."""
    journal, svc, mk, agent = new_world()
    journal.crash_on = {8: "before"}
    with pytest.raises(Crash):
        mk().run(agent)
    journal.crash_on = {}
    return journal, svc, mk


@pytest.mark.parametrize("variant", ["other_tool", "other_args", "once_instead_of_call", "other_once_name",
                                     "call_instead_of_once"])
def test_nondeterminism_is_detected(variant):
    journal, svc, mk = half_done_journal()

    def agent(run):
        if variant == "call_instead_of_once":
            run.call("charge", {"order": 1, "amount": 10})
            return
        run.once("plan" if variant != "other_once_name" else "other", svc.llm)
        if variant == "other_tool":
            run.call("send_email", {"to": "x", "body": "b"})
        elif variant == "other_args":
            run.call("charge", {"order": 1, "amount": 11})
        elif variant == "once_instead_of_call":
            run.once("x", lambda: 1)

    with pytest.raises(NonDeterminismError):
        mk().run(agent)


def test_same_code_after_half_done_journal_is_not_nondeterministic():
    journal, svc, mk = half_done_journal()
    result = mk().run(make_agent(svc))
    assert result["plan"] == "plan-1"
    only_once(svc, KEYS)


# --- помилки ------------------------------------------------------------------------------------

def test_unknown_tool_is_key_error_and_writes_nothing():
    journal, svc, mk, _ = new_world()

    def agent(run):
        run.call("charge", {"order": 1, "amount": 1})
        run.call("launch_missiles", {})

    with pytest.raises(KeyError):
        mk().run(agent)
    assert [e["type"] for e in journal.events] == ["step_started", "step_completed"]


def test_agent_exception_propagates_without_run_completed_and_resumes_from_journal():
    journal, svc, mk, _ = new_world()
    state = {"fail": True}

    def agent(run):
        a = run.call("charge", {"order": 1, "amount": 1})
        if state["fail"]:
            raise ValueError("bug in agent")
        return a

    run = mk()
    with pytest.raises(ValueError):
        run.run(agent)
    assert all(e["type"] != "run_completed" for e in journal.events)
    state["fail"] = False
    assert run.run(agent)["id"] == "ch-1"          # той самий екземпляр: нумерація кроків починається з нуля
    only_once(svc, ["r1:0"])
    assert len(svc.invocations) == 1               # завершений крок не викликано вдруге


def test_tool_exception_leaves_step_open_and_retry_uses_same_key():
    journal, svc, mk, agent = new_world()
    svc.flaky = {"r1:2"}
    with pytest.raises(RuntimeError):
        mk().run(agent)
    types = [(e["type"], e.get("seq")) for e in journal.events]
    assert ("step_started", 2) in types and ("step_completed", 2) not in types
    assert mk().run(agent)["b"]["id"] == "mail-2"
    only_once(svc, KEYS)
    assert [k for _, k in svc.invocations].count("r1:2") == 2


@pytest.mark.parametrize("bad", ["", None, 5, b"r"])
def test_invalid_run_id(bad):
    with pytest.raises(ValueError):
        DurableRun(bad, FakeJournal(), {})


# --- ізоляція запусків --------------------------------------------------------------------------

def test_runs_are_isolated_in_a_shared_journal():
    journal = FakeJournal()
    svc = Service(journal)
    agent = make_agent(svc)
    a = lambda: DurableRun("A", journal, svc.tools())
    b = lambda: DurableRun("B", journal, svc.tools())
    journal.crash_on = {4: "after"}
    with pytest.raises(Crash):
        a().run(agent)                          # A зупинився посередині
    journal.crash_on = {}
    result_b = b().run(agent)                   # B проходить повністю у тому самому журналі
    result_a = a().run(agent)                   # A продовжує: чужі кроки й run_completed не впливають
    assert (result_a["plan"], result_b["plan"]) == ("plan-1", "plan-2")
    assert sorted(svc.effect_log) == sorted(["A:1", "A:2", "A:3", "B:1", "B:2", "B:3"])
    assert [k for _, k in svc.invocations if k.startswith("A:")].count("A:1") == 1
    assert b().run(agent) == result_b and a().run(agent) == result_a
    assert result_a["a"]["id"] != result_b["a"]["id"]


def test_interleaved_events_of_two_runs():
    journal = FakeJournal()
    svc = Service(journal)
    ra, rb = DurableRun("A", journal, svc.tools()), DurableRun("B", journal, svc.tools())

    def agent_for(tag):
        def agent(run):
            return [run.call("charge", {"order": tag, "amount": i})["id"] for i in range(3)]
        return agent

    # вручну чергуємо запуски через падіння після кожної другої події
    journal.crash_on = {2: "after", 4: "after", 6: "after"}
    results = {}
    for _ in range(20):
        for name, run, tag in (("A", ra, 1), ("B", rb, 2)):
            if name in results:
                continue
            try:
                results[name] = run.run(agent_for(tag))
            except Crash:
                pass
        if len(results) == 2:
            break
    assert len(results) == 2
    assert sorted(svc.effect_log) == sorted([f"{r}:{i}" for r in "AB" for i in range(3)])
