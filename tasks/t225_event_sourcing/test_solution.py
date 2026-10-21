import copy

import pytest

from solution import (AccountRepository, BalanceProjection, ConcurrencyError, DomainError, EventStore, ReadModel,
                      StoredEvent, apply, decide)


def ev(t, **data):
    return {"type": t, "data": data}


def opened(owner="ann"):
    return ev("Opened", owner=owner)


class SpyStore(EventStore):
    def __init__(self):
        super().__init__()
        self.stream_reads = []

    def read_stream(self, stream_id, from_version=1):
        self.stream_reads.append((stream_id, from_version))
        return super().read_stream(stream_id, from_version)


def cmd(t, **kw):
    return {"type": t, **kw}


# --- EventStore --------------------------------------------------------------------------------

def test_append_assigns_versions_and_global_positions():
    s = EventStore()
    a = s.append("acc-1", [opened(), ev("Deposited", amount=5)], 0)
    b = s.append("acc-2", [opened("bob")], 0)
    c = s.append("acc-1", [ev("Deposited", amount=1)], 2)
    assert [(e.stream_id, e.version, e.position, e.type) for e in a] == [("acc-1", 1, 1, "Opened"), ("acc-1", 2, 2, "Deposited")]
    assert (b[0].version, b[0].position) == (1, 3)
    assert (c[0].version, c[0].position) == (3, 4)
    assert c[0].data == {"amount": 1}


def test_optimistic_concurrency_rejects_stale_writer_and_appends_nothing():
    s = EventStore()
    s.append("a", [opened()], 0)
    s.append("a", [ev("Deposited", amount=1)], 1)
    for stale in (0, 1, 3):
        with pytest.raises(ConcurrencyError):
            s.append("a", [ev("Deposited", amount=9)], stale)
    assert [e.version for e in s.read_stream("a")] == [1, 2]
    assert len(s.read_all()) == 2
    s.append("a", [ev("Deposited", amount=2)], 2)


def test_append_is_atomic_on_invalid_event():
    s = EventStore()
    for bad in ([opened(), {"type": "X"}], [opened(), {"type": "X", "data": "no"}], [opened(), "str"],
                [opened(), {"type": 5, "data": {}}]):
        with pytest.raises(ValueError):
            s.append("a", bad, 0)
    assert s.read_all() == []
    assert s.append("a", [opened()], 0)[0].version == 1


@pytest.mark.parametrize("bad", [-1, "0", None, 1.0, True])
def test_expected_version_must_be_non_negative_int(bad):
    with pytest.raises(ValueError):
        EventStore().append("a", [opened()], bad)


def test_empty_append_is_noop_but_checks_version():
    s = EventStore()
    assert s.append("a", [], 0) == []
    with pytest.raises(ConcurrencyError):
        s.append("a", [], 3)
    assert s.read_all() == []


def test_store_copies_data():
    s = EventStore()
    payload = {"type": "Opened", "data": {"owner": "ann", "tags": ["x"]}}
    s.append("a", [payload], 0)
    payload["data"]["owner"] = "evil"
    payload["data"]["tags"].append("y")
    stored = s.read_stream("a")[0]
    assert stored.data == {"owner": "ann", "tags": ["x"]}
    stored.data["owner"] = "evil2"
    assert s.read_stream("a")[0].data["owner"] == "ann"


def test_read_stream_and_read_all_ranges():
    s = EventStore()
    s.append("a", [opened(), ev("Deposited", amount=1), ev("Deposited", amount=2)], 0)
    s.append("b", [opened("b")], 0)
    s.append("a", [ev("Deposited", amount=3)], 3)
    assert [e.version for e in s.read_stream("a", from_version=3)] == [3, 4]
    assert s.read_stream("a", 5) == []
    assert s.read_stream("nope") == []
    assert [e.position for e in s.read_all(after_position=2)] == [3, 4, 5]
    assert [e.position for e in s.read_all(after_position=2, limit=2)] == [3, 4]
    assert s.read_all(after_position=5) == []
    assert [e.position for e in s.read_all(limit=0)] == []


# --- apply / decide ----------------------------------------------------------------------------

def test_apply_folds_events_and_is_pure():
    st = apply(None, opened("ann"))
    snapshot = copy.deepcopy(st)
    st2 = apply(st, ev("Deposited", amount=10))
    assert st == snapshot and st2 == {"owner": "ann", "balance": 10, "status": "open"}
    st3 = apply(st2, ev("Withdrawn", amount=4))
    st4 = apply(apply(st3, ev("Withdrawn", amount=6)), ev("Closed"))
    assert st3["balance"] == 6 and st4 == {"owner": "ann", "balance": 0, "status": "closed"}
    assert st2["balance"] == 10


def test_apply_accepts_stored_events_and_rejects_unknown():
    s = EventStore()
    stored = s.append("a", [opened("zed")], 0)[0]
    assert apply(None, stored)["owner"] == "zed"
    with pytest.raises(ValueError):
        apply(apply(None, opened()), ev("Teleported"))


def test_decide_rules():
    assert decide(None, cmd("open", owner="ann")) == [opened("ann")]
    st = {"owner": "ann", "balance": 10, "status": "open"}
    assert decide(st, cmd("deposit", amount=5)) == [ev("Deposited", amount=5)]
    assert decide(st, cmd("withdraw", amount=10)) == [ev("Withdrawn", amount=10)]
    assert decide({**st, "balance": 0}, cmd("close")) == [ev("Closed")]
    assert st == {"owner": "ann", "balance": 10, "status": "open"}


@pytest.mark.parametrize("state, command", [
    ({"owner": "a", "balance": 0, "status": "open"}, cmd("open", owner="x")),
    (None, cmd("deposit", amount=1)),
    (None, cmd("close")),
    ({"owner": "a", "balance": 5, "status": "closed"}, cmd("deposit", amount=1)),
    ({"owner": "a", "balance": 5, "status": "open"}, cmd("withdraw", amount=6)),
    ({"owner": "a", "balance": 5, "status": "open"}, cmd("close")),
    ({"owner": "a", "balance": 5, "status": "open"}, cmd("deposit", amount=0)),
    ({"owner": "a", "balance": 5, "status": "open"}, cmd("deposit", amount=-3)),
    ({"owner": "a", "balance": 5, "status": "open"}, cmd("deposit", amount=1.5)),
    ({"owner": "a", "balance": 5, "status": "open"}, cmd("deposit", amount=True)),
    ({"owner": "a", "balance": 5, "status": "open"}, cmd("withdraw", amount="1")),
])
def test_decide_domain_errors(state, command):
    with pytest.raises(DomainError):
        decide(state, command)


def test_decide_unknown_command():
    with pytest.raises(ValueError):
        decide(None, cmd("explode"))


# --- AccountRepository -------------------------------------------------------------------------

def test_repository_handle_and_load():
    s = EventStore()
    r = AccountRepository(s)
    assert r.load("a") == (None, 0)
    r.handle("a", cmd("open", owner="ann"))
    r.handle("a", cmd("deposit", amount=50))
    stored = r.handle("a", cmd("withdraw", amount=20))
    assert stored[0].version == 3
    assert r.load("a") == ({"owner": "ann", "balance": 30, "status": "open"}, 3)


def test_repository_domain_error_appends_nothing():
    s = EventStore()
    r = AccountRepository(s)
    r.handle("a", cmd("open", owner="ann"))
    with pytest.raises(DomainError):
        r.handle("a", cmd("withdraw", amount=1))
    assert len(s.read_all()) == 1


def test_concurrent_writers_second_gets_concurrency_error():
    s = EventStore()
    r1, r2 = AccountRepository(s), AccountRepository(s)
    r1.handle("a", cmd("open", owner="ann"))
    state, version = r1.load("a")
    s.append("a", decide(state, cmd("deposit", amount=5)), version)  # інший процес встиг
    with pytest.raises(ConcurrencyError):
        s.append("a", decide(state, cmd("deposit", amount=7)), version)
    r2.handle("a", cmd("deposit", amount=7))
    assert r2.load("a")[0]["balance"] == 12


def test_snapshots_are_taken_when_crossing_multiples():
    s = EventStore()
    r = AccountRepository(s, snapshot_every=3)
    r.handle("a", cmd("open", owner="ann"))
    r.handle("a", cmd("deposit", amount=1))
    assert "a" not in r.snapshots
    r.handle("a", cmd("deposit", amount=1))
    assert r.snapshots["a"]["version"] == 3 and r.snapshots["a"]["state"]["balance"] == 2
    r.handle("a", cmd("deposit", amount=1))
    r.handle("a", cmd("deposit", amount=1))
    assert r.snapshots["a"]["version"] == 3
    r.handle("a", cmd("deposit", amount=1))
    assert r.snapshots["a"]["version"] == 6 and r.snapshots["a"]["state"]["balance"] == 5


def test_snapshot_taken_at_new_version_when_batch_crosses_boundary():
    s = EventStore()
    r = AccountRepository(s, snapshot_every=3)
    s.append("a", [opened(), ev("Deposited", amount=1)], 0)
    r.handle("a", cmd("deposit", amount=1))  # 2 -> 3
    assert r.snapshots["a"]["version"] == 3
    s2 = EventStore()
    r2 = AccountRepository(s2, snapshot_every=2)
    s2.append("b", [opened()], 0)
    r2.handle("b", cmd("deposit", amount=1))
    assert r2.snapshots["b"]["version"] == 2


def test_load_with_snapshot_reads_only_the_tail_and_matches_full_replay():
    s = SpyStore()
    r = AccountRepository(s, snapshot_every=3)
    r.handle("a", cmd("open", owner="ann"))
    for _ in range(6):
        r.handle("a", cmd("deposit", amount=2))
    assert r.snapshots["a"]["version"] == 6
    s.stream_reads.clear()
    state, version = r.load("a")
    assert (state["balance"], version) == (12, 7)
    assert s.stream_reads == [("a", 7)]
    assert state == AccountRepository(s).load("a")[0]


def test_snapshot_is_a_copy_not_the_live_state():
    s = EventStore()
    r = AccountRepository(s, snapshot_every=2)
    r.handle("a", cmd("open", owner="ann"))
    r.handle("a", cmd("deposit", amount=5))
    loaded, _ = r.load("a")
    loaded["balance"] = 999
    assert r.snapshots["a"]["state"]["balance"] == 5
    assert r.load("a")[0]["balance"] == 5


def test_no_snapshots_when_disabled():
    s = EventStore()
    r = AccountRepository(s)
    r.handle("a", cmd("open", owner="ann"))
    for _ in range(10):
        r.handle("a", cmd("deposit", amount=1))
    assert r.snapshots == {}


# --- BalanceProjection -------------------------------------------------------------------------

def seed(store):
    r = AccountRepository(store)
    r.handle("a", cmd("open", owner="ann"))
    r.handle("b", cmd("open", owner="bob"))
    r.handle("a", cmd("deposit", amount=100))
    r.handle("b", cmd("deposit", amount=40))
    r.handle("a", cmd("withdraw", amount=30))
    return r


def test_projection_builds_read_model():
    s = EventStore()
    seed(s)
    p = BalanceProjection(s)
    assert p.catch_up() == 5
    assert p.checkpoint == 5
    assert p.get("a") == {"owner": "ann", "balance": 70, "status": "open"}
    assert p.get("b") == {"owner": "bob", "balance": 40, "status": "open"}
    assert p.get("zzz") is None
    assert p.total_open_balance() == 110


def test_projection_closed_accounts_leave_total():
    s = EventStore()
    r = seed(s)
    r.handle("b", cmd("withdraw", amount=40))
    r.handle("b", cmd("close"))
    p = BalanceProjection(s)
    p.catch_up()
    assert p.get("b")["status"] == "closed"
    assert p.total_open_balance() == 70


def test_projection_get_returns_copy():
    s = EventStore()
    seed(s)
    p = BalanceProjection(s)
    p.catch_up()
    p.get("a")["balance"] = 0
    assert p.get("a")["balance"] == 70


def test_catch_up_is_idempotent_and_incremental():
    s = EventStore()
    r = seed(s)
    p = BalanceProjection(s)
    assert p.catch_up(limit=2) == 2 and p.checkpoint == 2
    assert p.catch_up() == 3 and p.checkpoint == 5
    assert p.catch_up() == 0
    r.handle("a", cmd("deposit", amount=1))
    assert p.catch_up() == 1 and p.get("a")["balance"] == 71


def test_redelivery_of_old_events_is_ignored():
    s = EventStore()
    seed(s)
    p = BalanceProjection(s)
    p.catch_up()
    before = (p.get("a"), p.get("b"), p.checkpoint)
    for e in s.read_all():
        assert p.handle_event(e) is False
    assert (p.get("a"), p.get("b"), p.checkpoint) == before


def test_handle_event_returns_true_once_then_false():
    s = EventStore()
    stored = s.append("a", [opened()], 0)
    p = BalanceProjection(s)
    assert p.handle_event(stored[0]) is True
    assert p.handle_event(stored[0]) is False
    assert p.checkpoint == 1


def test_gap_in_positions_is_rejected_without_changes():
    s = EventStore()
    s.append("a", [opened()], 0)
    p = BalanceProjection(s)
    p.catch_up()
    ghost = StoredEvent("a", 3, 3, "Deposited", {"amount": 5})
    with pytest.raises(ValueError):
        p.handle_event(ghost)
    assert p.checkpoint == 1 and p.get("a")["balance"] == 0


def test_crash_in_the_middle_leaves_consistent_state_and_resumes():
    s = EventStore()
    seed(s)
    crashed = []

    def fault(event):
        if event.position == 3 and not crashed:
            crashed.append(event.position)
            raise RuntimeError("crash")

    p = BalanceProjection(s, fault=fault)
    with pytest.raises(RuntimeError):
        p.catch_up()
    assert p.checkpoint == 2
    assert p.get("a") == {"owner": "ann", "balance": 0, "status": "open"}
    assert p.get("b") == {"owner": "bob", "balance": 0, "status": "open"}
    assert p.catch_up() == 3
    reference = BalanceProjection(s)
    reference.catch_up()
    assert (p.get("a"), p.get("b"), p.checkpoint, p.total_open_balance()) == (
        reference.get("a"), reference.get("b"), reference.checkpoint, reference.total_open_balance())


def test_crash_on_first_event_changes_nothing():
    s = EventStore()
    s.append("a", [opened()], 0)

    def fault(event):
        raise RuntimeError("down")

    p = BalanceProjection(s, fault=fault)
    with pytest.raises(RuntimeError):
        p.catch_up()
    assert p.checkpoint == 0 and p.get("a") is None


def test_catch_up_dispatches_through_handle_event():
    seen = []

    class Spy(BalanceProjection):
        def handle_event(self, event):
            seen.append(event.position)
            return super().handle_event(event)

    s = EventStore()
    seed(s)
    p = Spy(s)
    assert p.catch_up() == 5
    assert seen == [1, 2, 3, 4, 5]


# --- ReadModel: перебудова без простою ----------------------------------------------------------

def test_read_model_delegates_to_current():
    s = EventStore()
    seed(s)
    m = ReadModel(s)
    assert m.get("a") is None
    assert m.catch_up() == 5
    assert m.get("a")["balance"] == 70
    assert m.current.checkpoint == 5


def test_rebuild_keeps_serving_old_projection_then_swaps():
    s = EventStore()
    r = seed(s)
    m = ReadModel(s)
    m.catch_up()
    old = m.current
    m.begin_rebuild()
    assert m.current is old
    assert m.rebuild_step(2) == 2
    assert m.current is old and m.get("a")["balance"] == 70
    r.handle("a", cmd("deposit", amount=5))  # трафік триває
    assert m.catch_up() == 1 and m.get("a")["balance"] == 75
    assert m.rebuild_step(1) == 1
    assert m.get("a")["balance"] == 75
    m.finish_rebuild()
    assert m.current is not old
    assert m.current.checkpoint == 6
    assert m.get("a") == {"owner": "ann", "balance": 75, "status": "open"}
    assert m.get("b")["balance"] == 40
    r.handle("b", cmd("deposit", amount=1))
    assert m.catch_up() == 1 and m.get("b")["balance"] == 41


def test_rebuild_with_new_projection_version_recomputes_history():
    class V2(BalanceProjection):
        def __init__(self, store, fault=None):
            super().__init__(store, fault)
            self.applied = 0

        def handle_event(self, event):
            ok = super().handle_event(event)
            self.applied += ok
            return ok

    s = EventStore()
    seed(s)
    m = ReadModel(s)
    m.catch_up()
    m.begin_rebuild(V2)
    m.finish_rebuild()
    assert isinstance(m.current, V2) and m.current.applied == 5
    m.begin_rebuild()
    m.finish_rebuild()
    assert isinstance(m.current, V2) and m.current.applied == 5


def test_rebuild_step_can_exhaust_and_is_chunked():
    s = EventStore()
    seed(s)
    m = ReadModel(s)
    m.begin_rebuild()
    assert [m.rebuild_step(2), m.rebuild_step(2), m.rebuild_step(2), m.rebuild_step(2)] == [2, 2, 1, 0]
    m.finish_rebuild()
    assert m.get("a")["balance"] == 70


def test_rebuild_state_errors_and_restart():
    s = EventStore()
    seed(s)
    m = ReadModel(s)
    with pytest.raises(RuntimeError):
        m.rebuild_step(1)
    with pytest.raises(RuntimeError):
        m.finish_rebuild()
    m.begin_rebuild()
    m.rebuild_step(3)
    m.begin_rebuild()
    assert m.rebuild_step(10) == 5
    m.finish_rebuild()
    with pytest.raises(RuntimeError):
        m.finish_rebuild()


def test_old_projection_unchanged_by_rebuild_progress():
    s = EventStore()
    seed(s)
    m = ReadModel(s)
    m.catch_up()
    old = m.current
    snapshot = (old.get("a"), old.get("b"), old.checkpoint)
    m.begin_rebuild()
    m.rebuild_step(3)
    assert (old.get("a"), old.get("b"), old.checkpoint) == snapshot
