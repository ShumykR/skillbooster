import pytest

from solution import GuardRejected, InvalidTransition, StateMachine, TransitionError, analyze

ORDER = {
    ("new", "pay"): "paid",
    ("new", "cancel"): "cancelled",
    ("paid", "ship"): "shipped",
    ("paid", "refund"): "refunded",
    ("shipped", "deliver"): "delivered",
    ("delivered", "return"): "refunded",
}


def make(**kw):
    return StateMachine(ORDER, "new", **kw)


# --- аналіз таблиці --------------------------------------------------------------------------

def test_analyze_finds_terminal_states():
    r = analyze(ORDER, "new")
    assert r["terminal"] == {"cancelled", "refunded"}
    assert r["unreachable"] == set()


def test_analyze_finds_unreachable_states():
    table = dict(ORDER)
    table[("limbo", "wake")] = "paid"
    table[("paid", "audit")] = "audited"
    r = analyze(table, "new")
    assert r["unreachable"] == {"limbo"}
    assert "audited" in r["terminal"]


def test_analyze_unreachable_cannot_be_terminal():
    table = {("a", "go"): "b", ("x", "go"): "y"}
    r = analyze(table, "a")
    assert r["unreachable"] == {"x", "y"}
    assert r["terminal"] == {"b"}


def test_analyze_handles_cycles():
    table = {("a", "next"): "b", ("b", "next"): "a"}
    r = analyze(table, "a")
    assert r == {"unreachable": set(), "terminal": set()}


def test_analyze_initial_without_transitions_is_terminal():
    assert analyze({}, "only") == {"unreachable": set(), "terminal": {"only"}}


def test_analyze_initial_unknown_to_table_counts_and_everything_else_is_unreachable():
    r = analyze({("a", "go"): "b"}, "z")
    assert r["unreachable"] == {"a", "b"}
    assert r["terminal"] == {"z"}


@pytest.mark.parametrize("bad", ["", None, 5])
def test_analyze_bad_initial(bad):
    with pytest.raises(ValueError):
        analyze(ORDER, bad)


# --- основна поведінка -------------------------------------------------------------------------

def test_happy_path_and_history():
    m = make()
    assert m.state == "new"
    assert m.fire("pay") == "paid"
    assert m.fire("ship") == "shipped"
    assert m.fire("deliver") == "delivered"
    assert m.state == "delivered"
    assert m.history == [("new", "pay", "paid"), ("paid", "ship", "shipped"), ("shipped", "deliver", "delivered")]


def test_invalid_event_for_current_state():
    m = make()
    with pytest.raises(InvalidTransition):
        m.fire("ship")  # відвантажити неоплачене
    assert m.state == "new"
    assert m.history == []


def test_unknown_event():
    with pytest.raises(InvalidTransition):
        make().fire("explode")


def test_error_hierarchy():
    assert issubclass(InvalidTransition, TransitionError)
    assert issubclass(GuardRejected, TransitionError)
    assert not issubclass(GuardRejected, InvalidTransition)


def test_terminal_state_accepts_nothing():
    m = make()
    m.fire("cancel")
    assert m.available() == []
    assert not m.can("pay")
    with pytest.raises(InvalidTransition):
        m.fire("pay")


def test_two_paths_to_same_state():
    m = make()
    m.fire("pay")
    m.fire("refund")
    assert m.state == "refunded"


def test_available_is_sorted_and_reflects_state():
    m = make()
    assert m.available() == ["cancel", "pay"]
    m.fire("pay")
    assert m.available() == ["refund", "ship"]


def test_can_matches_fire():
    m = make()
    assert m.can("pay") and not m.can("ship") and not m.can("???")


def test_history_is_a_copy():
    m = make()
    m.fire("pay")
    m.history.append(("x", "y", "z"))
    m.history.clear()
    assert m.history == [("new", "pay", "paid")]


def test_table_is_copied_at_creation():
    table = dict(ORDER)
    m = StateMachine(table, "new")
    table[("new", "hack")] = "delivered"
    del table[("new", "pay")]
    assert m.can("pay") and not m.can("hack")


def test_instances_do_not_share_state():
    a, b = make(), make()
    a.fire("pay")
    assert b.state == "new" and b.history == []


@pytest.mark.parametrize("initial", ["ghost", "", None])
def test_initial_must_be_in_table(initial):
    with pytest.raises(ValueError):
        StateMachine(ORDER, initial)


# --- охоронці й хук ----------------------------------------------------------------------------

def test_guard_blocks_transition_without_side_effects():
    m = make(guards={("paid", "ship"): lambda ctx: ctx.get("address") is not None})
    m.fire("pay")
    with pytest.raises(GuardRejected):
        m.fire("ship")
    assert m.state == "paid"
    assert m.history == [("new", "pay", "paid")]
    assert m.fire("ship", {"address": "Kyiv"}) == "shipped"


def test_guard_affects_available_and_can():
    m = make(guards={("paid", "refund"): lambda ctx: ctx.get("days", 0) <= 14})
    m.fire("pay")
    assert m.available({"days": 30}) == ["ship"]
    assert m.available({"days": 3}) == ["refund", "ship"]
    assert not m.can("refund", {"days": 30})
    assert m.can("refund", {"days": 3})
    assert m.can("refund")  # ctx за замовчуванням порожній -> days=0 -> дозволено


def test_guard_default_ctx_is_empty_dict():
    seen = []
    m = make(guards={("new", "pay"): lambda ctx: seen.append(ctx) or True})
    m.fire("pay")
    assert seen == [{}]


def test_guard_runs_only_for_its_transition():
    calls = []
    m = make(guards={("new", "pay"): lambda ctx: calls.append(1) or True})
    m.fire("cancel")
    assert calls == []


def test_guard_not_consulted_for_invalid_event():
    calls = []
    m = make(guards={("paid", "ship"): lambda ctx: calls.append(1) or True})
    with pytest.raises(InvalidTransition):
        m.fire("ship")  # зі стану new переходу немає: це InvalidTransition, а не GuardRejected
    assert calls == []


def test_guard_falsy_values_reject():
    for falsy in (0, None, "", []):
        m = make(guards={("new", "pay"): lambda ctx, v=falsy: v})
        with pytest.raises(GuardRejected):
            m.fire("pay")


def test_hook_gets_old_event_new_and_ctx_after_state_changed():
    seen = []
    holder = {}

    def hook(old, event, new, ctx):
        seen.append((old, event, new, ctx, holder["m"].state, list(holder["m"].history)))

    m = make(on_transition=hook)
    holder["m"] = m
    ctx = {"who": "ann"}
    m.fire("pay", ctx)
    old, event, new, got_ctx, state_now, hist_now = seen[0]
    assert (old, event, new) == ("new", "pay", "paid")
    assert got_ctx is ctx
    assert state_now == "paid"
    assert hist_now == [("new", "pay", "paid")]


def test_hook_not_called_on_rejected_transitions():
    calls = []
    m = make(guards={("new", "pay"): lambda ctx: False}, on_transition=lambda *a: calls.append(a))
    for event in ("pay", "ship"):
        with pytest.raises(TransitionError):
            m.fire(event)
    assert calls == []


def test_hook_error_propagates_but_transition_is_already_done():
    def hook(*a):
        raise RuntimeError("notify failed")

    m = make(on_transition=hook)
    with pytest.raises(RuntimeError):
        m.fire("pay")
    assert m.state == "paid"
    assert m.history == [("new", "pay", "paid")]


def test_machine_with_loop():
    m = StateMachine({("idle", "start"): "running", ("running", "stop"): "idle"}, "idle")
    for _ in range(3):
        m.fire("start")
        m.fire("stop")
    assert m.state == "idle" and len(m.history) == 6
