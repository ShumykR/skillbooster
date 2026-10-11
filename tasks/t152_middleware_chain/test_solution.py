import threading

import pytest

from solution import build_pipeline


def tracer(name, log):
    def mw(request, call_next):
        log.append(f"{name}:in")
        response = call_next(request)
        log.append(f"{name}:out")
        return response
    return mw


def test_no_middleware_calls_handler_directly():
    assert build_pipeline([], lambda r: r.upper())("abc") == "ABC"


def test_first_middleware_is_outermost():
    log = []
    pipe = build_pipeline([tracer("a", log), tracer("b", log), tracer("c", log)], lambda r: log.append("handler") or "ok")
    assert pipe("req") == "ok"
    assert log == ["a:in", "b:in", "c:in", "handler", "c:out", "b:out", "a:out"]


def test_middleware_can_modify_request_for_next_links():
    seen = []

    def add_user(request, call_next):
        return call_next({**request, "user": "ann"})

    def spy(request, call_next):
        seen.append(request)
        return call_next(request)

    pipe = build_pipeline([add_user, spy], lambda r: r["user"])
    assert pipe({"path": "/"}) == "ann"
    assert seen == [{"path": "/", "user": "ann"}]


def test_middleware_can_modify_response():
    def shout(request, call_next):
        return call_next(request).upper() + "!"

    def wrap(request, call_next):
        return f"[{call_next(request)}]"

    assert build_pipeline([wrap, shout], lambda r: "hi")("x") == "[HI!]"


def test_short_circuit_skips_the_rest_including_handler():
    log = []

    def gate(request, call_next):
        return "denied"

    pipe = build_pipeline([tracer("a", log), gate, tracer("b", log)], lambda r: log.append("handler") or "ok")
    assert pipe("req") == "denied"
    assert log == ["a:in", "a:out"]


def test_middleware_can_catch_exceptions_from_later_links():
    def guard(request, call_next):
        try:
            return call_next(request)
        except ValueError as exc:
            return f"error:{exc}"

    def bad_handler(request):
        raise ValueError("boom")

    assert build_pipeline([guard], bad_handler)("x") == "error:boom"


def test_unhandled_exception_propagates_unchanged():
    boom = RuntimeError("boom")

    def handler(request):
        raise boom

    log = []
    pipe = build_pipeline([tracer("a", log)], handler)
    with pytest.raises(RuntimeError) as info:
        pipe("x")
    assert info.value is boom
    assert log == ["a:in"]  # «out» не виконався, бо виняток пролетів повз


def test_exception_in_middleware_before_call_next():
    def broken(request, call_next):
        raise KeyError("early")

    log = []
    pipe = build_pipeline([broken, tracer("b", log)], lambda r: "ok")
    with pytest.raises(KeyError):
        pipe("x")
    assert log == []


def test_call_next_twice_is_an_error():
    def twice(request, call_next):
        call_next(request)
        return call_next(request)

    calls = []
    pipe = build_pipeline([twice], lambda r: calls.append(1) or "ok")
    with pytest.raises(RuntimeError, match="twice"):
        pipe("x")
    assert calls == [1]


def test_call_next_twice_is_detected_for_inner_links_too():
    def twice(request, call_next):
        call_next(request)
        return call_next(request)

    pipe = build_pipeline([lambda r, n: n(r), twice, lambda r, n: n(r)], lambda r: "ok")
    with pytest.raises(RuntimeError):
        pipe("x")


def test_pipeline_is_reusable_after_short_circuit():
    def gate(request, call_next):
        return "denied" if request == "bad" else call_next(request)

    log = []
    pipe = build_pipeline([gate, tracer("t", log)], lambda r: "ok")
    assert pipe("bad") == "denied"
    assert pipe("good") == "ok"
    assert pipe("bad") == "denied"
    assert pipe("good") == "ok"
    assert log == ["t:in", "t:out", "t:in", "t:out"]


def test_pipeline_is_reusable_after_exception():
    def handler(request):
        if request == "bad":
            raise ValueError
        return "ok"

    pipe = build_pipeline([lambda r, n: n(r), lambda r, n: n(r)], handler)
    with pytest.raises(ValueError):
        pipe("bad")
    assert pipe("fine") == "ok"
    assert pipe("fine") == "ok"


def test_pipeline_is_reentrant():
    # handler сам викликає той самий pipeline (вкладений прохід)
    holder = {}

    def handler(request):
        return request if request == 0 else holder["pipe"](request - 1) + 1

    holder["pipe"] = build_pipeline([lambda r, n: n(r)], handler)
    assert holder["pipe"](3) == 3


def test_concurrent_requests_do_not_interfere():
    errors = []
    gate = threading.Barrier(8)

    def slow(request, call_next):
        gate.wait(timeout=5)
        return call_next(request)

    pipe = build_pipeline([lambda r, n: n(r), slow, lambda r, n: n(r)], lambda r: r * 2)

    def work(i):
        try:
            assert pipe(i) == i * 2
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(i,)) for i in range(8)]
    [t.start() for t in threads]
    [t.join(10) for t in threads]
    assert errors == []


def test_middleware_list_is_copied():
    log = []
    mws = [tracer("a", log)]
    pipe = build_pipeline(mws, lambda r: "ok")
    mws.append(tracer("late", log))
    mws.clear()
    pipe("x")
    assert log == ["a:in", "a:out"]


@pytest.mark.parametrize("bad", [None, 5, "mw"])
def test_non_callable_middleware_fails_at_build_time(bad):
    with pytest.raises(TypeError):
        build_pipeline([lambda r, n: n(r), bad], lambda r: r)


def test_accepts_tuple_and_generator_of_middlewares():
    log = []
    assert build_pipeline((tracer("a", log),), lambda r: 1)("x") == 1
    assert build_pipeline((tracer(n, log) for n in "xy"), lambda r: 2)("x") == 2
    assert log == ["a:in", "a:out", "x:in", "y:in", "y:out", "x:out"]


def test_each_link_receives_its_own_call_next():
    nexts = []

    def collect(request, call_next):
        nexts.append(call_next)
        return call_next(request)

    pipe = build_pipeline([collect, collect], lambda r: "ok")
    pipe("x")
    assert nexts[0] is not nexts[1]
