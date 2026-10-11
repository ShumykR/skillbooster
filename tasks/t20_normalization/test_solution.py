from itertools import combinations

import pytest

from solution import candidate_keys, closure, is_3nf, minimal_cover, synthesize_3nf


def fd(lhs, rhs):
    return (set(lhs), set(rhs))


def fs(*groups):
    return {frozenset(g) for g in groups}


# --- closure ---------------------------------------------------------------------------------

def test_closure_is_transitive():
    fds = [fd("A", "B"), fd("B", "C"), fd("C", "D")]
    assert closure({"A"}, fds) == frozenset("ABCD")
    assert closure({"B"}, fds) == frozenset("BCD")
    assert closure({"D"}, fds) == frozenset("D")


def test_closure_needs_whole_lhs():
    fds = [fd("AB", "C"), fd("C", "D")]
    assert closure({"A"}, fds) == frozenset("A")
    assert closure({"A", "B"}, fds) == frozenset("ABCD")


def test_closure_returns_frozenset_and_does_not_mutate_inputs():
    attrs = {"A"}
    fds = [fd("A", "B")]
    result = closure(attrs, fds)
    assert isinstance(result, frozenset)
    assert attrs == {"A"} and fds == [fd("A", "B")]


def test_closure_with_no_fds_and_empty_lhs():
    assert closure({"A", "B"}, []) == frozenset("AB")
    assert closure(set(), [fd("", "X")]) == frozenset("X")


# --- candidate keys --------------------------------------------------------------------------

def test_single_key_chain():
    assert candidate_keys(set("ABC"), [fd("A", "B"), fd("B", "C")]) == fs("A")


def test_attributes_not_in_any_fd_must_be_in_the_key():
    assert candidate_keys(set("ABCD"), [fd("A", "B"), fd("B", "C")]) == fs("AD")


def test_no_fds_key_is_everything():
    assert candidate_keys(set("AB"), []) == fs("AB")


def test_multiple_candidate_keys():
    # AB -> C, C -> B: ключі AB і AC
    assert candidate_keys(set("ABC"), [fd("AB", "C"), fd("C", "B")]) == fs("AB", "AC")


def test_keys_are_minimal():
    # A -> BC: ключ лише A, а не AB
    assert candidate_keys(set("ABC"), [fd("A", "BC")]) == fs("A")


def test_mutual_dependency_gives_two_keys():
    assert candidate_keys(set("ABC"), [fd("A", "B"), fd("B", "A"), fd("A", "C")]) == fs("A", "B")


# --- is_3nf ----------------------------------------------------------------------------------

def test_transitive_dependency_violates_3nf():
    assert is_3nf(set("ABC"), [fd("A", "B"), fd("B", "C")]) is False


def test_all_determined_by_key_is_3nf():
    assert is_3nf(set("ABCD"), [fd("A", "BCD")]) is True


def test_3nf_but_not_bcnf():
    # AB -> C, C -> B: C не суперключ, але B простий (входить у ключ AB)
    assert is_3nf(set("ABC"), [fd("AB", "C"), fd("C", "B")]) is True


def test_partial_dependency_violates_3nf():
    # ключ AB, але B -> C залежить від частини ключа (C не простий)
    assert is_3nf(set("ABC"), [fd("AB", "C"), fd("B", "C")]) is False


def test_trivial_fds_are_ignored():
    assert is_3nf(set("AB"), [fd("AB", "A"), fd("A", "A")]) is True


def test_no_fds_is_3nf():
    assert is_3nf(set("ABC"), []) is True


def test_order_table_example():
    attrs = set(["order_id", "customer_id", "email", "product_id", "product_name", "qty"])
    fds = [
        fd(["order_id"], ["customer_id"]),
        fd(["customer_id"], ["email"]),
        fd(["product_id"], ["product_name"]),
        fd(["order_id", "product_id"], ["qty"]),
    ]
    assert candidate_keys(attrs, fds) == fs(["order_id", "product_id"])
    assert is_3nf(attrs, fds) is False


# --- minimal_cover ---------------------------------------------------------------------------

def equivalent(fds1, fds2):
    attrs = set().union(*[set(l) | set(r) for l, r in list(fds1) + list(fds2)]) if (fds1 or fds2) else set()
    for n in range(len(attrs) + 1):
        for combo in combinations(sorted(attrs), n):
            if closure(set(combo), fds1) != closure(set(combo), fds2):
                return False
    return True


COVER_CASES = [
    [fd("A", "BC"), fd("B", "C"), fd("A", "B"), fd("AB", "C")],
    [fd("AB", "CD"), fd("A", "C"), fd("C", "D"), fd("B", "D")],
    [fd("A", "B"), fd("B", "A"), fd("A", "C"), fd("C", "A"), fd("B", "C")],
    [fd("ABC", "D"), fd("A", "B"), fd("B", "C")],
    [],
]


@pytest.mark.parametrize("fds", COVER_CASES)
def test_minimal_cover_properties(fds):
    original = [(set(l), set(r)) for l, r in fds]
    cover = minimal_cover(fds)
    assert fds == original  # вхід не змінено
    assert equivalent(fds, cover)
    for lhs, rhs in cover:
        assert isinstance(lhs, frozenset) and isinstance(rhs, frozenset)
        assert len(rhs) == 1 and not rhs <= lhs  # (1) права частина один атрибут, нетривіальна
        for a in lhs:  # (2) жодного зайвого атрибута зліва
            if len(lhs) > 1:
                assert not rhs <= closure(lhs - {a}, cover)
    for i, one in enumerate(cover):  # (3) жодна FD не випливає з решти
        rest = cover[:i] + cover[i + 1:]
        assert not one[1] <= closure(one[0], rest)
    assert len(set(cover)) == len(cover)


def test_minimal_cover_known_result():
    cover = minimal_cover([fd("A", "BC"), fd("B", "C"), fd("A", "B"), fd("AB", "C")])
    assert set(cover) == {(frozenset("A"), frozenset("B")), (frozenset("B"), frozenset("C"))}


# --- synthesize_3nf --------------------------------------------------------------------------

def test_synthesis_chain_plus_key_relation():
    # A -> B, B -> C, D окремо: ключ AD не міститься в жодній схемі, додається
    assert synthesize_3nf(set("ABCD"), [fd("A", "B"), fd("B", "C")]) == fs("AB", "BC", "AD")


def test_synthesis_merges_same_lhs():
    assert synthesize_3nf(set("ABC"), [fd("A", "B"), fd("A", "C")]) == fs("ABC")


def test_synthesis_drops_redundant_fds():
    fds = [fd("A", "B"), fd("B", "C"), fd("A", "C"), fd("AB", "C")]
    assert synthesize_3nf(set("ABC"), fds) == fs("AB", "BC")


def test_synthesis_without_fds_keeps_relation():
    assert synthesize_3nf(set("AB"), []) == fs("AB")


def test_synthesis_adds_key_for_independent_fds():
    assert synthesize_3nf(set("ABCD"), [fd("A", "B"), fd("C", "D")]) == fs("AB", "CD", "AC")


def test_synthesis_does_not_add_key_when_a_schema_already_has_it():
    # ключ A міститься в схемі ABC
    assert synthesize_3nf(set("ABC"), [fd("A", "BC")]) == fs("ABC")


def test_synthesis_removes_subsumed_schemas():
    fds = [fd("A", "B"), fd("AB", "C")]  # AB -> C редукується до A -> C: усе в одній схемі
    assert synthesize_3nf(set("ABC"), fds) == fs("ABC")


def test_synthesis_result_covers_all_attributes_and_has_a_key():
    attrs = set("ABCDEF")
    fds = [fd("A", "B"), fd("B", "C"), fd("D", "E")]
    result = synthesize_3nf(attrs, fds)
    assert set().union(*result) == attrs
    keys = candidate_keys(attrs, fds)
    assert any(k <= s for s in result for k in keys)
    assert not any(a < b for a in result for b in result)
