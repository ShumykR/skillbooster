import pytest

from solution import EventBus


class Event:
    pass


class UserEvent(Event):
    pass


class UserCreated(UserEvent):
    pass


class Other:
    pass


@pytest.fixture
def bus():
    return EventBus()


def test_handler_receives_the_event_object(bus):
    got = []
    bus.subscribe(UserCreated, got.append)
    e = UserCreated()
    bus.publish(e)
    assert got == [e]


def test_event_without_subscribers_is_fine(bus):
    bus.publish(Other())


def test_only_matching_type_is_called(bus):
    got = []
    bus.subscribe(UserCreated, lambda e: got.append("created"))
    bus.publish(Other())
    bus.publish(UserEvent())  # батько не доставляється підписникам нащадка
    assert got == []


def test_base_class_handlers_get_subclass_events(bus):
    got = []
    bus.subscribe(UserEvent, lambda e: got.append("user"))
    bus.subscribe(Event, lambda e: got.append("event"))
    bus.publish(UserCreated())
    assert sorted(got) == ["event", "user"]


def test_order_is_exact_type_then_bases_then_subscription_order(bus):
    got = []
    bus.subscribe(Event, lambda e: got.append("event-1"))
    bus.subscribe(UserEvent, lambda e: got.append("user-1"))
    bus.subscribe(UserCreated, lambda e: got.append("created-1"))
    bus.subscribe(UserCreated, lambda e: got.append("created-2"))
    bus.subscribe(UserEvent, lambda e: got.append("user-2"))
    bus.publish(UserCreated())
    assert got == ["created-1", "created-2", "user-1", "user-2", "event-1"]


def test_object_subscription_is_not_a_catch_all(bus):
    got = []
    bus.subscribe(object, got.append)
    bus.publish(Other())
    assert got == []


def test_unsubscribe(bus):
    got = []
    off = bus.subscribe(Other, got.append)
    bus.publish(Other())
    off()
    bus.publish(Other())
    assert len(got) == 1
    off()  # повторно: нічого не відбувається
    assert bus.handlers_count(Other) == 0


def test_same_handler_twice_is_two_subscriptions(bus):
    got = []
    off1 = bus.subscribe(Other, got.append)
    bus.subscribe(Other, got.append)
    bus.publish(Other())
    assert len(got) == 2
    off1()
    got.clear()
    bus.publish(Other())
    assert len(got) == 1  # відписалась лише перша підписка


def test_handlers_count_is_per_exact_type(bus):
    bus.subscribe(Event, lambda e: None)
    bus.subscribe(UserEvent, lambda e: None)
    bus.subscribe(UserEvent, lambda e: None)
    assert bus.handlers_count(UserEvent) == 2
    assert bus.handlers_count(Event) == 1
    assert bus.handlers_count(UserCreated) == 0


@pytest.mark.parametrize("bad_type", ["UserEvent", 5, None, UserEvent()])
def test_event_type_must_be_a_class(bus, bad_type):
    with pytest.raises(TypeError):
        bus.subscribe(bad_type, lambda e: None)


@pytest.mark.parametrize("bad_handler", [None, 5, "f"])
def test_handler_must_be_callable(bus, bad_handler):
    with pytest.raises(TypeError):
        bus.subscribe(Other, bad_handler)


# --- знімок -------------------------------------------------------------------------------------

def test_handler_unsubscribing_itself_does_not_skip_the_next_one(bus):
    got = []
    offs = []

    def first(e):
        got.append("first")
        offs[0]()

    offs.append(bus.subscribe(Other, first))
    bus.subscribe(Other, lambda e: got.append("second"))
    bus.subscribe(Other, lambda e: got.append("third"))
    bus.publish(Other())
    assert got == ["first", "second", "third"]
    got.clear()
    bus.publish(Other())
    assert got == ["second", "third"]


def test_handler_unsubscribing_a_later_one_still_runs_it_this_time(bus):
    got = []
    holder = {}

    def killer(e):
        got.append("killer")
        holder["off"]()

    bus.subscribe(Other, killer)
    holder["off"] = bus.subscribe(Other, lambda e: got.append("victim"))
    bus.publish(Other())
    assert got == ["killer", "victim"]
    got.clear()
    bus.publish(Other())
    assert got == ["killer"]


def test_handler_subscribing_new_one_takes_effect_next_publish(bus):
    got = []

    def adder(e):
        got.append("adder")
        if len(got) == 1:
            bus.subscribe(Other, lambda e2: got.append("late"))

    bus.subscribe(Other, adder)
    bus.publish(Other())
    assert got == ["adder"]
    bus.publish(Other())
    assert got == ["adder", "adder", "late"]


def test_nested_publish_works(bus):
    got = []
    bus.subscribe(Other, lambda e: (got.append("outer"), bus.publish(UserCreated())))
    bus.subscribe(UserCreated, lambda e: got.append("inner"))
    bus.publish(Other())
    assert got == ["outer", "inner"]


# --- помилки ---------------------------------------------------------------------------------

def test_failing_handler_does_not_stop_others_and_errors_are_grouped(bus):
    got = []

    def bad1(e):
        raise ValueError("one")

    def bad2(e):
        raise KeyError("two")

    bus.subscribe(Other, lambda e: got.append("a"))
    bus.subscribe(Other, bad1)
    bus.subscribe(Other, lambda e: got.append("b"))
    bus.subscribe(Other, bad2)
    bus.subscribe(Other, lambda e: got.append("c"))
    with pytest.raises(ExceptionGroup) as info:
        bus.publish(Other())
    assert got == ["a", "b", "c"]
    errors = info.value.exceptions
    assert [type(x) for x in errors] == [ValueError, KeyError]


def test_errors_from_base_class_handlers_are_included(bus):
    def bad(e):
        raise RuntimeError("base")

    bus.subscribe(Event, bad)
    bus.subscribe(UserCreated, lambda e: (_ for _ in ()).throw(ValueError("exact")))
    with pytest.raises(ExceptionGroup) as info:
        bus.publish(UserCreated())
    assert [type(x) for x in info.value.exceptions] == [ValueError, RuntimeError]


def test_no_exception_group_when_all_succeed(bus):
    bus.subscribe(Other, lambda e: None)
    assert bus.publish(Other()) is None


def test_failed_handler_stays_subscribed(bus):
    calls = []

    def flaky(e):
        calls.append(1)
        raise ValueError

    bus.subscribe(Other, flaky)
    for _ in range(2):
        with pytest.raises(ExceptionGroup):
            bus.publish(Other())
    assert len(calls) == 2
