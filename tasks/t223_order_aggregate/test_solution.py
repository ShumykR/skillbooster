import dataclasses

import pytest

from solution import (ConcurrencyError, DomainError, Order, OrderCancelled, OrderLine, OrderPaid, OrderPlaced,
                      OrderRepository, OrderShipped)


def draft(max_total=100_000):
    o = Order("o-1", "c-1", max_total)
    return o


def with_lines():
    o = draft()
    o.add_line("A", 2, 1000)
    o.add_line("B", 1, 500)
    return o


# --- створення й читання -----------------------------------------------------------------------

def test_new_order_defaults():
    o = Order("o-1", "c-1")
    assert (o.id, o.customer_id, o.status, o.version, o.max_total_cents) == ("o-1", "c-1", "draft", 0, 100_000)
    assert o.lines == () and o.total_cents == 0
    assert o.pull_events() == []


@pytest.mark.parametrize("args", [("", "c"), ("o", ""), (None, "c"), ("o", 5), ("o", "c", 0), ("o", "c", -1),
                                  ("o", "c", True), ("o", "c", 1.5), ("o", "c", "100")])
def test_constructor_validation(args):
    with pytest.raises(ValueError):
        Order(*args)


def test_lines_and_total():
    o = with_lines()
    assert o.lines == (OrderLine("A", 2, 1000), OrderLine("B", 1, 500))
    assert o.total_cents == 2500


# --- інваріанти не обійти ззовні ---------------------------------------------------------------

@pytest.mark.parametrize("attr", ["id", "customer_id", "status", "version", "max_total_cents", "lines", "total_cents"])
def test_attributes_are_read_only(attr):
    o = with_lines()
    with pytest.raises(AttributeError):
        setattr(o, attr, "hacked" if attr != "lines" else [])


def test_lines_cannot_be_mutated_through_the_returned_collection():
    o = with_lines()
    lines = o.lines
    assert isinstance(lines, tuple)
    assert not hasattr(lines, "append")
    with pytest.raises(TypeError):
        lines[0] = OrderLine("X", 1, 1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        lines[0].qty = 999
    with pytest.raises(dataclasses.FrozenInstanceError):
        lines[0].unit_price_cents = 1
    assert o.total_cents == 2500


def test_snapshot_taken_earlier_does_not_change():
    o = draft()
    o.add_line("A", 1, 100)
    snap = o.lines
    o.add_line("A", 4, 100)
    assert snap == (OrderLine("A", 1, 100),)
    assert o.lines == (OrderLine("A", 5, 100),)


def test_events_are_immutable():
    o = with_lines()
    o.place()
    ev = o.pull_events()[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        ev.total_cents = 1


# --- add_line / remove_line --------------------------------------------------------------------

def test_same_sku_same_price_merges_keeping_position():
    o = with_lines()
    o.add_line("A", 3, 1000)
    assert o.lines == (OrderLine("A", 5, 1000), OrderLine("B", 1, 500))
    assert o.total_cents == 5500


def test_same_sku_different_price_is_domain_error_and_changes_nothing():
    o = with_lines()
    with pytest.raises(DomainError):
        o.add_line("A", 1, 999)
    assert o.lines == (OrderLine("A", 2, 1000), OrderLine("B", 1, 500))


@pytest.mark.parametrize("args", [("", 1, 1), (None, 1, 1), ("A", 0, 1), ("A", -1, 1), ("A", 1.0, 1), ("A", True, 1),
                                  ("A", 1, 0), ("A", 1, -5), ("A", 1, 2.5), ("A", 1, True), ("A", "1", 1)])
def test_add_line_validation(args):
    o = draft()
    with pytest.raises(ValueError):
        o.add_line(*args)
    assert o.lines == ()


def test_total_limit_is_enforced_including_merges_and_boundary():
    o = draft(max_total=1000)
    o.add_line("A", 1, 1000)  # рівно ліміт: можна
    assert o.total_cents == 1000
    with pytest.raises(DomainError):
        o.add_line("A", 1, 1000)  # злиття перевищило б
    with pytest.raises(DomainError):
        o.add_line("B", 1, 1)
    assert o.lines == (OrderLine("A", 1, 1000),)
    assert o.total_cents == 1000


def test_failed_limit_check_does_not_leave_a_partial_line():
    o = draft(max_total=500)
    with pytest.raises(DomainError):
        o.add_line("A", 1, 501)
    assert o.lines == ()
    o.add_line("A", 5, 100)
    assert o.total_cents == 500


def test_remove_line():
    o = with_lines()
    o.remove_line("A")
    assert o.lines == (OrderLine("B", 1, 500),)
    assert o.total_cents == 500
    with pytest.raises(DomainError):
        o.remove_line("A")


def test_lines_are_frozen_after_place():
    o = with_lines()
    o.place()
    with pytest.raises(DomainError):
        o.add_line("C", 1, 1)
    with pytest.raises(DomainError):
        o.remove_line("A")
    assert o.total_cents == 2500


# --- переходи статусу й події ------------------------------------------------------------------

def test_happy_path_events_in_order():
    o = with_lines()
    o.place()
    o.pay()
    o.ship()
    assert o.status == "shipped"
    assert o.pull_events() == [OrderPlaced("o-1", "c-1", 2500), OrderPaid("o-1", 2500), OrderShipped("o-1")]
    assert o.pull_events() == []


def test_place_requires_a_line_and_changes_nothing_on_failure():
    o = draft()
    with pytest.raises(DomainError):
        o.place()
    assert o.status == "draft" and o.pull_events() == []


@pytest.mark.parametrize("path, forbidden", [
    ([], "pay"), ([], "ship"), (["place"], "place"), (["place"], "ship"),
    (["place", "pay"], "place"), (["place", "pay"], "pay"), (["place", "pay", "ship"], "ship"),
    (["place", "pay", "ship"], "cancel"), (["cancel"], "place"), (["cancel"], "pay"), (["cancel"], "cancel"),
])
def test_forbidden_transitions(path, forbidden):
    o = with_lines()
    for step in path:
        getattr(o, step)("because") if step == "cancel" else getattr(o, step)()
    before_status, before_events = o.status, o.pull_events()
    with pytest.raises(DomainError):
        getattr(o, forbidden)("again") if forbidden == "cancel" else getattr(o, forbidden)()
    assert o.status == before_status
    assert o.pull_events() == []
    assert isinstance(before_events, list)


@pytest.mark.parametrize("path, previous", [([], "draft"), (["place"], "placed"), (["place", "pay"], "paid")])
def test_cancel_from_allowed_states(path, previous):
    o = with_lines()
    for step in path:
        getattr(o, step)()
    o.pull_events()
    o.cancel("customer changed mind")
    assert o.status == "cancelled"
    assert o.pull_events() == [OrderCancelled("o-1", "customer changed mind", previous)]


@pytest.mark.parametrize("reason", ["", None, 5])
def test_cancel_reason_validation(reason):
    o = with_lines()
    with pytest.raises(ValueError):
        o.cancel(reason)
    assert o.status == "draft"


def test_place_event_carries_total_at_that_moment():
    o = with_lines()
    o.place()
    o.pay()
    events = o.pull_events()
    assert events[0].total_cents == events[1].total_cents == 2500


# --- репозиторій і оптимістичне блокування -----------------------------------------------------

def test_save_new_and_get_roundtrip():
    repo = OrderRepository()
    o = with_lines()
    repo.save(o)
    assert o.version == 1
    got = repo.get("o-1")
    assert got is not o
    assert (got.id, got.customer_id, got.status, got.version, got.max_total_cents) == ("o-1", "c-1", "draft", 1, 100_000)
    assert got.lines == o.lines and got.total_cents == 2500
    assert got.pull_events() == []


def test_get_unknown_is_key_error():
    with pytest.raises(KeyError):
        OrderRepository().get("nope")


def test_whole_aggregate_is_persisted_including_status_and_limit():
    repo = OrderRepository()
    o = Order("o-9", "c-9", 777)
    o.add_line("A", 1, 700)
    o.place()
    repo.save(o)
    got = repo.get("o-9")
    assert got.status == "placed" and got.max_total_cents == 777 and got.customer_id == "c-9"
    with pytest.raises(DomainError):
        got.add_line("B", 1, 1)  # статус зберігся: чернетка вже закрита
    got.pay()
    assert got.status == "paid"


def test_version_increments_on_each_save():
    repo = OrderRepository()
    o = with_lines()
    repo.save(o)
    o.place()
    repo.save(o)
    o.pay()
    repo.save(o)
    assert o.version == 3
    assert repo.get("o-1").version == 3


def test_concurrent_modification_is_rejected_and_store_unchanged():
    repo = OrderRepository()
    first = with_lines()
    repo.save(first)
    a, b = repo.get("o-1"), repo.get("o-1")
    a.add_line("C", 1, 100)
    b.place()
    repo.save(a)
    with pytest.raises(ConcurrencyError):
        repo.save(b)
    stored = repo.get("o-1")
    assert stored.status == "draft" and stored.version == 2
    assert stored.lines[-1] == OrderLine("C", 1, 100)
    assert b.version == 1  # невдале збереження не рухає версію обʼєкта


def test_stale_object_can_retry_after_reload():
    repo = OrderRepository()
    repo.save(with_lines())
    a, b = repo.get("o-1"), repo.get("o-1")
    a.add_line("C", 1, 100)
    repo.save(a)
    b = repo.get("o-1")
    b.place()
    repo.save(b)
    assert repo.get("o-1").status == "placed" and repo.get("o-1").version == 3


def test_saving_a_second_new_order_with_same_id_conflicts():
    repo = OrderRepository()
    repo.save(with_lines())
    dup = Order("o-1", "c-2")
    dup.add_line("Z", 1, 1)
    with pytest.raises(ConcurrencyError):
        repo.save(dup)
    got = repo.get("o-1")
    assert got.customer_id == "c-1" and got.version == 1


def test_object_mutated_after_save_does_not_leak_into_the_store():
    repo = OrderRepository()
    o = with_lines()
    repo.save(o)
    o.add_line("LEAK", 1, 1)
    o.place()
    got = repo.get("o-1")
    assert got.status == "draft"
    assert [l.sku for l in got.lines] == ["A", "B"]


def test_loaded_copies_are_independent_of_each_other():
    repo = OrderRepository()
    repo.save(with_lines())
    a, b = repo.get("o-1"), repo.get("o-1")
    a.add_line("A", 10, 1000)
    assert b.lines[0].qty == 2
    assert repo.get("o-1").lines[0].qty == 2


def test_events_do_not_travel_through_the_repository():
    repo = OrderRepository()
    o = with_lines()
    o.place()
    repo.save(o)
    assert len(o.pull_events()) == 1  # save не забирає події
    assert repo.get("o-1").pull_events() == []


def test_repositories_are_independent():
    r1, r2 = OrderRepository(), OrderRepository()
    r1.save(with_lines())
    with pytest.raises(KeyError):
        r2.get("o-1")
