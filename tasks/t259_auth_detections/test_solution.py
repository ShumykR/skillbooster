import copy
import random

import pytest

from solution import detect

KYIV = (50.45, 30.52, "UA")
LVIV = (49.84, 24.03, "UA")
BERLIN = (52.52, 13.40, "DE")
NYC = (40.71, -74.00, "US")
KYIV_NEAR = (50.90, 30.52, "UA")  # ~50 км від Києва


def ev(ts, type_, user="alice", ip="1.1.1.1", country="UA", geo=None):
    e = {"ts": ts, "type": type_, "user": user, "ip": ip, "country": country}
    if geo:
        e["lat"], e["lon"], e["country"] = geo
    return e


def fails(times, user="alice", ip="1.1.1.1"):
    return [ev(t, "login_failure", user, ip) for t in times]


def alert(rule, key, start, end, count, severity):
    return {"rule": rule, "key": key, "start": start, "end": end, "count": count, "severity": severity}


def rules(alerts):
    return [a["rule"] for a in alerts]


# --- вхід і форма -------------------------------------------------------------------------------

def test_empty_and_irrelevant():
    assert detect([]) == []
    assert detect([ev(1, "login_success"), ev(2, "something_else"), ev(3, "login_failure")]) == []


@pytest.mark.parametrize("bad", [None, {}, "x", ({"ts": 1},)])
def test_events_must_be_a_list(bad):
    with pytest.raises(ValueError):
        detect(bad)


def test_missing_ts_is_value_error():
    with pytest.raises(ValueError):
        detect([{"type": "login_failure", "user": "a", "ip": "i"}])


def test_input_is_not_mutated_and_order_does_not_matter():
    events = fails([0, 60, 120, 180, 240]) + [ev(10, "login_success", geo=KYIV), ev(20, "login_success", geo=NYC)]
    snapshot = copy.deepcopy(events)
    expected = detect(events)
    assert events == snapshot
    shuffled = events[:]
    random.Random(7).shuffle(shuffled)
    assert detect(shuffled) == expected
    assert len(expected) == 2


def test_alert_shape_is_exact():
    (a,) = detect(fails([0, 10, 20, 30, 40]))
    assert set(a) == {"rule", "key", "start", "end", "count", "severity"}


# --- bruteforce --------------------------------------------------------------------------------

def test_bruteforce_threshold():
    assert detect(fails([0, 60, 120, 180])) == []
    assert detect(fails([0, 60, 120, 180, 240])) == [alert("bruteforce", "alice", 0, 240, 5, "medium")]


def test_bruteforce_window_bounds_are_inclusive():
    assert rules(detect(fails([0, 75, 150, 225, 300]))) == ["bruteforce"]
    assert detect(fails([0, 75, 150, 225, 301])) == []


def test_bruteforce_counts_all_ips_but_only_one_user():
    events = [ev(i * 10, "login_failure", "alice", f"9.9.9.{i}") for i in range(5)]
    assert detect(events) == [alert("bruteforce", "alice", 0, 40, 5, "medium")]
    mixed = fails([0, 10, 20], "alice") + fails([30, 40], "bob")
    assert detect(mixed) == []


def test_bruteforce_same_second_events_count():
    assert rules(detect(fails([5, 5, 5, 5, 5]))) == ["bruteforce"]


def test_bruteforce_long_burst_is_one_merged_alert():
    got = detect(fails(range(0, 600, 60)))
    assert got == [alert("bruteforce", "alice", 0, 540, 10, "medium")]


def test_bruteforce_separate_bursts_are_separate_alerts():
    got = detect(fails([0, 10, 20, 30, 40] + [1000, 1010, 1020, 1030, 1040]))
    assert got == [alert("bruteforce", "alice", 0, 40, 5, "medium"),
                   alert("bruteforce", "alice", 1000, 1040, 5, "medium")]


def test_bruteforce_two_users_two_alerts_sorted():
    events = fails([100, 110, 120, 130, 140], "bob") + fails([0, 10, 20, 30, 40], "alice")
    assert [(a["key"], a["start"]) for a in detect(events)] == [("alice", 0), ("bob", 100)]


def test_successes_do_not_count_as_failures():
    events = fails([0, 10, 20, 30]) + [ev(40, "login_success")]
    assert detect(events) == []


# --- spraying ----------------------------------------------------------------------------------

def spray(n, ip="6.6.6.6", step=30, t0=0):
    return [ev(t0 + i * step, "login_failure", f"user{i}", ip) for i in range(n)]


def test_spraying_threshold():
    assert detect(spray(9)) == []
    assert detect(spray(10)) == [alert("spraying", "6.6.6.6", 0, 270, 10, "high")]


def test_spraying_window_bounds():
    ok = [ev(i * 66, "login_failure", f"u{i}", "6.6.6.6") for i in range(9)] + [ev(600, "login_failure", "u9", "6.6.6.6")]
    assert rules(detect(ok)) == ["spraying"]
    late = ok[:-1] + [ev(601, "login_failure", "u9", "6.6.6.6")]
    assert detect(late) == []


def test_spraying_needs_distinct_users_not_failures():
    events = [ev(i, "login_failure", "alice", "6.6.6.6") for i in range(12)]
    assert rules(detect(events)) == ["bruteforce"]


def test_spraying_per_ip():
    assert detect(spray(6, "1.1.1.1") + spray(6, "2.2.2.2")) == []


def test_spraying_long_campaign_merged():
    got = detect(spray(20, step=30))
    assert got == [alert("spraying", "6.6.6.6", 0, 570, 20, "high")]


# --- impossible_travel -------------------------------------------------------------------------

def test_impossible_travel_basic():
    events = [ev(1000, "login_success", geo=KYIV), ev(4600, "login_success", geo=NYC)]
    assert detect(events) == [alert("impossible_travel", "alice", 1000, 4600, 2, "high")]


def test_plausible_travel_is_fine():
    assert detect([ev(0, "login_success", geo=KYIV), ev(12 * 3600, "login_success", geo=NYC)]) == []
    assert detect([ev(0, "login_success", geo=KYIV), ev(7200, "login_success", geo=LVIV)]) == []


def test_speed_threshold_between_plausible_and_not():
    assert rules(detect([ev(0, "login_success", geo=KYIV), ev(3600, "login_success", geo=BERLIN)])) == ["impossible_travel"]
    assert detect([ev(0, "login_success", geo=KYIV), ev(5400, "login_success", geo=BERLIN)]) == []


def test_short_distance_is_ignored_even_if_instant():
    assert detect([ev(0, "login_success", geo=KYIV), ev(1, "login_success", geo=KYIV_NEAR)]) == []


def test_zero_elapsed_far_apart_is_alert():
    got = detect([ev(500, "login_success", geo=KYIV), ev(500, "login_success", geo=NYC)])
    assert rules(got) == ["impossible_travel"]


def test_only_adjacent_successes_with_coordinates_are_compared():
    events = [
        ev(0, "login_success", geo=KYIV),
        ev(100, "login_failure", geo=NYC),            # невдалий вхід не рахується
        ev(200, "login_success"),                      # без координат: ніби його немає
        ev(86400, "login_success", geo=NYC),           # добу потому: нормально
        ev(86400 + 600, "login_success", geo=KYIV),    # 10 хв після Нью-Йорка: алерт
    ]
    assert detect(events) == [alert("impossible_travel", "alice", 86400, 86400 + 600, 2, "high")]


def test_travel_is_per_user():
    events = [ev(0, "login_success", "alice", geo=KYIV), ev(60, "login_success", "bob", geo=NYC)]
    assert detect(events) == []


def test_flapping_gives_one_alert_per_pair():
    events = [ev(0, "login_success", geo=KYIV), ev(60, "login_success", geo=NYC),
              ev(120, "login_success", geo=KYIV)]
    got = detect(events)
    assert [(a["start"], a["end"]) for a in got] == [(0, 60), (60, 120)]


# --- mfa_fatigue -------------------------------------------------------------------------------

def pushes(times, user="alice"):
    return [ev(t, "mfa_push", user) for t in times]


def test_mfa_fatigue_threshold_and_window():
    assert detect(pushes([0, 100, 200, 300])) == []
    assert detect(pushes([0, 100, 200, 300, 400])) == [alert("mfa_fatigue", "alice", 0, 400, 5, "high")]
    assert rules(detect(pushes([0, 150, 300, 450, 600]))) == ["mfa_fatigue"]
    assert detect(pushes([0, 150, 300, 450, 601])) == []


def test_mfa_fatigue_becomes_critical_when_user_approves():
    base = pushes([0, 100, 200, 300, 400])
    got = detect(base + [ev(450, "mfa_approved")])
    assert got == [alert("mfa_fatigue", "alice", 0, 400, 5, "critical")]
    assert detect(base + [ev(1000, "mfa_approved")])[0]["severity"] == "critical"  # end + 600
    assert detect(base + [ev(1001, "mfa_approved")])[0]["severity"] == "high"
    assert detect(base + [ev(-1, "mfa_approved")])[0]["severity"] == "high"
    assert detect(base + [ev(450, "mfa_approved", "bob")])[0]["severity"] == "high"


def test_mfa_pushes_are_per_user():
    events = pushes([0, 100, 200], "alice") + pushes([300, 400], "bob")
    assert detect(events) == []


# --- new_country_after_reset -------------------------------------------------------------------

def history(user="alice", country="UA", times=(100, 200)):
    return [ev(t, "login_success", user, country=country) for t in times]


def test_new_country_after_reset():
    events = history() + [ev(1000, "password_reset"), ev(2000, "login_success", country="RO")]
    assert detect(events) == [alert("new_country_after_reset", "alice", 1000, 2000, 1, "critical")]


def test_known_country_after_reset_is_fine():
    events = history() + [ev(1000, "password_reset"), ev(2000, "login_success", country="UA")]
    assert detect(events) == []


def test_time_window_after_reset_is_inclusive_24h():
    base = history() + [ev(1000, "password_reset")]
    assert rules(detect(base + [ev(1000 + 86400, "login_success", country="RO")])) == ["new_country_after_reset"]
    assert detect(base + [ev(1000 + 86401, "login_success", country="RO")]) == []


def test_login_before_reset_is_not_an_alert_and_becomes_history():
    events = history() + [ev(500, "login_success", country="RO"), ev(1000, "password_reset"),
                          ev(2000, "login_success", country="RO")]
    assert detect(events) == []


def test_no_history_means_no_alert():
    events = [ev(1000, "password_reset"), ev(2000, "login_success", country="RO")]
    assert detect(events) == []


def test_history_is_per_user():
    events = history("alice", "UA") + history("bob", "RO") + [
        ev(1000, "password_reset", "alice"), ev(2000, "login_success", "alice", country="RO")]
    assert rules(detect(events)) == ["new_country_after_reset"]


def test_same_new_country_once_different_countries_separately():
    events = history() + [ev(1000, "password_reset"), ev(2000, "login_success", country="RO"),
                          ev(2100, "login_success", country="RO"), ev(2200, "login_success", country="PL")]
    got = detect(events)
    assert [(a["start"], a["end"]) for a in got] == [(1000, 2000), (1000, 2200)]


def test_latest_reset_is_the_baseline():
    events = history() + [ev(1000, "password_reset"), ev(1500, "login_success", country="RO"),
                          ev(3000, "password_reset"), ev(3500, "login_success", country="RO")]
    got = detect(events)
    assert [(a["start"], a["end"]) for a in got] == [(1000, 1500)]


# --- разом -------------------------------------------------------------------------------------

def test_mixed_log_gives_sorted_deduplicated_alerts():
    events = (spray(10, "6.6.6.6", t0=5000) + fails([0, 10, 20, 30, 40], "carol")
              + pushes([2000, 2100, 2200, 2300, 2400], "dave")
              + [ev(3000, "login_success", "erin", geo=KYIV), ev(3060, "login_success", "erin", geo=NYC)])
    got = detect(events)
    assert [(a["start"], a["rule"], a["key"]) for a in got] == [
        (0, "bruteforce", "carol"), (2000, "mfa_fatigue", "dave"),
        (3000, "impossible_travel", "erin"), (5000, "spraying", "6.6.6.6")]


def test_latest_reset_defines_baseline_for_other_country():
    events = history() + [ev(1000, "password_reset"), ev(1500, "login_success", country="RO"),
                          ev(3000, "password_reset"), ev(3500, "login_success", country="PL")]
    got = detect(events)
    assert [(a["start"], a["end"]) for a in got] == [(1000, 1500), (3000, 3500)]


def test_unsorted_input_for_travel_and_reset():
    events = [ev(4600, "login_success", geo=NYC), ev(1000, "login_success", geo=KYIV)]
    assert detect(events) == [alert("impossible_travel", "alice", 1000, 4600, 2, "high")]
    events = [ev(2000, "login_success", country="RO"), ev(1000, "password_reset"), ev(200, "login_success"),
              ev(100, "login_success")]
    assert rules(detect(events)) == ["new_country_after_reset"]
