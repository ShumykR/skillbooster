import calendar

import pytest

from solution import BudgetManager, cost

PRICES = {"big": {"in": 3, "out": 15}, "mid": {"in": 1, "out": 5}, "small": {"in": 0.1, "out": 0.4}}
MODELS = ["big", "mid", "small"]


def ts(y, m, d, h=12, minute=0, s=0):
    return float(calendar.timegm((y, m, d, h, minute, s)))


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


def make(limits=None, now=None):
    clock = Clock(now or ts(2026, 3, 15))
    limits = {"user_daily": 0.05, "user_monthly": 0.5, "global_monthly": 1.0} if limits is None else limits
    return clock, BudgetManager(PRICES, limits, clock)


def spend(mgr, user, micro_dollars, model="mid"):
    """Витрачає рівно micro_dollars µ$ (ціна mid: 1 µ$ за вхідний токен)."""
    return mgr.record(user, model, {"prompt_tokens": micro_dollars})


# ---------- cost --------------------------------------------------------------------------------------------------


def test_cost_per_model():
    assert cost(PRICES, "big", {"prompt_tokens": 1000, "completion_tokens": 500}) == 0.0105
    assert cost(PRICES, "small", {"prompt_tokens": 1000, "completion_tokens": 500}) == 0.0003
    assert cost(PRICES, "mid", {"prompt_tokens": 2000}) == 0.002, "completion_tokens необовʼязкові"
    assert cost(PRICES, "mid", {"prompt_tokens": 0, "completion_tokens": 0}) == 0.0
    assert cost(PRICES, "big", {"prompt_tokens": 1, "completion_tokens": 1}) == 0.000018


@pytest.mark.parametrize("model, usage", [
    ("nope", {"prompt_tokens": 1}), ("big", {}), ("big", {"completion_tokens": 5}),
    ("big", {"prompt_tokens": -1}), ("big", {"prompt_tokens": 1, "completion_tokens": -1})])
def test_cost_validation(model, usage):
    with pytest.raises(ValueError):
        cost(PRICES, model, usage)


# ---------- accounting -----------------------------------------------------------------------------------------------


def test_record_returns_cost_and_keeps_events():
    clock, m = make()
    assert m.record("ann", "big", {"prompt_tokens": 1000, "completion_tokens": 500}) == 0.0105
    clock.now += 60
    m.record("bob", "small", {"prompt_tokens": 1000, "completion_tokens": 500})
    assert m.events == [{"ts": ts(2026, 3, 15), "user": "ann", "model": "big", "cost": 0.0105},
                        {"ts": ts(2026, 3, 15) + 60, "user": "bob", "model": "small", "cost": 0.0003}]
    m.events.clear()
    assert len(m.events) == 2, "events повертає копію"


def test_spent_per_user_and_globally():
    _, m = make()
    spend(m, "ann", 10_000)
    spend(m, "ann", 5_000)
    spend(m, "bob", 1_000)
    assert m.spent("ann", "day") == 0.015 and m.spent("ann", "month") == 0.015
    assert m.spent("bob", "day") == 0.001 and m.spent("zed", "day") == 0.0
    assert m.global_spent() == 0.016
    with pytest.raises(ValueError):
        m.spent("ann", "week")


def test_day_rollover_resets_daily_but_not_monthly():
    clock, m = make()
    spend(m, "ann", 20_000)
    clock.now = ts(2026, 3, 15, 23, 59, 59)
    assert m.spent("ann", "day") == 0.02
    clock.now = ts(2026, 3, 16, 0, 0, 0)
    assert m.spent("ann", "day") == 0.0 and m.spent("ann", "month") == 0.02 and m.global_spent() == 0.02


def test_month_rollover_resets_everything():
    clock, m = make()
    clock.now = ts(2026, 3, 31, 23, 59, 59)
    spend(m, "ann", 20_000)
    clock.now = ts(2026, 4, 1, 0, 0, 0)
    assert m.spent("ann", "month") == 0.0 and m.global_spent() == 0.0 and m.spent("ann", "day") == 0.0


def test_same_month_in_a_different_year_is_a_different_month():
    clock, m = make(now=ts(2025, 3, 15))
    spend(m, "ann", 10_000)
    clock.now = ts(2026, 3, 15)
    assert m.spent("ann", "month") == 0.0 and m.global_spent() == 0.0


# ---------- remaining ---------------------------------------------------------------------------------------------------


def test_remaining_is_the_tightest_limit():
    clock, m = make()
    assert m.remaining("ann") == 0.05
    spend(m, "ann", 30_000)
    assert m.remaining("ann") == 0.02
    _, tight_month = make({"user_daily": 1.0, "user_monthly": 0.04, "global_monthly": 1.0})
    spend(tight_month, "ann", 10_000)
    assert tight_month.remaining("ann") == 0.03
    _, tight_global = make({"user_daily": 1.0, "user_monthly": 1.0, "global_monthly": 0.02})
    spend(tight_global, "bob", 15_000)
    assert tight_global.remaining("ann") == 0.005, "глобальний бюджет вичерпують інші"


def test_remaining_never_negative_and_without_limits_is_infinite():
    _, m = make()
    spend(m, "ann", 70_000)
    assert m.remaining("ann") == 0.0
    _, free = make({})
    spend(free, "ann", 1_000_000)
    assert free.remaining("ann") == float("inf")
    _, partial = make({"user_daily": None, "user_monthly": 0.1})
    assert partial.remaining("ann") == 0.1


# ---------- plan --------------------------------------------------------------------------------------------------------------


def test_plan_picks_the_preferred_model_when_it_fits():
    _, m = make()
    assert m.plan("ann", MODELS, 1000, 500) == {"model": "big", "reason": "ok", "estimated_cost": 0.0105, "warning": False}


def test_plan_falls_back_to_a_cheaper_model():
    _, m = make()
    spend(m, "ann", 40_000)
    p = m.plan("ann", MODELS, 1000, 500)
    assert p == {"model": "mid", "reason": "fallback", "estimated_cost": 0.0035, "warning": True}


def test_plan_skips_models_that_do_not_fit_until_one_does():
    _, m = make()
    spend(m, "ann", 49_000)   # лишилось 0.001
    p = m.plan("ann", MODELS, 1000, 500)
    assert p["model"] == "small" and p["reason"] == "fallback" and p["estimated_cost"] == 0.0003


def test_estimate_equal_to_remaining_is_allowed():
    _, m = make()
    spend(m, "ann", 39_500)
    assert m.remaining("ann") == 0.0105
    assert m.plan("ann", MODELS, 1000, 500)["model"] == "big"


def test_budget_exhausted():
    _, m = make()
    spend(m, "ann", 49_990)   # лишилось 0.00001
    p = m.plan("ann", MODELS, 1000, 500)
    assert p == {"model": None, "reason": "budget_exhausted", "estimated_cost": 0.0003, "warning": False}
    assert m.plan("ann", ["big"], 1000, 500)["estimated_cost"] == 0.0105


def test_order_of_models_is_respected():
    _, m = make()
    assert m.plan("ann", ["small", "big"], 1000, 500)["model"] == "small"
    assert m.plan("ann", ["small", "big"], 1000, 500)["reason"] == "ok"


def test_warning_threshold_is_inclusive_and_configurable():
    _, m = make()
    spend(m, "ann", 29_500)   # +0.0105 = 0.04 = рівно 80% від 0.05
    assert m.plan("ann", MODELS, 1000, 500)["warning"] is True
    _, below = make()
    spend(below, "ann", 29_000)
    assert below.plan("ann", MODELS, 1000, 500)["warning"] is False
    _, custom = make({"user_daily": 0.05, "warn_at": 0.2})
    assert custom.plan("ann", MODELS, 1000, 500) == {"model": "big", "reason": "ok", "estimated_cost": 0.0105, "warning": True}


def test_warning_considers_every_limit():
    _, m = make({"user_daily": 10.0, "user_monthly": 10.0, "global_monthly": 0.02})
    spend(m, "bob", 8_000)
    assert m.plan("ann", MODELS, 1000, 500)["warning"] is True, "глобальний ліміт майже вичерпано"


def test_plan_validation():
    _, m = make()
    with pytest.raises(ValueError):
        m.plan("ann", [], 10, 10)
    with pytest.raises(ValueError):
        m.plan("ann", MODELS, -1, 10)
    with pytest.raises(ValueError):
        m.plan("ann", MODELS, 10, -1)
    with pytest.raises(ValueError):
        m.plan("ann", ["ghost"], 10, 10)


def test_unlimited_plan_always_takes_the_first_model():
    _, m = make({})
    spend(m, "ann", 5_000_000)
    assert m.plan("ann", MODELS, 100_000, 100_000) == {"model": "big", "reason": "ok", "estimated_cost": 1.8, "warning": False}
