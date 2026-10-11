import pytest

from solution import StrategyRegistry, UnknownStrategy, capped, fixed_off, percent_off


@pytest.fixture
def reg():
    r = StrategyRegistry()
    r.register("ten")(percent_off(10))
    r.register("five_uah")(fixed_off(500))
    return r


# --- реєстр ----------------------------------------------------------------------------------

def test_register_returns_function_unchanged_and_get_finds_it():
    r = StrategyRegistry()

    @r.register("zero")
    def zero(total, ctx):
        return 0

    assert zero(100, {}) == 0
    assert r.get("zero") is zero


def test_names_are_sorted(reg):
    assert reg.names() == ["five_uah", "ten"]


def test_duplicate_name_is_rejected_and_keeps_the_first(reg):
    with pytest.raises(ValueError):
        reg.register("ten")(fixed_off(1))
    assert reg.apply(1000, ["ten"]) == 900


@pytest.mark.parametrize("bad", ["", None, 5, b"x"])
def test_bad_names_are_rejected(bad):
    with pytest.raises(ValueError):
        StrategyRegistry().register(bad)


def test_unknown_name_in_get():
    with pytest.raises(UnknownStrategy):
        StrategyRegistry().get("nope")


def test_unknown_strategy_is_a_key_error():
    assert issubclass(UnknownStrategy, KeyError)


def test_registries_are_independent():
    a, b = StrategyRegistry(), StrategyRegistry()
    a.register("x")(fixed_off(1))
    assert b.names() == []


# --- apply -----------------------------------------------------------------------------------

def test_rules_are_applied_sequentially_to_the_running_total(reg):
    # 10% від 10000 = 1000 -> 9000; потім мінус 500 -> 8500
    assert reg.apply(10_000, ["ten", "five_uah"]) == 8_500
    # у зворотному порядку: 10000-500=9500, 10% від 9500 = 950 -> 8550
    assert reg.apply(10_000, ["five_uah", "ten"]) == 8_550


def test_empty_list_changes_nothing(reg):
    assert reg.apply(1234, []) == 1234


def test_same_rule_can_be_applied_twice(reg):
    assert reg.apply(10_000, ["ten", "ten"]) == 8_100


def test_discount_never_makes_total_negative(reg):
    assert reg.apply(300, ["five_uah"]) == 0
    assert reg.apply(300, ["five_uah", "five_uah"]) == 0


def test_unknown_name_fails_before_any_rule_runs():
    calls = []
    r = StrategyRegistry()

    @r.register("spy")
    def spy(total, ctx):
        calls.append(total)
        return 1

    with pytest.raises(UnknownStrategy):
        r.apply(100, ["spy", "ghost"])
    assert calls == []


def test_ctx_is_shared_and_defaults_to_empty_dict():
    seen = []
    r = StrategyRegistry()

    @r.register("vip")
    def vip(total, ctx):
        seen.append(ctx)
        return total // 2 if ctx.get("vip") else 0

    ctx = {"vip": True}
    assert r.apply(1000, ["vip"], ctx) == 500
    assert seen[0] is ctx
    assert r.apply(1000, ["vip"]) == 1000
    assert seen[1] == {}


@pytest.mark.parametrize("bad", [-1, 1.5, "5", None, True])
def test_total_must_be_non_negative_int(reg, bad):
    with pytest.raises(ValueError):
        reg.apply(bad, ["ten"])


@pytest.mark.parametrize("result", [-1, 0.5, "1", None, True])
def test_rule_must_return_non_negative_int(result):
    r = StrategyRegistry()
    r.register("bad")(lambda total, ctx: result)
    with pytest.raises(ValueError):
        r.apply(100, ["bad"])


def test_new_strategy_needs_no_change_in_the_engine():
    r = StrategyRegistry()

    @r.register("black_friday")
    def black_friday(total, ctx):
        return total * 30 // 100

    assert r.apply(2000, ["black_friday"]) == 1400


# --- фабрики ---------------------------------------------------------------------------------

def test_percent_off_uses_integer_division():
    rule = percent_off(15)
    assert rule(999, {}) == 149
    assert rule(0, {}) == 0
    assert percent_off(0)(500, {}) == 0
    assert percent_off(100)(500, {}) == 500


@pytest.mark.parametrize("bad", [-1, 101, 10.5, "10", None, True])
def test_percent_off_validates_at_creation(bad):
    with pytest.raises(ValueError):
        percent_off(bad)


def test_fixed_off():
    assert fixed_off(250)(10_000, {}) == 250
    assert fixed_off(0)(10, {}) == 0


@pytest.mark.parametrize("bad", [-1, 2.5, "5", None, True])
def test_fixed_off_validates_at_creation(bad):
    with pytest.raises(ValueError):
        fixed_off(bad)


def test_capped_limits_the_discount_and_passes_arguments_through():
    seen = []

    def spy(total, ctx):
        seen.append((total, ctx))
        return total

    rule = capped(spy, 700)
    assert rule(1000, {"a": 1}) == 700
    assert rule(300, {}) == 300
    assert seen[0] == (1000, {"a": 1})


def test_capped_composes_with_registry():
    r = StrategyRegistry()
    r.register("promo")(capped(percent_off(50), 1000))
    assert r.apply(10_000, ["promo"]) == 9_000
    assert r.apply(1_000, ["promo"]) == 500


@pytest.mark.parametrize("bad", [-1, 1.5, None, True])
def test_capped_validates_the_cap(bad):
    with pytest.raises(ValueError):
        capped(fixed_off(1), bad)
