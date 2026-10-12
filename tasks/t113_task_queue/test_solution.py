import pytest

from solution import TaskQueue, consume_once, process


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def env():
    clock = Clock()
    return clock, TaskQueue(clock, visibility_timeout=30, max_attempts=3)


# ---------- basics ---------------------------------------------------------------


def test_fifo_delivery_with_attempt_and_receipts(env):
    clock, q = env
    ids = [q.enqueue(f"job{i}") for i in range(3)]
    assert ids == ["t1", "t2", "t3"]
    got = q.receive(2)
    assert [(d["id"], d["payload"], d["attempt"], d["receipt"]) for d in got] == [("t1", "job0", 1, "r1"), ("t2", "job1", 1, "r2")]
    assert q.stats() == {"ready": 1, "delayed": 0, "in_flight": 2, "dead": 0}
    assert [d["id"] for d in q.receive(5)] == ["t3"]
    assert q.receive() == []


def test_ack_removes_the_task(env):
    clock, q = env
    q.enqueue("a")
    d = q.receive()[0]
    assert q.ack(d["receipt"]) is True
    assert q.ack(d["receipt"]) is False, "повторне підтвердження"
    clock.now += 1000
    assert q.receive() == [] and q.stats() == {"ready": 0, "delayed": 0, "in_flight": 0, "dead": 0}


def test_unknown_receipt(env):
    _, q = env
    assert q.ack("nope") is False and q.nack("nope") is False and q.extend("nope", 5) is False


# ---------- at-least-once: visibility timeout ------------------------------------


def test_unacknowledged_task_is_redelivered_after_visibility_timeout(env):
    clock, q = env
    q.enqueue("a")
    first = q.receive()[0]
    clock.now += 29.99
    assert q.receive() == []
    clock.now += 0.01
    second = q.receive()[0]
    assert second["id"] == first["id"] and second["attempt"] == 2 and second["receipt"] != first["receipt"]
    assert q.ack(first["receipt"]) is False, "застарілий receipt після повторної видачі"
    assert q.ack(second["receipt"]) is True


def test_late_ack_is_rejected(env):
    clock, q = env
    q.enqueue("a")
    d = q.receive()[0]
    clock.now += 30
    assert q.ack(d["receipt"]) is False
    assert q.receive()[0]["attempt"] == 2


def test_ack_just_before_the_deadline_works(env):
    clock, q = env
    q.enqueue("a")
    d = q.receive()[0]
    clock.now += 29.99
    assert q.ack(d["receipt"]) is True


def test_extend_keeps_a_long_job_invisible(env):
    clock, q = env
    q.enqueue("a")
    d = q.receive()[0]
    clock.now += 10
    assert q.extend(d["receipt"], 60) is True
    clock.now += 59.99
    assert q.receive() == []
    clock.now += 0.01
    assert q.receive()[0]["attempt"] == 2


def test_extend_after_expiry_fails_and_validates_seconds(env):
    clock, q = env
    q.enqueue("a")
    d = q.receive()[0]
    with pytest.raises(ValueError):
        q.extend(d["receipt"], 0)
    clock.now += 30
    assert q.extend(d["receipt"], 60) is False


# ---------- retries, dead-letter -------------------------------------------------


def test_task_goes_to_dead_letter_after_max_attempts(env):
    clock, q = env
    q.enqueue({"x": 1})
    for attempt in (1, 2, 3):
        assert q.receive()[0]["attempt"] == attempt
        clock.now += 30
    assert q.receive() == []
    assert q.dead_letters() == [{"id": "t1", "payload": {"x": 1}, "attempts": 3}]
    assert q.stats() == {"ready": 0, "delayed": 0, "in_flight": 0, "dead": 1}


def test_nack_with_delay_and_dead_letter_on_last_attempt(env):
    clock, q = env
    q.enqueue("a")
    d = q.receive()[0]
    assert q.nack(d["receipt"], delay=5) is True
    assert q.stats()["delayed"] == 1 and q.receive() == []
    clock.now += 4.99
    assert q.receive() == []
    clock.now += 0.01
    d2 = q.receive()[0]
    assert d2["attempt"] == 2
    q.nack(d2["receipt"])
    d3 = q.receive()[0]
    assert d3["attempt"] == 3
    assert q.nack(d3["receipt"]) is True
    assert q.stats()["dead"] == 1 and q.receive() == []


def test_dead_letters_keep_the_order_of_death(env):
    clock, q = env
    q.enqueue("first")
    q.enqueue("second")
    for _ in range(3):
        for d in q.receive(2):
            if d["id"] == "t2":
                q.nack(d["receipt"])
        clock.now += 30
    # t2 помер першим (nack на третій спробі), t1 після завершення таймаутів
    assert [d["id"] for d in q.dead_letters()] == ["t2", "t1"]


def test_redrive_returns_a_dead_task_with_fresh_attempts(env):
    clock, q = env
    q.enqueue("a")
    for _ in range(3):
        q.receive()
        clock.now += 30
    assert q.stats()["dead"] == 1
    assert q.redrive("t1") is True
    assert q.dead_letters() == []
    assert q.receive()[0]["attempt"] == 1
    assert q.redrive("t1") is False, "уже не в dead-letter"
    assert q.redrive("zzz") is False


# ---------- ordering and delay -----------------------------------------------------


def test_enqueue_delay(env):
    clock, q = env
    q.enqueue("late", delay=10)
    q.enqueue("now")
    assert [d["payload"] for d in q.receive(5)] == ["now"]
    clock.now += 10
    assert [d["payload"] for d in q.receive(5)] == ["late"]
    with pytest.raises(ValueError):
        q.enqueue("bad", delay=-1)


def test_order_is_by_available_time_then_creation(env):
    clock, q = env
    q.enqueue("delayed", delay=100)     # t1, доступне через 100
    q.enqueue("will-retry")             # t2
    q.receive()                         # t2 у польоті до +30
    clock.now += 100
    assert [d["payload"] for d in q.receive(5)] == ["will-retry", "delayed"], "t2 доступне з +30, t1 з +100"


# ---------- idempotent producer ------------------------------------------------------


def test_enqueue_key_deduplicates_active_tasks(env):
    _, q = env
    a = q.enqueue("pay", key="order-1")
    assert q.enqueue("pay again", key="order-1") == a
    assert q.enqueue("other", key="order-2") != a
    assert q.enqueue("no key") != q.enqueue("no key")
    assert q.stats()["ready"] == 4
    d = q.receive()[0]
    assert q.enqueue("pay", key="order-1") == a, "завдання в польоті ще активне"
    q.ack(d["receipt"])
    again = q.enqueue("pay", key="order-1")
    assert again != a, "після підтвердження ключ вільний"


def test_key_is_released_when_the_task_dies(env):
    clock, q = env
    first = q.enqueue("a", key="k")
    for _ in range(3):
        q.receive()
        clock.now += 30
    assert q.stats()["dead"] == 1
    assert q.enqueue("a", key="k") != first
    assert q.redrive(first) is True, "redrive працює, навіть якщо ключ зайняли"


# ---------- process and consume_once -------------------------------------------------


def test_process_acks_successes_and_nacks_failures_with_backoff(env):
    clock, q = env
    q.enqueue("ok")
    q.enqueue("bad")

    def handler(payload):
        if payload == "bad":
            raise RuntimeError("boom")

    assert process(q, handler, n=5) == [("t1", "done"), ("t2", "retry")]
    assert q.stats()["delayed"] == 1
    clock.now += 0.99
    assert process(q, handler) == []
    clock.now += 0.01
    assert process(q, handler) == [("t2", "retry")]       # attempt 2: затримка 2 с
    clock.now += 1.99
    assert process(q, handler) == []
    clock.now += 0.01
    assert process(q, handler) == [("t2", "dead")]       # attempt 3: dead-letter
    assert q.dead_letters()[0]["id"] == "t2"


def test_backoff_is_capped(env):
    clock, q = env
    q.enqueue("bad")

    def handler(payload):
        raise RuntimeError

    process(q, handler, backoff_base=10, backoff_cap=15)
    clock.now += 9.99
    assert process(q, handler, backoff_base=10, backoff_cap=15) == []
    clock.now += 0.01
    process(q, handler, backoff_base=10, backoff_cap=15)          # attempt 2: min(20, 15) = 15
    clock.now += 14.99
    assert q.receive() == []
    clock.now += 0.01
    assert q.receive()[0]["attempt"] == 3


def test_consume_once():
    done, calls = set(), []
    assert consume_once(done, "m1", lambda: calls.append("m1")) is True
    assert consume_once(done, "m1", lambda: calls.append("again")) is False
    assert calls == ["m1"] and done == {"m1"}

    def failing():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        consume_once(done, "m2", failing)
    assert "m2" not in done
    assert consume_once(done, "m2", lambda: calls.append("m2")) is True


def test_crash_after_side_effect_gives_a_duplicate_that_idempotency_absorbs(env):
    clock, q = env
    q.enqueue("charge $10")
    processed, charges = set(), []
    first = q.receive()[0]
    consume_once(processed, first["id"], lambda: charges.append(first["payload"]))
    # воркер впав до ack: підтвердження немає
    clock.now += 30
    second = q.receive()[0]
    assert second["id"] == first["id"], "at-least-once: повторна доставка"
    assert consume_once(processed, second["id"], lambda: charges.append(second["payload"])) is False
    assert q.ack(second["receipt"]) is True
    assert charges == ["charge $10"], "побічний ефект виконано один раз"
