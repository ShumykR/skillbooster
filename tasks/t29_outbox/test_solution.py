import json
import sqlite3

import pytest

from solution import SCHEMA, place_order, relay


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.executescript(SCHEMA)
    return c


def counts(c):
    return (
        c.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
        c.execute("SELECT COUNT(*) FROM outbox").fetchone()[0],
    )


def test_order_and_event_saved_together(conn):
    place_order(conn, 1, 99.5)
    assert counts(conn) == (1, 1)
    topic, payload = conn.execute("SELECT topic, payload FROM outbox").fetchone()
    assert topic == "order.created"
    assert json.loads(payload) == {"order_id": 1, "total": 99.5}


def test_crash_between_writes_is_atomic(conn):
    def boom():
        raise RuntimeError("process died")

    with pytest.raises(RuntimeError):
        place_order(conn, 1, 10, _crash=boom)
    assert counts(conn) == (0, 0), "або обидва записи, або жодного"


def test_relay_publishes_in_order_and_marks_sent(conn):
    for i in (1, 2, 3):
        place_order(conn, i, i * 10)
    sent = []
    assert relay(conn, lambda topic, payload, eid: sent.append((eid, json.loads(payload)["order_id"]))) == 3
    assert [order for _, order in sent] == [1, 2, 3]
    assert [eid for eid, _ in sent] == sorted(eid for eid, _ in sent)
    assert conn.execute("SELECT COUNT(*) FROM outbox WHERE sent_at IS NULL").fetchone()[0] == 0


def test_relay_is_idempotent_when_nothing_new(conn):
    place_order(conn, 1, 10)
    relay(conn, lambda *a: None)
    sent = []
    assert relay(conn, lambda *a: sent.append(a)) == 0
    assert sent == []


def test_publish_failure_keeps_unsent_and_retry_delivers(conn):
    for i in (1, 2, 3):
        place_order(conn, i, i)
    delivered = []

    def flaky(topic, payload, eid):
        if json.loads(payload)["order_id"] == 2:
            raise ConnectionError("broker down")
        delivered.append(json.loads(payload)["order_id"])

    with pytest.raises(ConnectionError):
        relay(conn, flaky)
    assert delivered == [1]
    unsent = conn.execute("SELECT COUNT(*) FROM outbox WHERE sent_at IS NULL").fetchone()[0]
    assert unsent == 2

    assert relay(conn, lambda t, p, e: delivered.append(json.loads(p)["order_id"])) == 2
    assert delivered == [1, 2, 3], "порядок має зберігатися, повторів немає"


def test_event_id_is_stable_for_consumer_dedup(conn):
    place_order(conn, 1, 10)
    ids = []

    def fail_once(topic, payload, eid):
        ids.append(eid)
        if len(ids) == 1:
            raise ConnectionError

    with pytest.raises(ConnectionError):
        relay(conn, fail_once)
    relay(conn, fail_once)
    assert len(ids) == 2 and ids[0] == ids[1], "повторна доставка має мати той самий event_id"
