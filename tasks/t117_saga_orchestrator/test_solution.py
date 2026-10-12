import pytest

from solution import NonRetryable, SagaOrchestrator


class Crash(BaseException):
    """Імітація смерті процесу: не Exception, тому оркестратор не має її перехоплювати."""


class World:
    """Усі «зовнішні сервіси»: журнал викликів і налаштування збоїв."""

    def __init__(self):
        self.calls = []
        self.fail = {}        # імʼя дії -> скільки разів ще впаде (або виняток)
        self.crash = set()

    def action(self, name, result=None):
        def run(ctx):
            self.calls.append(name)
            if name in self.crash:
                self.crash.discard(name)
                raise Crash(name)
            f = self.fail.get(name)
            if f:
                if isinstance(f, Exception):
                    raise f
                self.fail[name] = f - 1
                raise RuntimeError(f"{name} failed")
            if result:
                ctx.update(result)
        return run

    def undo(self, name, key=None):
        def run(ctx):
            self.calls.append(f"undo:{name}:{ctx.get(key) if key else ''}")
            f = self.fail.get(f"undo:{name}")
            if f:
                self.fail[f"undo:{name}"] = f - 1
                raise RuntimeError("undo failed")
            if f"crash:undo:{name}" in self.crash:
                self.crash.discard(f"crash:undo:{name}")
                raise Crash(name)
        return run


def order_steps(w, **retries):
    return [
        {"name": "reserve", "action": w.action("reserve", {"reservation": "r1"}), "compensate": w.undo("reserve", "reservation"), "retries": retries.get("reserve", 0)},
        {"name": "charge", "action": w.action("charge", {"payment": "p1"}), "compensate": w.undo("charge", "payment"), "retries": retries.get("charge", 0)},
        {"name": "ship", "action": w.action("ship"), "compensate": w.undo("ship"), "retries": retries.get("ship", 0)},
        {"name": "email", "action": w.action("email"), "compensate": None},
    ]


@pytest.fixture
def world():
    return World()


@pytest.fixture
def store():
    return {}


# ---------- happy path -------------------------------------------------------------


def test_all_steps_succeed(world, store):
    result = SagaOrchestrator(store).run("s1", order_steps(world), {"order": 7})
    assert result == {"saga_id": "s1", "status": "completed", "completed": ["reserve", "charge", "ship", "email"], "undone": [], "error": None}
    assert world.calls == ["reserve", "charge", "ship", "email"]
    assert store["s1"]["ctx"] == {"order": 7, "reservation": "r1", "payment": "p1"}
    assert store["s1"]["log"] == ["start:reserve", "done:reserve", "start:charge", "done:charge", "start:ship", "done:ship", "start:email", "done:email"]


def test_input_ctx_is_not_mutated_and_results_are_copies(world, store):
    ctx = {"order": 1}
    result = SagaOrchestrator(store).run("s", order_steps(world), ctx)
    assert ctx == {"order": 1}
    result["completed"].append("hack")
    assert store["s"]["completed"] == ["reserve", "charge", "ship", "email"]


# ---------- compensation ---------------------------------------------------------------


def test_failure_compensates_completed_steps_in_reverse_order(world, store):
    world.fail["ship"] = 1
    result = SagaOrchestrator(store).run("s1", order_steps(world))
    assert result["status"] == "compensated" and result["completed"] == ["reserve", "charge"]
    assert result["undone"] == ["charge", "reserve"]
    assert result["error"] == "ship: RuntimeError: ship failed"
    assert world.calls == ["reserve", "charge", "ship", "undo:charge:p1", "undo:reserve:r1"], "ship не компенсується: він не завершився"
    assert store["s1"]["log"][-5:] == ["failed:ship", "undo:charge", "undone:charge", "undo:reserve", "undone:reserve"]
    assert "email" not in world.calls


def test_first_step_failing_has_nothing_to_compensate(world, store):
    world.fail["reserve"] = 1
    result = SagaOrchestrator(store).run("s", order_steps(world))
    assert result["status"] == "compensated" and result["undone"] == [] and world.calls == ["reserve"]


def test_steps_without_compensation_are_marked_undone_silently(world, store):
    steps = [
        {"name": "a", "action": world.action("a"), "compensate": world.undo("a")},
        {"name": "mail", "action": world.action("mail"), "compensate": None},
        {"name": "b", "action": world.action("b"), "compensate": world.undo("b")},
    ]
    world.fail["b"] = 1
    result = SagaOrchestrator(store).run("s", steps)
    assert result["undone"] == ["mail", "a"]
    assert world.calls == ["a", "mail", "b", "undo:a:"]
    assert not any(e.endswith(":mail") and e.startswith("undo") for e in store["s"]["log"])


# ---------- retries ------------------------------------------------------------------------


def test_step_is_retried_before_the_saga_gives_up(world, store):
    world.fail["charge"] = 2
    result = SagaOrchestrator(store).run("s", order_steps(world, charge=2))
    assert result["status"] == "completed"
    assert world.calls.count("charge") == 3
    assert store["s"]["log"].count("start:charge") == 3 and "failed:charge" not in store["s"]["log"]


def test_retries_exhausted_starts_compensation(world, store):
    world.fail["charge"] = 5
    result = SagaOrchestrator(store).run("s", order_steps(world, charge=1))
    assert result["status"] == "compensated"
    assert world.calls.count("charge") == 2
    assert world.calls[-1] == "undo:reserve:r1"


def test_non_retryable_errors_are_not_retried(world, store):
    world.fail["charge"] = NonRetryable("insufficient funds")
    result = SagaOrchestrator(store).run("s", order_steps(world, charge=5))
    assert world.calls.count("charge") == 1
    assert result["status"] == "compensated" and result["error"] == "charge: NonRetryable: insufficient funds"
    assert issubclass(NonRetryable, Exception)


# ---------- compensation failures ------------------------------------------------------------


def test_compensation_is_retried(world, store):
    world.fail["ship"] = 1
    world.fail["undo:charge"] = 2
    result = SagaOrchestrator(store, compensation_attempts=3).run("s", order_steps(world))
    assert result["status"] == "compensated"
    assert world.calls.count("undo:charge:p1") == 3


def test_failed_compensation_stops_the_saga_for_manual_help_and_can_be_resumed(world, store):
    world.fail["ship"] = 1
    world.fail["undo:charge"] = 2
    orch = SagaOrchestrator(store, compensation_attempts=2)
    result = orch.run("s", order_steps(world))
    assert result["status"] == "failed" and result["undone"] == []
    assert "undo_failed:charge" in store["s"]["log"]
    assert "undo:reserve:r1" not in world.calls, "решту не скасовуємо, поки не розібрались із застряглою компенсацією"
    # оператор виправив проблему: повторний запуск продовжує компенсацію
    result = orch.run("s", order_steps(world))
    assert result["status"] == "compensated" and result["undone"] == ["charge", "reserve"]
    assert "ship" not in world.calls[world.calls.index("undo:charge:p1"):], "дії більше не виконуються"


# ---------- crash and resume ---------------------------------------------------------------------


def test_resume_after_process_death_skips_finished_steps(world, store):
    world.crash.add("charge")
    orch = SagaOrchestrator(store)
    with pytest.raises(Crash):
        orch.run("s", order_steps(world), {"order": 1})
    assert store["s"]["status"] == "running" and store["s"]["completed"] == ["reserve"]
    result = orch.run("s", order_steps(world))
    assert result["status"] == "completed"
    assert world.calls == ["reserve", "charge", "charge", "ship", "email"], "reserve не повторено, charge виконано знову"
    assert store["s"]["ctx"]["reservation"] == "r1" and store["s"]["ctx"]["order"] == 1


def test_resumed_saga_uses_the_persisted_context_for_compensation(world, store):
    world.crash.add("ship")
    orch = SagaOrchestrator(store)
    with pytest.raises(Crash):
        orch.run("s", order_steps(world))
    world.fail["ship"] = 1
    result = orch.run("s", order_steps(world))
    assert result["status"] == "compensated"
    assert world.calls[-2:] == ["undo:charge:p1", "undo:reserve:r1"], "значення з ctx відновлені зі store"


def test_crash_during_compensation_resumes_only_the_remaining_undo(world, store):
    world.fail["ship"] = 1
    world.crash.add("crash:undo:charge")
    orch = SagaOrchestrator(store)
    with pytest.raises(Crash):
        orch.run("s", order_steps(world))
    assert store["s"]["status"] == "compensating" and store["s"]["undone"] == []
    result = orch.run("s", order_steps(world))
    assert result["status"] == "compensated" and result["undone"] == ["charge", "reserve"]
    assert world.calls.count("undo:charge:p1") == 2 and world.calls.count("undo:reserve:r1") == 1


def test_crash_between_compensations_does_not_repeat_finished_ones(world, store):
    world.fail["ship"] = 1
    world.crash.add("crash:undo:reserve")
    orch = SagaOrchestrator(store)
    with pytest.raises(Crash):
        orch.run("s", order_steps(world))
    assert store["s"]["undone"] == ["charge"]
    orch.run("s", order_steps(world))
    assert world.calls.count("undo:charge:p1") == 1


def test_finished_sagas_are_not_executed_again(world, store):
    orch = SagaOrchestrator(store)
    first = orch.run("done", order_steps(world))
    calls = list(world.calls)
    assert orch.run("done", order_steps(world)) == first and world.calls == calls
    world.fail["ship"] = 1
    comp = orch.run("bad", order_steps(world))
    calls = list(world.calls)
    assert comp["status"] == "compensated"
    assert orch.run("bad", order_steps(world)) == comp and world.calls == calls


def test_sagas_are_independent(world, store):
    orch = SagaOrchestrator(store)
    orch.run("a", order_steps(world))
    world.fail["charge"] = 1
    assert orch.run("b", order_steps(world))["status"] == "compensated"
    assert store["a"]["status"] == "completed"


# ---------- validation ---------------------------------------------------------------------------------


def test_invalid_step_lists(world, store):
    orch = SagaOrchestrator(store)
    with pytest.raises(ValueError):
        orch.run("s", [])
    dup = [{"name": "x", "action": world.action("x"), "compensate": None}] * 2
    with pytest.raises(ValueError):
        orch.run("s", dup)


def test_stored_state_with_an_unknown_step_is_rejected(world, store):
    store["s"] = {"status": "running", "completed": ["old_step"], "undone": [], "ctx": {}, "error": None, "log": []}
    with pytest.raises(ValueError):
        SagaOrchestrator(store).run("s", order_steps(world))
