import json

from solution import run_agent


class Script:
    """llm, що віддає заготовлені відповіді й запамʼятовує знімки messages."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.snapshots = []

    def __call__(self, messages):
        self.snapshots.append(json.loads(json.dumps(messages)))
        return self.replies[len(self.snapshots) - 1]


def test_final_immediately():
    llm = Script({"final": "42"})
    res = run_agent(llm, {}, "q")
    assert res == {"answer": "42", "steps": 1, "stopped": "final"}
    assert llm.snapshots[0] == [{"role": "user", "content": "q"}]


def test_tool_then_final_with_kwargs_and_message_format():
    calls = []

    def add(a, b):
        calls.append((a, b))
        return a + b

    llm = Script({"tool": "add", "args": {"a": 2, "b": 3}}, {"final": "5"})
    res = run_agent(llm, {"add": add}, "2+3?")
    assert res == {"answer": "5", "steps": 2, "stopped": "final"}
    assert calls == [(2, 3)]
    msgs = llm.snapshots[1]
    assert msgs[1] == {"role": "assistant", "content": json.dumps({"tool": "add", "args": {"a": 2, "b": 3}}, sort_keys=True)}
    assert msgs[2] == {"role": "tool", "name": "add", "content": "5"}


def test_unknown_tool_is_reported_back_not_raised():
    llm = Script({"tool": "nope", "args": {}}, {"final": "ok"})
    res = run_agent(llm, {}, "q")
    assert res["stopped"] == "final"
    assert llm.snapshots[1][-1]["content"].startswith("ERROR:")


def test_tool_exception_is_reported_back():
    def boom(**kw):
        raise ValueError("bad input")

    llm = Script({"tool": "boom", "args": {}}, {"final": "recovered"})
    res = run_agent(llm, {"boom": boom}, "q")
    assert res["answer"] == "recovered"
    last = llm.snapshots[1][-1]["content"]
    assert last.startswith("ERROR:") and "bad input" in last


def test_bad_args_are_reported_back():
    llm = Script({"tool": "t", "args": {"wrong": 1}}, {"final": "ok"})
    res = run_agent(llm, {"t": lambda x: x}, "q")
    assert res["stopped"] == "final"
    assert llm.snapshots[1][-1]["content"].startswith("ERROR:")


def test_long_observation_truncated():
    llm = Script({"tool": "big", "args": {}}, {"final": "ok"})
    run_agent(llm, {"big": lambda: "x" * 5000}, "q")
    assert len(llm.snapshots[1][-1]["content"]) == 500


def test_loop_detection_on_third_identical_call():
    runs = []
    call = {"tool": "search", "args": {"q": "same"}}
    llm = Script(call, call, call, {"final": "never"})
    res = run_agent(llm, {"search": lambda q: runs.append(q) or "r"}, "q", max_steps=10)
    assert res == {"answer": None, "steps": 3, "stopped": "loop"}
    assert len(runs) == 2, "третій однаковий виклик виконувати не можна"


def test_same_tool_different_args_is_not_a_loop():
    llm = Script(
        {"tool": "s", "args": {"q": "a"}},
        {"tool": "s", "args": {"q": "b"}},
        {"tool": "s", "args": {"q": "c"}},
        {"final": "done"},
    )
    res = run_agent(llm, {"s": lambda q: q}, "q", max_steps=10)
    assert res["stopped"] == "final"


def test_args_order_does_not_hide_loop():
    a = {"tool": "s", "args": {"x": 1, "y": 2}}
    b = {"tool": "s", "args": {"y": 2, "x": 1}}
    llm = Script(a, b, a, {"final": "never"})
    res = run_agent(llm, {"s": lambda x, y: x + y}, "q", max_steps=10)
    assert res["stopped"] == "loop"


def test_max_steps_without_final():
    llm = Script(*[{"tool": "s", "args": {"i": i}} for i in range(10)])
    res = run_agent(llm, {"s": lambda i: i}, "q", max_steps=4)
    assert res == {"answer": None, "steps": 4, "stopped": "max_steps"}
    assert len(llm.snapshots) == 4


def test_final_on_last_allowed_step_counts():
    llm = Script({"tool": "s", "args": {"i": 1}}, {"final": "just in time"})
    res = run_agent(llm, {"s": lambda i: i}, "q", max_steps=2)
    assert res["stopped"] == "final" and res["answer"] == "just in time"
