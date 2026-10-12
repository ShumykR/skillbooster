import pytest

from solution import LlmTracer

PRICES = {"big": {"in": 3, "out": 15}, "small": {"in": 0.1, "out": 0.4}}


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


@pytest.fixture
def env():
    clock = Clock()
    return clock, LlmTracer(clock, PRICES)


# ---------- traces and spans ---------------------------------------------------------------------------------------------


def test_a_simple_trace(env):
    clock, tr = env
    with tr.trace("ask", user="ann", tags=["prod", "rag"]) as t:
        clock.now += 0.5
        with t.span("retrieve", top_k=3) as s:
            clock.now += 0.25
    done = tr.traces[0]
    assert (done["id"], done["name"], done["user"], done["tags"]) == ("t1", "ask", "ann", ["prod", "rag"])
    assert (done["start"], done["end"], done["duration"], done["status"], done["error"]) == (100.0, 100.75, 0.75, "ok", None)
    assert done["cost"] == 0.0 and done["tokens"] == 0
    assert done["spans"] == [{"id": "s1", "parent": None, "kind": "span", "name": "retrieve", "start": 100.5, "end": 100.75, "duration": 0.25,
                              "status": "ok", "error": None, "attrs": {"top_k": 3}}]
    assert s["id"] == "s1" and s["name"] == "retrieve"


def test_nested_spans_know_their_parent(env):
    clock, tr = env
    with tr.trace("ask") as t:
        with t.span("outer"):
            with t.span("inner"):
                clock.now += 1
            with t.span("inner2"):
                pass
        with t.span("after"):
            pass
    spans = {s["name"]: s for s in tr.traces[0]["spans"]}
    assert spans["outer"]["parent"] is None and spans["inner"]["parent"] == "s1" and spans["inner2"]["parent"] == "s1" and spans["after"]["parent"] is None
    assert spans["outer"]["duration"] == 1.0 and [s["id"] for s in tr.traces[0]["spans"]] == ["s1", "s2", "s3", "s4"]


def test_trace_ids_increment_and_traces_list_is_a_copy(env):
    _, tr = env
    for _ in range(3):
        with tr.trace("x"):
            pass
    assert [t["id"] for t in tr.traces] == ["t1", "t2", "t3"]
    tr.traces.clear()
    assert len(tr.traces) == 3


def test_exceptions_are_recorded_and_propagate(env):
    clock, tr = env
    with pytest.raises(ValueError):
        with tr.trace("ask", user="ann") as t:
            with t.span("work"):
                clock.now += 2
                raise ValueError("boom")
    done = tr.traces[0]
    assert done["status"] == "error" and done["error"] == "ValueError: boom" and done["duration"] == 2.0
    assert done["spans"][0]["status"] == "error" and done["spans"][0]["error"] == "ValueError: boom" and done["spans"][0]["duration"] == 2.0


def test_a_caught_exception_marks_the_span_but_not_the_trace(env):
    _, tr = env
    with tr.trace("ask") as t:
        try:
            with t.span("flaky"):
                raise RuntimeError("retryable")
        except RuntimeError:
            pass
        with t.span("fallback"):
            pass
    done = tr.traces[0]
    assert done["status"] == "ok" and done["error"] is None
    assert [s["status"] for s in done["spans"]] == ["error", "ok"]
    assert [s["parent"] for s in done["spans"]] == [None, None], "стек span закрито і після винятку"


def test_using_a_finished_trace_is_an_error(env):
    _, tr = env
    with tr.trace("x") as t:
        pass
    with pytest.raises(RuntimeError):
        with t.span("late"):
            pass
    with pytest.raises(RuntimeError):
        with t.generation("late", "big", "p"):
            pass


def test_max_traces_keeps_the_latest():
    clock = Clock()
    tr = LlmTracer(clock, PRICES, max_traces=2)
    for _ in range(3):
        with tr.trace("x"):
            pass
    assert [t["id"] for t in tr.traces] == ["t2", "t3"]


# ---------- generations -----------------------------------------------------------------------------------------------------------


def test_generation_cost_tokens_and_ttft(env):
    clock, tr = env
    with tr.trace("ask", user="ann") as t:
        with t.generation("answer", "big", "What is the refund policy?") as g:
            clock.now += 0.25
            g.first_token()
            clock.now += 1.0
            g.first_token()
            g.finish("14 days", {"prompt_tokens": 1000, "completion_tokens": 500})
    gen = tr.traces[0]["spans"][0]
    assert gen == {"id": "s1", "parent": None, "kind": "generation", "name": "answer", "start": 100.0, "end": 101.25, "duration": 1.25,
                   "status": "ok", "error": None, "attrs": {}, "model": "big", "prompt_chars": 26, "prompt_tokens": 1000, "completion_tokens": 500,
                   "cost": 0.0105, "ttft": 0.25, "output_chars": 7}
    assert tr.traces[0]["cost"] == 0.0105 and tr.traces[0]["tokens"] == 1500


def test_prompts_and_outputs_are_not_stored_by_default(env):
    _, tr = env
    with tr.trace("ask") as t:
        with t.generation("a", "big", "secret prompt") as g:
            g.finish("secret answer", {"prompt_tokens": 1})
    gen = tr.traces[0]["spans"][0]
    assert "input" not in gen and "output" not in gen
    assert "secret" not in str(tr.traces[0])


def test_capture_content_stores_texts():
    tr = LlmTracer(Clock(), PRICES, capture_content=True)
    with tr.trace("ask") as t:
        with t.generation("a", "big", "the prompt") as g:
            g.finish("the answer", {})
    gen = tr.traces[0]["spans"][0]
    assert gen["input"] == "the prompt" and gen["output"] == "the answer"


def test_generation_without_finish_and_double_finish(env):
    _, tr = env
    with tr.trace("ask") as t:
        with t.generation("a", "big", "p"):
            pass
        with t.generation("b", "big", "p") as g:
            g.finish("x", {"prompt_tokens": 1})
            with pytest.raises(RuntimeError):
                g.finish("y", {})
    gens = tr.traces[0]["spans"]
    assert (gens[0]["cost"], gens[0]["prompt_tokens"], gens[0]["ttft"], gens[0]["output_chars"]) == (0.0, 0, None, 0)
    assert gens[1]["prompt_tokens"] == 1 and gens[1]["completion_tokens"] == 0


def test_unknown_model_has_no_cost_and_is_not_counted(env):
    _, tr = env
    with tr.trace("ask") as t:
        with t.generation("a", "mystery", "p") as g:
            g.finish("x", {"prompt_tokens": 10, "completion_tokens": 5})
        with t.generation("b", "small", "p") as g:
            g.finish("x", {"prompt_tokens": 1000, "completion_tokens": 500})
    done = tr.traces[0]
    assert done["spans"][0]["cost"] is None and done["spans"][1]["cost"] == 0.0003
    assert done["cost"] == 0.0003 and done["tokens"] == 1515


def test_generation_nested_in_a_span_and_errors(env):
    clock, tr = env
    with pytest.raises(TimeoutError):
        with tr.trace("ask") as t:
            with t.span("pipeline"):
                with t.generation("a", "big", "p"):
                    clock.now += 3
                    raise TimeoutError("llm timeout")
    spans = tr.traces[0]["spans"]
    assert spans[1]["parent"] == "s1" and spans[1]["status"] == "error" and spans[1]["error"] == "TimeoutError: llm timeout"
    assert spans[0]["status"] == "error" and tr.traces[0]["status"] == "error"


# ---------- report ---------------------------------------------------------------------------------------------------------------------


def run(tr, clock, name, user, duration, model="big", p=1000, c=500, fail=False):
    try:
        with tr.trace(name, user=user) as t:
            with t.generation("g", model, "prompt") as g:
                g.finish("out", {"prompt_tokens": p, "completion_tokens": c})
            clock.now += duration
            if fail:
                raise RuntimeError("x")
    except RuntimeError:
        pass


def test_report(env):
    clock, tr = env
    run(tr, clock, "a", "ann", 1.0)
    run(tr, clock, "b", "ann", 2.0, model="small")
    run(tr, clock, "c", "bob", 4.0, fail=True)
    run(tr, clock, "d", None, 0.5)
    r = tr.report()
    assert r["traces"] == 4 and r["errors"] == 1 and r["error_rate"] == 0.25
    assert r["latency"] == {"p50": 1.0, "p95": 4.0}
    assert r["cost"] == round(0.0105 * 3 + 0.0003, 6) and r["tokens"] == 6000
    assert r["by_model"] == {"big": {"calls": 3, "cost": 0.0315, "prompt_tokens": 3000, "completion_tokens": 1500},
                             "small": {"calls": 1, "cost": 0.0003, "prompt_tokens": 1000, "completion_tokens": 500}}
    assert r["by_user"] == {"ann": {"traces": 2, "cost": 0.0108}, "bob": {"traces": 1, "cost": 0.0105}}
    assert r["slowest"] == ["t3", "t2", "t1"]


def test_percentiles_use_nearest_rank():
    clock = Clock()
    tr = LlmTracer(clock, PRICES)
    for d in (5, 1, 4, 2, 3, 10, 9, 8, 7, 6):
        with tr.trace("x"):
            clock.now += d
    assert tr.report()["latency"] == {"p50": 5, "p95": 10}
    single = LlmTracer(clock, PRICES)
    with single.trace("x"):
        clock.now += 2
    assert single.report()["latency"] == {"p50": 2, "p95": 2}


def test_empty_report(env):
    _, tr = env
    assert tr.report() == {"traces": 0, "errors": 0, "error_rate": 0.0, "latency": {"p50": None, "p95": None}, "cost": 0.0, "tokens": 0,
                           "by_model": {}, "by_user": {}, "slowest": []}


def test_slowest_ties_are_ordered_by_id(env):
    clock, tr = env
    for _ in range(5):
        with tr.trace("x"):
            clock.now += 1
    assert tr.report()["slowest"] == ["t1", "t2", "t3"]
    with tr.trace("slow"):
        clock.now += 9
    assert tr.report()["slowest"][0] == "t6"
