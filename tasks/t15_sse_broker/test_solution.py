import pytest

from solution import Event, EventBroker, format_sse, heartbeat


def drain(sub):
    out = []
    while (e := sub.get_nowait()) is not None:
        out.append(e)
    return out


def ids(events):
    return [e.id for e in events]


# ---------- публікація і підписка ---------------------------------------------


def test_ids_start_at_one_and_grow():
    b = EventBroker()
    assert [b.publish("a").id, b.publish("b").id, b.publish("c", event="tick").id] == [1, 2, 3]


def test_live_subscriber_gets_only_new_events_in_order():
    b = EventBroker()
    b.publish("before")
    sub = b.subscribe()
    b.publish("x")
    b.publish("y", event="tick")
    events = drain(sub)
    assert [(e.id, e.data, e.event) for e in events] == [(2, "x", "message"), (3, "y", "tick")]
    assert not sub.needs_resync and not sub.closed
    assert sub.get_nowait() is None


def test_each_subscriber_has_its_own_queue():
    b = EventBroker()
    s1, s2 = b.subscribe(), b.subscribe()
    b.publish("x")
    assert ids(drain(s1)) == [1]
    assert ids(drain(s2)) == [1]
    assert b.subscriber_count() == 2


def test_unsubscribe_is_idempotent_and_stops_delivery():
    b = EventBroker()
    sub = b.subscribe()
    b.unsubscribe(sub)
    b.unsubscribe(sub)
    b.publish("x")
    assert drain(sub) == []
    assert b.subscriber_count() == 0


def test_publish_without_subscribers_works():
    assert EventBroker().publish("x").id == 1


# ---------- реконект з Last-Event-ID ------------------------------------------


def test_reconnect_replays_missed_events_then_continues_live():
    b = EventBroker()
    for i in range(5):
        b.publish(f"m{i}")
    sub = b.subscribe(last_event_id=2)
    b.publish("live")
    assert ids(drain(sub)) == [3, 4, 5, 6]
    assert not sub.needs_resync


def test_reconnect_with_latest_id_replays_nothing():
    b = EventBroker()
    b.publish("a")
    sub = b.subscribe(last_event_id=1)
    assert drain(sub) == [] and not sub.needs_resync


def test_reconnect_when_history_no_longer_has_everything_needs_resync():
    b = EventBroker(history=3, max_queue=10)
    for i in range(10):  # в історії лишаються id 8, 9, 10
        b.publish(f"m{i}")
    sub = b.subscribe(last_event_id=4)
    assert sub.needs_resync
    assert ids(drain(sub)) == [8, 9, 10]


def test_reconnect_right_at_history_edge_does_not_need_resync():
    b = EventBroker(history=3, max_queue=10)
    for i in range(10):
        b.publish(f"m{i}")
    sub = b.subscribe(last_event_id=7)  # пропущено 8, 9, 10: усе ще в історії
    assert not sub.needs_resync
    assert ids(drain(sub)) == [8, 9, 10]


def test_replay_larger_than_queue_keeps_newest_and_needs_resync():
    b = EventBroker(history=100, max_queue=4)
    for i in range(20):
        b.publish(f"m{i}")
    sub = b.subscribe(last_event_id=0)
    assert sub.needs_resync
    assert ids(drain(sub)) == [17, 18, 19, 20]


def test_last_event_id_from_the_future_needs_resync():
    b = EventBroker()
    b.publish("a")
    sub = b.subscribe(last_event_id=999)
    assert sub.needs_resync and drain(sub) == []


# ---------- backpressure ------------------------------------------------------


def test_slow_subscriber_is_dropped_without_affecting_others():
    b = EventBroker(max_queue=3)
    slow, fast = b.subscribe(), b.subscribe()
    for i in range(3):
        b.publish(f"m{i}")
        drain(fast)
    assert not slow.closed and slow.pending() == 3
    b.publish("overflow")  # черга slow повна
    assert slow.closed and slow.close_reason == "slow"
    assert b.subscriber_count() == 1
    assert ids(drain(fast)) == [4]
    assert ids(drain(slow)) == [1, 2, 3], "вже поставлене в чергу ще можна дочитати"
    b.publish("later")
    assert ids(drain(slow)) == []
    assert slow.pending() == 0


def test_queue_never_exceeds_limit():
    b = EventBroker(max_queue=5)
    sub = b.subscribe()
    for i in range(1000):
        b.publish("x")
    assert sub.pending() <= 5


def test_slow_client_can_catch_up_after_reconnect():
    b = EventBroker(history=50, max_queue=3)
    slow = b.subscribe()
    for i in range(10):
        b.publish(f"m{i}")
    assert slow.closed
    last_seen = drain(slow)[-1].id  # 3
    again = b.subscribe(last_event_id=last_seen)
    assert again.needs_resync, "повтор не вміщається в чергу, тож клієнт мусить перезавантажити стан"
    assert ids(drain(again)) == [8, 9, 10]


# ---------- формат SSE --------------------------------------------------------


def test_format_basic_and_named_event():
    assert format_sse(Event(7, "hello")) == "id: 7\ndata: hello\n\n"
    assert format_sse(Event(8, "x", event="tick")) == "id: 8\nevent: tick\ndata: x\n\n"


def test_format_multiline_data_and_empty_data():
    assert format_sse(Event(1, "a\nb\r\nc")) == "id: 1\ndata: a\ndata: b\ndata: c\n\n"
    assert format_sse(Event(2, "")) == "id: 2\ndata: \n\n"


def test_format_prevents_field_injection():
    out = format_sse(Event(1, "hi\nevent: admin\nid: 999"))
    assert "\nevent: admin" not in out.replace("data: event: admin", "")
    assert out == "id: 1\ndata: hi\ndata: event: admin\ndata: id: 999\n\n"
    for bad in ("tick\nid: 5", "tick\rx"):
        with pytest.raises(ValueError):
            format_sse(Event(1, "x", event=bad))


def test_heartbeat_is_a_comment():
    assert heartbeat() == ": keep-alive\n\n"
