import itertools

import pytest

from solution import detect_deadlock, safe_lock_order


# --- detect_deadlock -------------------------------------------------------------------------

def test_classic_two_transaction_deadlock():
    holds = {"T1": {"A"}, "T2": {"B"}}
    waits = {"T1": "B", "T2": "A"}
    assert detect_deadlock(holds, waits) == ["T1", "T2"]


def test_no_waiters_no_deadlock():
    assert detect_deadlock({"T1": {"A"}, "T2": {"B"}}, {}) == []


def test_chain_without_cycle():
    holds = {"T1": {"A"}, "T2": {"B"}, "T3": {"C"}}
    waits = {"T1": "B", "T2": "C"}  # T1 -> T2 -> T3, T3 вільна
    assert detect_deadlock(holds, waits) == []


def test_waiting_for_a_free_resource_is_not_waiting_on_anyone():
    assert detect_deadlock({"T1": {"A"}}, {"T1": "Z"}) == []


def test_waiting_for_own_resource_is_not_a_cycle():
    assert detect_deadlock({"T1": {"A"}}, {"T1": "A"}) == []


def test_three_way_cycle():
    holds = {"T1": {"A"}, "T2": {"B"}, "T3": {"C"}}
    waits = {"T1": "B", "T2": "C", "T3": "A"}
    assert detect_deadlock(holds, waits) == ["T1", "T2", "T3"]


def test_innocent_bystander_waiting_on_a_cycle_is_not_reported():
    holds = {"T1": {"A"}, "T2": {"B"}, "T3": {"C"}}
    waits = {"T1": "B", "T2": "A", "T3": "A"}  # T3 чекає на T1, але в циклі T1<->T2 її немає
    assert detect_deadlock(holds, waits) == ["T1", "T2"]


def test_cycle_among_many_unrelated_transactions():
    holds = {"T1": {"A"}, "T2": {"B"}, "T3": {"C", "D"}, "T4": {"E"}, "T5": set()}
    waits = {"T1": "B", "T2": "A", "T4": "C", "T5": "E"}
    assert detect_deadlock(holds, waits) == ["T1", "T2"]


def test_two_independent_cycles_are_both_reported():
    holds = {"T1": {"A"}, "T2": {"B"}, "T3": {"C"}, "T4": {"D"}}
    waits = {"T1": "B", "T2": "A", "T3": "D", "T4": "C"}
    assert detect_deadlock(holds, waits) == ["T1", "T2", "T3", "T4"]


def test_transaction_holding_several_resources():
    holds = {"T1": {"A", "B"}, "T2": {"C"}}
    waits = {"T1": "C", "T2": "B"}
    assert detect_deadlock(holds, waits) == ["T1", "T2"]


def test_inputs_are_not_mutated():
    holds = {"T1": {"A"}, "T2": {"B"}}
    waits = {"T1": "B", "T2": "A"}
    detect_deadlock(holds, waits)
    assert holds == {"T1": {"A"}, "T2": {"B"}} and waits == {"T1": "B", "T2": "A"}


# --- safe_lock_order -------------------------------------------------------------------------

def test_safe_order_sorts_each_plan():
    plans = {"T1": ["B", "A"], "T2": ["C", "A", "B"]}
    assert safe_lock_order(plans) == {"T1": ["A", "B"], "T2": ["A", "B", "C"]}


def test_safe_order_removes_duplicates_and_keeps_input():
    plans = {"T1": ["B", "A", "B"]}
    assert safe_lock_order(plans) == {"T1": ["A", "B"]}
    assert plans == {"T1": ["B", "A", "B"]}


def test_safe_order_empty():
    assert safe_lock_order({}) == {}
    assert safe_lock_order({"T1": []}) == {"T1": []}


# --- модель: перебір усіх чергувань ----------------------------------------------------------

def explore(plans):
    """Перебирає всі досяжні стани. Повертає множину результатів detect_deadlock у стані
    «ніхто не може рухатись, але не всі завершили»."""
    names = sorted(plans)
    deadlocks = set()
    seen = set()

    def step(pos):
        if pos in seen:
            return
        seen.add(pos)
        active = {n: i for n, i in zip(names, pos) if i < len(plans[n])}
        if not active:
            return
        holds = {n: set(plans[n][:i]) for n, i in active.items()}
        held = {r: n for n, rs in holds.items() for r in rs}
        runnable, waits = [], {}
        for idx, n in enumerate(names):
            if n not in active:
                continue
            want = plans[n][active[n]]
            if want in held and held[want] != n:
                waits[n] = want
            else:
                runnable.append(idx)
        if not runnable:
            deadlocks.add(tuple(detect_deadlock(holds, waits)))
            return
        for idx in runnable:
            nxt = list(pos)
            nxt[idx] += 1  # взяв блокування; завершивши всі, транзакція вважається закомічена
            step(tuple(nxt))

    step(tuple(0 for _ in names))
    return deadlocks


def test_model_finds_the_classic_deadlock():
    plans = {"T1": ["A", "B"], "T2": ["B", "A"]}
    assert explore(plans) == {("T1", "T2")}


def test_model_no_deadlock_when_orders_agree():
    assert explore({"T1": ["A", "B"], "T2": ["A", "B"]}) == set()


def test_safe_order_removes_the_classic_deadlock():
    plans = {"T1": ["A", "B"], "T2": ["B", "A"]}
    assert explore(safe_lock_order(plans)) == set()


def test_safe_order_removes_three_way_deadlock():
    plans = {"T1": ["A", "B"], "T2": ["B", "C"], "T3": ["C", "A"]}
    assert explore(plans) == {("T1", "T2", "T3")}
    assert explore(safe_lock_order(plans)) == set()


@pytest.mark.parametrize("resources", [("A", "B"), ("A", "B", "C")])
def test_safe_order_is_deadlock_free_for_every_permutation_pair(resources):
    perms = list(itertools.permutations(resources))
    for p1, p2 in itertools.product(perms, repeat=2):
        plans = {"T1": list(p1), "T2": list(p2)}
        assert explore(safe_lock_order(plans)) == set(), (p1, p2)


def test_unsafe_plans_do_deadlock_for_opposite_orders():
    for resources in (("A", "B"), ("A", "B", "C")):
        plans = {"T1": list(resources), "T2": list(reversed(resources))}
        assert explore(plans), resources
