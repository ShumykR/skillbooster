import json

from solution import IdempotencyStore, process_batch

NOW = 1_000.0


def rec(message_id, payload, raw=None):
    return {"messageId": message_id, "body": raw if raw is not None else json.dumps(payload)}


class Handler:
    def __init__(self, fail_on=()):
        self.fail_on, self.calls = set(fail_on), []

    def __call__(self, payload):
        self.calls.append(payload)
        if payload.get("n") in self.fail_on or payload.get("boom"):
            raise RuntimeError("cannot process")


def run(records, handler, store=None, now=NOW, **kw):
    store = store or IdempotencyStore()
    return process_batch({"Records": records}, handler, store, now=now, **kw), store


def failed_ids(result):
    return [f["itemIdentifier"] for f in result["batchItemFailures"]]


def test_all_succeed():
    h = Handler()
    result, _ = run([rec("m1", {"n": 1}), rec("m2", {"n": 2})], h)
    assert result == {"batchItemFailures": []}
    assert h.calls == [{"n": 1}, {"n": 2}]


def test_partial_batch_response_only_returns_failed_records():
    h = Handler(fail_on={2, 4})
    records = [rec(f"m{i}", {"n": i}) for i in range(1, 6)]
    result, _ = run(records, h)
    assert failed_ids(result) == ["m2", "m4"]
    assert [c["n"] for c in h.calls] == [1, 2, 3, 4, 5], "помилка одного не зупиняє пачку"


def test_redelivered_message_is_not_processed_twice():
    h, store = Handler(), IdempotencyStore()
    run([rec("m1", {"n": 1})], h, store)
    result, _ = run([rec("m1", {"n": 1})], h, store, now=NOW + 5)
    assert result == {"batchItemFailures": []}
    assert len(h.calls) == 1


def test_duplicate_business_event_with_different_message_ids():
    h = Handler()
    result, _ = run([rec("m1", {"event_id": "evt-9", "n": 1}), rec("m2", {"event_id": "evt-9", "n": 1})], h)
    assert result == {"batchItemFailures": []}
    assert len(h.calls) == 1


def test_event_id_is_preferred_over_message_id_and_numbers_are_stringified():
    h, store = Handler(), IdempotencyStore()
    run([rec("m1", {"event_id": 42})], h, store)
    assert store.begin("42", NOW) == "done"
    run([rec("m1", {"n": 7, "event_id": ""}), rec("m1", {"n": 7})], h, store)
    assert store.begin("m1", NOW) == "done"
    assert len([c for c in h.calls if c.get("n") == 7]) == 1


def test_failed_message_is_retried_on_next_delivery():
    h, store = Handler(fail_on={1}), IdempotencyStore()
    first, _ = run([rec("m1", {"n": 1})], h, store)
    assert failed_ids(first) == ["m1"]
    h.fail_on = set()
    second, _ = run([rec("m1", {"n": 1})], h, store, now=NOW + 30)
    assert second == {"batchItemFailures": []}
    assert len(h.calls) == 2


def test_message_being_processed_elsewhere_is_reported_as_failed_without_calling_handler():
    h, store = Handler(), IdempotencyStore(lock_ttl=300)
    assert store.begin("m1", NOW) == "acquired"
    result, _ = run([rec("m1", {"n": 1})], h, store, now=NOW + 10)
    assert failed_ids(result) == ["m1"] and h.calls == []


def test_stale_lock_is_taken_over():
    h, store = Handler(), IdempotencyStore(lock_ttl=300)
    store.begin("m1", NOW)
    result, _ = run([rec("m1", {"n": 1})], h, store, now=NOW + 301)
    assert result == {"batchItemFailures": []} and len(h.calls) == 1


def test_malformed_bodies_fail_without_touching_handler_or_store():
    h, store = Handler(), IdempotencyStore()
    records = [rec("m1", None, raw="{not json"), rec("m2", None, raw="[1, 2]"), rec("m3", None, raw='"text"'), rec("m4", {"n": 4})]
    result, _ = run(records, h, store)
    assert failed_ids(result) == ["m1", "m2", "m3"]
    assert h.calls == [{"n": 4}]
    assert store.begin("m1", NOW) == "acquired", "для зіпсованого запису ключ не створювався"


def test_fifo_stops_after_first_failure_and_fails_the_rest_untouched():
    h, store = Handler(fail_on={2}), IdempotencyStore()
    records = [rec(f"m{i}", {"n": i}) for i in range(1, 5)]
    result, _ = run(records, h, store, fifo=True)
    assert failed_ids(result) == ["m2", "m3", "m4"]
    assert [c["n"] for c in h.calls] == [1, 2]
    assert store.begin("m3", NOW) == "acquired", "наступні записи не чіпали store"


def test_fifo_without_failures_processes_everything():
    h = Handler()
    result, _ = run([rec(f"m{i}", {"n": i}) for i in range(3)], h, fifo=True)
    assert result == {"batchItemFailures": []} and len(h.calls) == 3


def test_fifo_duplicates_are_not_failures():
    h, store = Handler(), IdempotencyStore()
    run([rec("m1", {"n": 1})], h, store)
    result, _ = run([rec("m1", {"n": 1}), rec("m2", {"n": 2})], h, store, fifo=True)
    assert result == {"batchItemFailures": []} and len(h.calls) == 2


def test_empty_event():
    assert run([], Handler())[0] == {"batchItemFailures": []}
    assert process_batch({}, Handler(), IdempotencyStore(), now=NOW) == {"batchItemFailures": []}


def test_order_of_failures_follows_record_order():
    h = Handler(fail_on={3, 1})
    records = [rec("m3", {"n": 3}), rec("m1", {"n": 1}), rec("m2", {"n": 2})]
    assert failed_ids(run(records, h)[0]) == ["m3", "m1"]


# ---------- наскрізно: SQS з redrive у DLQ ------------------------------------


class MiniSqs:
    """Дуже спрощена SQS: повторна доставка невдалих, лічильник отримань, переміщення в DLQ після maxReceiveCount."""

    def __init__(self, bodies, max_receive_count=3, duplicate_every=None):
        self.queue = [{"messageId": f"m{i}", "body": json.dumps(b), "receives": 0} for i, b in enumerate(bodies)]
        if duplicate_every:
            self.queue.insert(2, dict(self.queue[0]))  # продюсер надіслав те саме двічі
        self.max_receive_count, self.dlq = max_receive_count, []

    def run(self, handler, store, batch_size=10, fifo=False):
        clock = NOW
        while self.queue:
            batch, self.queue = self.queue[:batch_size], self.queue[batch_size:]
            for m in batch:
                m["receives"] += 1
            result = process_batch({"Records": [{"messageId": m["messageId"], "body": m["body"]} for m in batch]}, handler, store, now=clock, fifo=fifo)
            failed = set(failed_ids(result))
            for m in batch:
                if m["messageId"] in failed:
                    if m["receives"] >= self.max_receive_count:
                        self.dlq.append(m)
                    else:
                        self.queue.append(m)
            clock += 60


def test_end_to_end_poison_goes_to_dlq_good_messages_run_exactly_once():
    h, store = Handler(), IdempotencyStore()
    sqs = MiniSqs([{"event_id": "a", "n": 1}, {"event_id": "b", "boom": True}, {"event_id": "c", "n": 3}], duplicate_every=True)
    sqs.run(h, store)
    assert [m["messageId"] for m in sqs.dlq] == ["m1"] and sqs.dlq[0]["receives"] == 3
    ok_calls = [c["n"] for c in h.calls if c.get("n")]
    assert sorted(ok_calls) == [1, 3], "n=1 прийшло двічі, але виконано один раз"
    assert len([c for c in h.calls if c.get("boom")]) == 3, "отруйне пробувалось рівно maxReceiveCount разів"


def test_end_to_end_transient_failure_recovers_without_duplicates():
    class Flaky:
        def __init__(self):
            self.calls, self.done = 0, []

        def __call__(self, payload):
            self.calls += 1
            if payload["n"] == 2 and self.calls < 4:
                raise TimeoutError("db timeout")
            self.done.append(payload["n"])

    h, store = Flaky(), IdempotencyStore()
    sqs = MiniSqs([{"n": 1}, {"n": 2}, {"n": 3}])
    sqs.run(h, store)
    assert sqs.dlq == []
    assert sorted(h.done) == [1, 2, 3] and len(h.done) == 3
