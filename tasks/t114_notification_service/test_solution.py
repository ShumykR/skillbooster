import pytest

from solution import NotificationService

HOUR = 3600
DAY = 86400


class Clock:
    def __init__(self, hour=12):
        self.now = 100 * DAY + hour * HOUR

    def __call__(self):
        return self.now


class Sender:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    def __call__(self, user, kind, payload):
        self.calls.append((user, kind, payload))
        if self.fail:
            raise ConnectionError("provider down")


@pytest.fixture
def env():
    clock = Clock()
    push, email = Sender(), Sender()
    svc = NotificationService(clock, {"push": push, "email": email, "sms": Sender()})
    return clock, push, email, svc


def statuses(events):
    return [(e["id"], e["status"], e["channel"], e["attempt"]) for e in events]


# ---------- basics ---------------------------------------------------------------


def test_default_channel_is_push_and_sender_gets_the_payload(env):
    clock, push, email, svc = env
    assert svc.submit("ann", "order_shipped", {"order": 7}) == {"id": 1, "status": "queued"}
    assert svc.status(1) == "queued"
    assert statuses(svc.dispatch()) == [(1, "sent", "push", 1)]
    assert push.calls == [("ann", "order_shipped", {"order": 7})] and email.calls == []
    assert svc.sent == [(1, "push")] and svc.status(1) == "sent"
    assert svc.dispatch() == [], "відправлене вдруге не йде"


def test_unknown_id_and_invalid_priority(env):
    _, _, _, svc = env
    with pytest.raises(KeyError):
        svc.status(99)
    with pytest.raises(ValueError):
        svc.submit("ann", "k", {}, priority="urgent")


def test_ids_count_only_accepted_notifications(env):
    _, _, _, svc = env
    svc.set_preferences("ann", muted_kinds={"promo"})
    assert svc.submit("ann", "promo", {})["id"] is None
    assert svc.submit("ann", "news", {})["id"] == 1
    assert svc.submit("ann", "news", {}, dedupe_key="d")["id"] == 2
    assert svc.submit("ann", "news", {}, dedupe_key="d")["id"] is None
    assert svc.submit("ann", "news", {})["id"] == 3


# ---------- priorities -----------------------------------------------------------


def test_dispatch_order_is_priority_then_age(env):
    _, _, _, svc = env
    svc.submit("u", "a", 1, priority="low")
    svc.submit("u", "b", 2, priority="normal")
    svc.submit("u", "c", 3, priority="critical")
    svc.submit("u", "d", 4, priority="normal")
    svc.submit("u", "e", 5, priority="high")
    assert [e["id"] for e in svc.dispatch()] == [3, 5, 2, 4, 1]


# ---------- deduplication --------------------------------------------------------


def test_dedupe_window_boundary(env):
    clock, _, _, svc = env
    assert svc.submit("ann", "k", {}, dedupe_key="x")["status"] == "queued"
    clock.now += 299.99
    assert svc.submit("ann", "k", {}, dedupe_key="x")["status"] == "duplicate"
    clock.now += 0.01
    assert svc.submit("ann", "k", {}, dedupe_key="x")["status"] == "queued"
    clock.now += 100
    assert svc.submit("ann", "k", {}, dedupe_key="x")["status"] == "duplicate", "новий прийнятий запис відкрив нове вікно"


def test_duplicates_do_not_extend_the_window(env):
    clock, _, _, svc = env
    svc.submit("ann", "k", {}, dedupe_key="x")
    clock.now += 200
    assert svc.submit("ann", "k", {}, dedupe_key="x")["status"] == "duplicate"
    clock.now += 100
    assert svc.submit("ann", "k", {}, dedupe_key="x")["status"] == "queued"


def test_dedupe_is_per_user_and_per_key(env):
    _, _, _, svc = env
    assert svc.submit("ann", "k", {}, dedupe_key="x")["status"] == "queued"
    assert svc.submit("bob", "k", {}, dedupe_key="x")["status"] == "queued"
    assert svc.submit("ann", "k", {}, dedupe_key="y")["status"] == "queued"
    assert svc.submit("ann", "k", {})["status"] == "queued"
    assert svc.submit("ann", "k", {})["status"] == "queued", "без ключа дублікатів немає"


def test_muted_kinds_but_not_critical(env):
    clock, _, _, svc = env
    svc.set_preferences("ann", muted_kinds=["promo"])
    assert svc.submit("ann", "promo", {}) == {"id": None, "status": "muted"}
    assert svc.submit("ann", "promo", {}, priority="low")["status"] == "muted"
    assert svc.submit("ann", "promo", {}, priority="critical")["status"] == "queued"
    assert svc.submit("bob", "promo", {})["status"] == "queued"


def test_muted_message_does_not_open_a_dedupe_window(env):
    _, _, _, svc = env
    svc.set_preferences("ann", muted_kinds=["promo"])
    assert svc.submit("ann", "promo", {}, dedupe_key="p")["status"] == "muted"
    svc.set_preferences("ann", muted_kinds=[])
    assert svc.submit("ann", "promo", {}, dedupe_key="p")["status"] == "queued"


# ---------- retries and fallback ----------------------------------------------------


def test_retry_with_exponential_backoff_then_fallback_to_the_next_channel(env):
    clock, push, email, svc = env
    push.fail = True
    svc.submit("ann", "k", {})
    assert statuses(svc.dispatch()) == [(1, "retry", "push", 1)]
    assert svc.dispatch() == [], "backoff ще не минув"
    clock.now += 9.99
    assert svc.dispatch() == []
    clock.now += 0.01
    assert statuses(svc.dispatch()) == [(1, "retry", "push", 2)]
    clock.now += 19.99
    assert svc.dispatch() == []
    clock.now += 0.01
    assert statuses(svc.dispatch()) == [(1, "fallback", "push", 3)]
    assert statuses(svc.dispatch()) == [(1, "sent", "email", 1)], "fallback доступний одразу, спроби скинуті"
    assert svc.sent == [(1, "email")] and len(push.calls) == 3


def test_all_channels_failing_ends_in_failed(env):
    clock, push, email, svc = env
    push.fail = email.fail = True
    svc.set_preferences("ann", channels=["push", "email"])
    svc.submit("ann", "k", {})
    log = []
    for _ in range(20):
        log += statuses(svc.dispatch())
        clock.now += 20
    assert [s for _, s, _, _ in log] == ["retry", "retry", "fallback", "retry", "retry", "failed"]
    assert svc.status(1) == "failed" and svc.dispatch() == []


def test_custom_attempts_and_backoff():
    clock, push = Clock(), Sender(fail=True)
    svc = NotificationService(clock, {"push": push}, max_attempts=2, backoff_base=5)
    svc.set_preferences("u", channels=["push"])
    svc.submit("u", "k", {})
    assert statuses(svc.dispatch()) == [(1, "retry", "push", 1)]
    clock.now += 4.99
    assert svc.dispatch() == []
    clock.now += 0.01
    assert statuses(svc.dispatch()) == [(1, "failed", "push", 2)]


def test_a_failing_notification_does_not_block_others(env):
    clock, push, email, svc = env
    calls = []

    def flaky(user, kind, payload):
        calls.append(user)
        if user == "bad":
            raise ConnectionError

    svc.senders["push"] = flaky
    svc.submit("bad", "k", {}, priority="critical")
    svc.submit("good", "k", {})
    events = svc.dispatch()
    assert statuses(events) == [(1, "retry", "push", 1), (2, "sent", "push", 1)]


def test_user_channel_order(env):
    _, push, email, svc = env
    svc.set_preferences("ann", channels=["email"])
    svc.submit("ann", "k", {})
    assert statuses(svc.dispatch()) == [(1, "sent", "email", 1)] and push.calls == []


# ---------- quiet hours -------------------------------------------------------------


def test_quiet_hours_across_midnight(env):
    clock, push, _, svc = env
    svc.set_preferences("ann", quiet_hours=(22, 7))
    cases = {21: False, 22: True, 23: True, 0: True, 6: True, 7: False, 12: False}
    for hour, quiet in cases.items():
        clock.now = 100 * DAY + hour * HOUR + 59
        svc.submit("ann", "k", {"h": hour})
        events = svc.dispatch()
        assert (events == []) == quiet, hour
        if quiet:
            clock.now = 101 * DAY + 12 * HOUR
            svc.dispatch()
            clock.now = 100 * DAY


def test_quiet_hours_same_day_range(env):
    clock, _, _, svc = env
    svc.set_preferences("ann", quiet_hours=(13, 15))
    for hour, quiet in {12: False, 13: True, 14: True, 15: False}.items():
        clock.now = 100 * DAY + hour * HOUR
        svc.submit("ann", "k", {})
        assert (svc.dispatch() == []) == quiet, hour
        clock.now += 30 * DAY
        svc.dispatch()


def test_critical_ignores_quiet_hours_and_others_wait(env):
    clock, _, _, svc = env
    svc.set_preferences("ann", quiet_hours=(22, 7))
    clock.now = 100 * DAY + 23 * HOUR
    svc.submit("ann", "promo", {}, priority="high")
    svc.submit("ann", "alarm", {}, priority="critical")
    assert statuses(svc.dispatch()) == [(2, "sent", "push", 1)]
    assert svc.status(1) == "queued"
    clock.now = 101 * DAY + 7 * HOUR
    assert statuses(svc.dispatch()) == [(1, "sent", "push", 1)]


def test_quiet_hours_only_affect_their_user(env):
    clock, _, _, svc = env
    svc.set_preferences("ann", quiet_hours=(0, 23))
    svc.submit("ann", "k", {})
    svc.submit("bob", "k", {})
    assert [e["id"] for e in svc.dispatch()] == [2]


# ---------- preferences validation ---------------------------------------------------


@pytest.mark.parametrize("kwargs", [dict(channels=["fax"]), dict(channels=[]), dict(quiet_hours=(5, 5)), dict(quiet_hours=(24, 3)), dict(quiet_hours=(-1, 3))])
def test_invalid_preferences(env, kwargs):
    with pytest.raises(ValueError):
        env[3].set_preferences("ann", **kwargs)


def test_backoff_doubles_each_attempt():
    clock, push = Clock(), Sender(fail=True)
    svc = NotificationService(clock, {"push": push}, max_attempts=4, backoff_base=5)
    svc.set_preferences("u", channels=["push"])
    svc.submit("u", "k", {})
    start = clock.now
    for offset, attempt in ((0, 1), (5, 2), (15, 3)):       # паузи 5, 10, 20
        clock.now = start + offset
        assert statuses(svc.dispatch()) == [(1, "retry", "push", attempt)]
    clock.now = start + 34.99
    assert svc.dispatch() == []
    clock.now = start + 35
    assert statuses(svc.dispatch()) == [(1, "failed", "push", 4)]
