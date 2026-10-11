import itertools

import pytest

from solution import Spec, all_of, any_of, spec


@spec
def active(u):
    return u["active"]


@spec
def not_banned(u):
    return not u["banned"]


@spec("is admin")
def admin(u):
    return u["role"] == "admin"


def user(active=True, banned=False, role="user"):
    return {"active": active, "banned": banned, "role": role}


# --- базові ------------------------------------------------------------------------------------

def test_spec_decorator_without_and_with_name():
    assert isinstance(active, Spec) and active.name == "active"
    assert admin.name == "is admin"
    assert active(user()) is True
    assert active(user(active=False)) is False


def test_result_is_coerced_to_bool():
    s = Spec(lambda x: x, "truthy")
    assert s("text") is True
    assert s("") is False
    assert s(None) is False


def test_repr():
    assert repr(active) == "Spec(active)"
    assert repr(active & admin) == "Spec((active AND is admin))"


def test_names_of_composites():
    assert (active & not_banned).name == "(active AND not_banned)"
    assert (active | admin).name == "(active OR is admin)"
    assert (~active).name == "NOT active"
    assert (active & (not_banned | admin)).name == "(active AND (not_banned OR is admin))"
    assert (~(active & admin)).name == "NOT (active AND is admin)"


def test_decorated_function_with_explicit_spec_class():
    s = Spec(lambda n: n > 3, "big")
    assert s(5) and not s(1)


# --- логіка ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("a, b", list(itertools.product([False, True], repeat=2)))
def test_truth_tables(a, b):
    sa, sb = Spec(lambda _: a, "a"), Spec(lambda _: b, "b")
    assert (sa & sb)(None) is (a and b)
    assert (sa | sb)(None) is (a or b)
    assert (~sa)(None) is (not a)


def test_realistic_policy():
    can_login = active & not_banned
    can_admin = can_login & admin
    assert can_login(user())
    assert not can_login(user(banned=True))
    assert can_admin(user(role="admin"))
    assert not can_admin(user())
    assert (can_admin | ~active)(user(active=False))


def test_operations_create_new_objects_and_leave_operands_intact():
    both = active & admin
    assert both is not active and both is not admin
    assert active(user()) and active.name == "active"


# --- лінь ---------------------------------------------------------------------------------------------

def counting(result):
    calls = []

    def fn(x):
        calls.append(x)
        return result

    return Spec(fn, f"c{result}"), calls


def test_and_is_lazy():
    first, c1 = counting(False)
    second, c2 = counting(True)
    assert (first & second)("x") is False
    assert c1 == ["x"] and c2 == []


def test_and_evaluates_second_when_first_is_true():
    first, _ = counting(True)
    second, c2 = counting(True)
    assert (first & second)("x") is True
    assert c2 == ["x"]


def test_or_is_lazy():
    first, c1 = counting(True)
    second, c2 = counting(False)
    assert (first | second)("x") is True
    assert c2 == []


def test_or_evaluates_second_when_first_is_false():
    first, _ = counting(False)
    second, c2 = counting(True)
    assert (first | second)("x") is True
    assert c2 == ["x"]


def test_guard_pattern_protects_second_check():
    # типове застосування лінощів: друга перевірка безпечна лише якщо перша пройшла
    has_owner = Spec(lambda r: r.get("owner") is not None, "has owner")
    owner_is_ann = Spec(lambda r: r["owner"]["name"] == "ann", "owner is ann")
    assert not (has_owner & owner_is_ann)({"owner": None})


# --- типи ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("other", [1, True, None, "x", lambda o: True])
def test_operators_with_non_specs_are_type_errors(other):
    with pytest.raises(TypeError):
        active & other
    with pytest.raises(TypeError):
        active | other
    with pytest.raises(TypeError):
        other & active
    with pytest.raises(TypeError):
        other | active


# --- failures ----------------------------------------------------------------------------------------

def test_failures_of_leaf():
    assert active.failures(user()) == []
    assert active.failures(user(active=False)) == ["active"]


def test_failures_of_and_reports_every_failed_operand():
    rule = active & not_banned & admin
    assert rule.failures(user()) == ["is admin"]
    assert rule.failures(user(active=False, banned=True)) == ["active", "not_banned", "is admin"]
    assert rule.failures(user(role="admin")) == []


def test_failures_of_and_does_not_short_circuit():
    first, _ = counting(False)
    second, c2 = counting(False)
    assert (first & second).failures("x") == ["cFalse", "cFalse"]
    assert c2 == ["x"]


def test_failures_of_or_is_empty_if_any_passes():
    rule = admin | not_banned
    assert rule.failures(user()) == []
    assert rule.failures(user(role="admin", banned=True)) == []


def test_failures_of_or_lists_all_when_none_passes():
    rule = admin | not_banned
    assert rule.failures(user(banned=True)) == ["is admin", "not_banned"]


def test_failures_of_not():
    assert (~admin).failures(user()) == []
    assert (~admin).failures(user(role="admin")) == ["NOT is admin"]


def test_failures_of_nested_composite():
    rule = active & (admin | ~not_banned)
    assert rule.failures(user()) == ["is admin", "NOT not_banned"]
    assert rule.failures(user(active=False, banned=True)) == ["active"]  # права гілка OR пройшла
    assert rule.failures(user(active=False)) == ["active", "is admin", "NOT not_banned"]


@pytest.mark.parametrize("a, b, c", list(itertools.product([False, True], repeat=3)))
def test_failures_empty_iff_spec_true(a, b, c):
    sa, sb, sc = (Spec(lambda _, v=v: v, n) for v, n in ((a, "a"), (b, "b"), (c, "c")))
    for rule in (sa & sb | sc, sa & (sb | sc), ~(sa | sb) & sc, ~sa | ~sb | sc, ~(sa & ~sb)):
        assert (rule.failures(None) == []) == rule(None)


# --- all_of / any_of --------------------------------------------------------------------------------

def test_all_of_and_any_of():
    assert all_of(active, not_banned)(user()) is True
    assert all_of(active, not_banned)(user(banned=True)) is False
    assert any_of(admin, not_banned)(user()) is True
    assert any_of(admin, active)(user(active=False)) is False


def test_all_of_name_and_laziness():
    assert all_of(active, not_banned, admin).name == "((active AND not_banned) AND is admin)"
    first, _ = counting(False)
    second, c2 = counting(True)
    all_of(first, second)("x")
    assert c2 == []


def test_empty_all_of_and_any_of():
    assert all_of()(None) is True and all_of().name == "TRUE"
    assert any_of()(None) is False and any_of().name == "FALSE"
    assert all_of().failures(None) == []


def test_single_element_behaves_like_the_element():
    assert all_of(admin)(user(role="admin")) is True
    assert any_of(admin)(user()) is False


@pytest.mark.parametrize("bad", [lambda o: True, 5, None])
def test_all_of_any_of_accept_only_specs(bad):
    with pytest.raises(TypeError):
        all_of(active, bad)
    with pytest.raises(TypeError):
        any_of(bad)
