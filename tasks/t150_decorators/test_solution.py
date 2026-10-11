import asyncio
import inspect

import pytest

from solution import observed


class FakeClock:
    def __init__(self, *ticks):
        self.ticks = list(ticks)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.ticks.pop(0)


def make(clock=None, **kw):
    events = []
    return events, dict(clock=clock or FakeClock(0.0, 1.0), sink=events.append, **kw)


# --- два способи вживання ----------------------------------------------------------------------

def test_with_parameters():
    events, kw = make(FakeClock(10.0, 12.5))

    @observed(**kw)
    def add(a, b=1):
        return a + b

    assert add(2, b=3) == 5
    assert events == [{"name": add.__qualname__, "seconds": 2.5, "ok": True, "error": None}]


def test_without_parentheses_works_and_does_not_crash():
    @observed
    def f(x):
        return x * 2

    assert f(4) == 8  # sink за замовчуванням нічого не робить


def test_empty_parentheses():
    @observed()
    def f():
        return 1

    assert f() == 1


def test_custom_name():
    events, kw = make(name="checkout")

    @observed(**kw)
    def f():
        pass

    f()
    assert events[0]["name"] == "checkout"


def test_default_name_is_qualname_of_the_wrapped_function():
    events, kw = make()

    class Service:
        @observed(**kw)
        def run(self):
            pass

    Service().run()
    assert events[0]["name"].endswith("Service.run")
    assert "<locals>" in events[0]["name"]


# --- метадані ----------------------------------------------------------------------------------

def test_metadata_is_preserved():
    @observed
    def documented(a: int, b: str = "x", *args, key=None, **kw) -> str:
        """Опис."""
        return b

    assert documented.__name__ == "documented"
    assert documented.__doc__ == "Опис."
    assert documented.__module__ == __name__
    assert documented.__qualname__.endswith("documented")
    assert inspect.signature(documented) == inspect.signature(documented.__wrapped__)
    assert list(inspect.signature(documented).parameters) == ["a", "b", "args", "key", "kw"]


def test_wrapped_is_the_original_function():
    def original():
        return 1

    wrapped = observed(original)
    assert wrapped.__wrapped__ is original


# --- вимірювання ---------------------------------------------------------------------------------

def test_exactly_one_clock_call_before_and_one_after():
    clock = FakeClock(0.0, 3.0)
    events, kw = make(clock)

    @observed(**kw)
    def f():
        pass

    f()
    assert clock.calls == 2
    assert len(events) == 1


def test_clock_is_read_before_and_after_the_call():
    order = []
    clock = FakeClock(0.0, 1.0)

    def tracking_clock():
        order.append("clock")
        return clock()

    @observed(clock=tracking_clock, sink=lambda e: order.append("sink"))
    def f():
        order.append("body")

    f()
    assert order == ["clock", "body", "clock", "sink"]


def test_each_call_is_reported_separately():
    events, kw = make(FakeClock(0, 1, 10, 14))

    @observed(**kw)
    def f():
        pass

    f()
    f()
    assert [e["seconds"] for e in events] == [1, 4]


def test_exception_is_reported_and_the_same_object_is_raised():
    events, kw = make(FakeClock(0, 2))
    boom = ValueError("boom")

    @observed(**kw)
    def f():
        raise boom

    with pytest.raises(ValueError) as info:
        f()
    assert info.value is boom
    assert events == [{"name": f.__qualname__, "seconds": 2, "ok": False, "error": "ValueError"}]


def test_traceback_still_points_to_the_original_function():
    @observed
    def inner_fail():
        raise RuntimeError("x")

    with pytest.raises(RuntimeError) as info:
        inner_fail()
    frames = [f.name for f in __import__("traceback").extract_tb(info.value.__traceback__)]
    assert "inner_fail" in frames


def test_failing_sink_does_not_mask_the_result():
    def bad_sink(event):
        raise RuntimeError("sink down")

    @observed(clock=FakeClock(0, 1), sink=bad_sink)
    def f():
        return "result"

    assert f() == "result"


def test_failing_sink_does_not_replace_the_original_exception():
    def bad_sink(event):
        raise RuntimeError("sink down")

    @observed(clock=FakeClock(0, 1), sink=bad_sink)
    def f():
        raise KeyError("original")

    with pytest.raises(KeyError):
        f()


# --- методи ----------------------------------------------------------------------------------------

def test_works_on_instance_methods_classmethods_and_staticmethods():
    events, kw = make(FakeClock(*range(10)))

    class C:
        def __init__(self):
            self.x = 5

        @observed(**kw)
        def inst(self, k):
            return self.x * k

        @classmethod
        @observed(**kw)
        def cls(cls):
            return cls.__name__

        @staticmethod
        @observed(**kw)
        def stat(v):
            return v + 1

    c = C()
    assert c.inst(2) == 10
    assert C.cls() == "C"
    assert C.stat(1) == 2
    assert len(events) == 3


# --- async -----------------------------------------------------------------------------------------

def test_async_function_is_still_a_coroutine_function():
    @observed
    async def a():
        return 1

    @observed
    def s():
        return 1

    assert inspect.iscoroutinefunction(a)
    assert not inspect.iscoroutinefunction(s)


def test_async_time_covers_the_whole_coroutine():
    events, kw = make(FakeClock(0.0, 5.0))

    @observed(**kw)
    async def work(x):
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        return x * 2

    assert asyncio.run(work(21)) == 42
    assert events == [{"name": work.__qualname__, "seconds": 5.0, "ok": True, "error": None}]


def test_async_event_is_not_emitted_until_awaited():
    events, kw = make()

    @observed(**kw)
    async def work():
        return 1

    coro = work()
    assert events == []
    assert asyncio.run(coro) == 1
    assert len(events) == 1


def test_async_exception():
    events, kw = make(FakeClock(0, 1))

    @observed(**kw)
    async def work():
        await asyncio.sleep(0)
        raise LookupError("nope")

    with pytest.raises(LookupError):
        asyncio.run(work())
    assert events[0]["ok"] is False and events[0]["error"] == "LookupError"


def test_async_cancellation_is_recorded_and_propagates():
    events, kw = make(FakeClock(0, 1))

    @observed(**kw)
    async def slow():
        await asyncio.sleep(10)

    async def main():
        task = asyncio.ensure_future(slow())
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(main())
    assert events[0]["ok"] is False and events[0]["error"] == "CancelledError"


def test_concurrent_calls_are_measured_independently():
    ticks = iter([0, 100, 1, 3, 2, 4, 5, 6, 7, 8, 9, 10])
    events = []

    @observed(clock=lambda: next(ticks), sink=events.append)
    async def work(delay):
        await asyncio.sleep(delay)
        return delay

    async def main():
        return await asyncio.gather(work(0.02), work(0.01))

    assert asyncio.run(main()) == [0.02, 0.01]
    assert len(events) == 2
