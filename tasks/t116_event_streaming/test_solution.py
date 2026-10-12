import zlib

import pytest

from solution import ConsumerGroup, Topic


def part_of(key, n):
    return zlib.crc32(key.encode()) % n


def filled(n=3, count=9):
    """count повідомлень без ключа: round-robin, партиція p отримує v{p}, v{p+n}, ..."""
    t = Topic(n)
    for i in range(count):
        t.produce(None, f"v{i}")
    return t


def values(records):
    return [r["value"] for r in records]


# ---------- Topic ----------------------------------------------------------------


def test_keyed_messages_go_to_a_stable_partition_with_growing_offsets():
    t = Topic(4)
    first = t.produce("user-1", "a")
    second = t.produce("user-1", "b")
    assert first == (part_of("user-1", 4), 0) and second == (part_of("user-1", 4), 1)
    other = "user-2" if part_of("user-2", 4) != first[0] else "user-3"
    assert t.produce(other, "c")[1] == 0, "offset рахується окремо в кожній партиції"


def test_messages_without_key_are_spread_round_robin():
    t = Topic(3)
    assert [t.produce(None, i) for i in range(5)] == [(0, 0), (1, 0), (2, 0), (0, 1), (1, 1)]
    t.produce("k", "x")
    assert t.produce(None, "next")[0] == 2, "лічильник round-robin не зачіпається ключовими повідомленнями"


def test_read_ranges():
    t = filled()
    assert [r["value"] for r in t.read(0, 0, 10)] == ["v0", "v3", "v6"]
    assert [(r["offset"], r["value"]) for r in t.read(0, 1, 1)] == [(1, "v3")]
    assert t.read(0, 3, 5) == [] and t.read(1, 10, 5) == []
    assert t.read(2, 0, 1)[0] == {"partition": 2, "offset": 0, "key": None, "value": "v2"}
    assert t.end_offsets() == [3, 3, 3]
    with pytest.raises(ValueError):
        t.read(3, 0, 1)
    with pytest.raises(ValueError):
        Topic(0)


def test_order_is_preserved_per_key():
    t = Topic(3)
    for i in range(6):
        t.produce("order-7", f"event{i}")
        t.produce(f"noise-{i}", "x")
    g = ConsumerGroup(t, "g")
    g.join("a")
    mine = [r for r in g.poll("a", 100) if r["key"] == "order-7"]
    assert values(mine) == [f"event{i}" for i in range(6)]
    assert len({r["partition"] for r in mine}) == 1


# ---------- assignment and rebalance ---------------------------------------------------


def test_assignment_round_robin_over_sorted_members():
    g = ConsumerGroup(filled(), "g")
    assert g.assignment() == {}
    g.join("b")
    assert g.assignment() == {"b": [0, 1, 2]}
    g.join("a")
    assert g.assignment() == {"a": [0, 2], "b": [1]}
    g.join("c")
    assert g.assignment() == {"a": [0], "b": [1], "c": [2]}
    g.join("d")
    assert g.assignment() == {"a": [0], "b": [1], "c": [2], "d": []}, "учасників більше, ніж партицій"


def test_generation_changes_only_on_real_membership_changes():
    g = ConsumerGroup(filled(), "g")
    assert g.generation == 0
    g.join("a")
    g.join("a")
    assert g.generation == 1
    g.leave("zzz")
    assert g.generation == 1
    g.join("b")
    g.leave("a")
    assert g.generation == 3


# ---------- polling and committing -------------------------------------------------------


def test_poll_reads_partitions_in_order_and_advances():
    g = ConsumerGroup(filled(), "g")
    g.join("a")
    assert values(g.poll("a", 100)) == ["v0", "v3", "v6", "v1", "v4", "v7", "v2", "v5", "v8"]
    assert g.poll("a", 100) == []


def test_max_records_is_a_total_limit_and_polling_resumes():
    g = ConsumerGroup(filled(), "g")
    g.join("a")
    assert values(g.poll("a", 4)) == ["v0", "v3", "v6", "v1"]
    assert values(g.poll("a", 4)) == ["v4", "v7", "v2", "v5"]
    assert values(g.poll("a", 4)) == ["v8"]


def test_members_read_disjoint_partitions_and_together_everything():
    g = ConsumerGroup(filled(), "g")
    g.join("a")
    g.join("b")
    a, b = values(g.poll("a", 100)), values(g.poll("b", 100))
    assert a == ["v0", "v3", "v6", "v2", "v5", "v8"] and b == ["v1", "v4", "v7"]


def test_uncommitted_records_are_redelivered_after_rebalance():
    g = ConsumerGroup(filled(), "g")
    g.join("a")
    assert len(g.poll("a", 100)) == 9
    g.join("b")  # rebalance без commit: усе читається знову
    assert values(g.poll("a", 100)) == ["v0", "v3", "v6", "v2", "v5", "v8"]
    assert values(g.poll("b", 100)) == ["v1", "v4", "v7"]


def test_committed_records_are_not_redelivered():
    g = ConsumerGroup(filled(), "g")
    g.join("a")
    g.poll("a", 4)
    g.commit("a")
    assert g.committed() == {0: 3, 1: 1, 2: 0}
    g.join("b")
    assert values(g.poll("a", 100)) == ["v2", "v5", "v8"], "a тепер має партиції 0 і 2: партиція 0 дочитана, партиція 2 з нуля"
    assert values(g.poll("b", 100)) == ["v4", "v7"], "партиція 1 продовжується з committed offset 1"


def test_commit_only_covers_the_members_partitions():
    g = ConsumerGroup(filled(), "g")
    g.join("a")
    g.join("b")
    g.poll("a", 100)
    g.poll("b", 100)
    g.commit("a")
    assert g.committed() == {0: 3, 1: 0, 2: 3}
    g.commit("b")
    assert g.committed() == {0: 3, 1: 3, 2: 3}


def test_commit_after_rebalance_without_poll_keeps_committed():
    g = ConsumerGroup(filled(), "g")
    g.join("a")
    g.poll("a", 4)
    g.commit("a")
    g.join("b")
    g.commit("a")
    assert g.committed() == {0: 3, 1: 1, 2: 0}


def test_a_crashed_member_does_not_lose_messages():
    g = ConsumerGroup(filled(), "g")
    g.join("a")
    g.poll("a", 100)
    g.leave("a")  # впав, не закомітивши
    g.join("b")
    assert len(g.poll("b", 100)) == 9


def test_new_messages_are_picked_up():
    t = filled()
    g = ConsumerGroup(t, "g")
    g.join("a")
    g.poll("a", 100)
    t.produce(None, "late")  # round-robin: 9-й -> партиція 0
    assert values(g.poll("a", 100)) == ["late"]


# ---------- lag, seek, replay ---------------------------------------------------------------


def test_lag():
    g = ConsumerGroup(filled(), "g")
    assert g.lag() == {"partitions": {0: 3, 1: 3, 2: 3}, "total": 9}
    g.join("a")
    g.poll("a", 4)
    assert g.lag()["total"] == 9, "прочитане, але не закомічене все ще в лазі"
    g.commit("a")
    assert g.lag() == {"partitions": {0: 0, 1: 2, 2: 3}, "total": 5}


def test_seek_replays_from_an_offset():
    g = ConsumerGroup(filled(), "g")
    g.join("a")
    g.poll("a", 100)
    g.commit("a")
    g.seek("a", 0, 1)
    assert values(g.poll("a", 100)) == ["v3", "v6"]
    g.seek("a", 1, 0)
    assert values(g.poll("a", 100)) == ["v1", "v4", "v7"]


def test_seek_validation():
    g = ConsumerGroup(filled(), "g")
    g.join("a")
    g.join("b")
    with pytest.raises(ValueError):
        g.seek("a", 1, 0)  # партиція 1 належить b
    with pytest.raises(ValueError):
        g.seek("a", 0, -1)
    with pytest.raises(ValueError):
        g.seek("ghost", 0, 0)


def test_only_members_can_poll_or_commit():
    g = ConsumerGroup(filled(), "g")
    for call in (lambda: g.poll("x"), lambda: g.commit("x")):
        with pytest.raises(ValueError):
            call()


def test_initial_committed_offsets_cover_all_partitions():
    assert ConsumerGroup(Topic(4), "g").committed() == {0: 0, 1: 0, 2: 0, 3: 0}
