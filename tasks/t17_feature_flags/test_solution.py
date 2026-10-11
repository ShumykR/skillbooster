import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from solution import is_enabled

HERE = Path(__file__).resolve().parent
USERS = [f"user-{i}" for i in range(10_000)]


def enabled_set(flag, percent, users=USERS, **kw):
    return {u for u in users if is_enabled(flag, u, percent, **kw)}


def test_zero_and_hundred_percent():
    assert enabled_set("f", 0) == set()
    assert enabled_set("f", 100) == set(USERS)
    assert enabled_set("f", 0.0) == set()
    assert enabled_set("f", 100.0) == set(USERS)


@pytest.mark.parametrize("percent", [-0.1, -1, 100.1, 101, 1000])
def test_percent_out_of_range(percent):
    with pytest.raises(ValueError):
        is_enabled("f", "u", percent)


def test_result_is_bool():
    assert is_enabled("f", "u1", 50) in (True, False)
    assert isinstance(is_enabled("f", "u1", 50), bool)


def test_same_inputs_same_result():
    first = [is_enabled("f", u, 37) for u in USERS[:500]]
    assert first == [is_enabled("f", u, 37) for u in USERS[:500]]


@pytest.mark.parametrize("percent", [1, 10, 30, 50, 90])
def test_distribution_is_roughly_uniform(percent):
    count = len(enabled_set("checkout-v2", percent))
    expected = len(USERS) * percent / 100
    sigma = (len(USERS) * (percent / 100) * (1 - percent / 100)) ** 0.5
    assert abs(count - expected) < 5 * sigma + 1, (count, expected)


def test_monotonic_growth():
    previous = set()
    for percent in (1, 5, 10, 25, 50, 75, 99, 100):
        current = enabled_set("search-ai", percent)
        assert previous <= current, f"при {percent}% хтось втратив доступ"
        previous = current
    assert previous == set(USERS)


def test_small_increase_adds_only_a_few_users():
    at_10 = enabled_set("f", 10)
    at_11 = enabled_set("f", 11)
    assert at_10 <= at_11
    assert 0 < len(at_11 - at_10) < 300  # ≈ 100 ± запас


def test_flags_are_independent():
    a = enabled_set("flag-a", 50)
    b = enabled_set("flag-b", 50)
    overlap = len(a & b)
    # незалежні прапорці: перетин ≈ 25% користувачів (2500 ± запас), а не 50% і не 0
    assert 2000 < overlap < 3000, overlap
    assert a != b


def test_stable_across_processes_with_different_hash_seeds():
    code = (
        "import json, sys; sys.path.insert(0, sys.argv[1]);"
        "from solution import is_enabled;"
        "print(json.dumps([is_enabled('new-ui', f'u{i}', 40) for i in range(300)]))"
    )
    results = []
    for seed in ("1", "2", "random"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        out = subprocess.run(
            [sys.executable, "-c", code, str(HERE)], capture_output=True, text=True, env=env, check=True
        ).stdout
        results.append(json.loads(out))
    local = [is_enabled("new-ui", f"u{i}", 40) for i in range(300)]
    assert results[0] == results[1] == results[2] == local
    assert 0 < sum(local) < 300


def test_deny_beats_everything():
    users = USERS[:200]
    assert enabled_set("f", 100, users, deny=set(users[:50])) == set(users[50:])
    assert enabled_set("f", 100, users, allow=set(users[:10]), deny=set(users[:10])) == set(users[10:])


def test_allow_forces_on_at_zero_percent():
    users = USERS[:100]
    assert enabled_set("f", 0, users, allow=["user-3", "user-7"]) == {"user-3", "user-7"}


def test_allow_and_deny_accept_lists_sets_tuples():
    assert is_enabled("f", "vip", 0, allow=["vip"]) is True
    assert is_enabled("f", "vip", 0, allow={"vip"}) is True
    assert is_enabled("f", "vip", 100, deny=("vip",)) is False


def test_allow_deny_do_not_affect_other_users():
    base = enabled_set("f", 30, USERS[:1000])
    with_lists = enabled_set("f", 30, USERS[:1000], allow=["nobody"], deny=["ghost"])
    assert base == with_lists


def test_different_user_ids_with_common_prefix_are_not_correlated():
    users = [f"u{i}" for i in range(2000)]
    got = enabled_set("f", 50, users)
    assert 850 < len(got) < 1150
    evens = sum(1 for i in range(0, 2000, 2) if users[i] in got)
    assert 400 < evens < 600
