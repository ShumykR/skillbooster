from datetime import date

import pytest

from solution import classify, triage

TODAY = date(2026, 10, 21)


def finding(id="CVE-1", cvss=5.0, epss=0.01, kev=False, reachable=None, internet=False, crit="medium",
            first_seen="2026-10-01"):
    return {"id": id, "cvss": cvss, "epss": epss, "in_kev": kev, "reachable": reachable,
            "asset": {"internet_facing": internet, "criticality": crit}, "first_seen": first_seen}


# --- classify ------------------------------------------------------------------------------------

@pytest.mark.parametrize("kwargs, priority, sla, reasons", [
    (dict(cvss=9.8, epss=0.02), "P1", 14, ["cvss-critical"]),
    (dict(cvss=9.8, reachable=False, crit="low"), "P3", 90, ["cvss-critical", "asset-low", "unreachable-cap"]),
    (dict(cvss=7.5, kev=True, reachable=True), "P0", 3, ["kev"]),
    (dict(cvss=7.5, kev=True, reachable=None), "P0", 3, ["kev"]),
    (dict(cvss=2.0, kev=True, reachable=True, crit="low"), "P0", 3, ["kev"]),
    (dict(cvss=7.5, kev=True, reachable=False), "P1", 14, ["kev-unreachable"]),
    (dict(cvss=5.0, epss=0.6, internet=True), "P0", 3, ["epss-exposed"]),
    (dict(cvss=5.0, epss=0.5, internet=True, reachable=True), "P0", 3, ["epss-exposed"]),
    (dict(cvss=5.0, epss=0.6, internet=True, reachable=False), "P3", 90,
     ["cvss-medium", "epss-elevated", "unreachable-cap"]),
    (dict(cvss=5.0, epss=0.6, internet=False), "P2", 30, ["cvss-medium", "epss-elevated"]),
    (dict(cvss=8.0, epss=0.05, internet=True, crit="high"), "P1", 14, ["cvss-high", "internet-facing"]),
    (dict(cvss=9.5, epss=0.2, internet=True, crit="critical"), "P1", 14,
     ["cvss-critical", "epss-elevated", "internet-facing", "asset-critical"]),
    (dict(cvss=3.0, crit="low"), "P4", 180, ["cvss-low", "asset-low"]),
    (dict(cvss=0.0), "P4", 180, ["cvss-low"]),
    (dict(cvss=10.0), "P1", 14, ["cvss-critical"]),
    (dict(cvss=6.0, internet=True), "P3", 90, ["cvss-medium"]),
    (dict(cvss=7.0, internet=True), "P1", 14, ["cvss-high", "internet-facing"]),
    (dict(cvss=4.0, crit="critical"), "P2", 30, ["cvss-medium", "asset-critical"]),
    (dict(cvss=4.0, crit="high"), "P3", 90, ["cvss-medium"]),
    (dict(cvss=8.0, reachable=False), "P3", 90, ["cvss-high", "unreachable-cap"]),
    (dict(cvss=3.0, reachable=False), "P4", 180, ["cvss-low", "unreachable-cap"]),
])
def test_classify_table(kwargs, priority, sla, reasons):
    r = classify(finding(**kwargs))
    assert r == {"priority": priority, "sla_days": sla, "reasons": reasons}


@pytest.mark.parametrize("cvss, expected", [(0.0, "P4"), (3.9, "P4"), (4.0, "P3"), (6.9, "P3"), (7.0, "P2"),
                                            (8.9, "P2"), (9.0, "P1"), (10.0, "P1")])
def test_cvss_boundaries(cvss, expected):
    assert classify(finding(cvss=cvss))["priority"] == expected


@pytest.mark.parametrize("epss, expected", [(0.0, "P3"), (0.099, "P3"), (0.1, "P2"), (0.49, "P2"), (1.0, "P2")])
def test_epss_boundaries_without_exposure(epss, expected):
    assert classify(finding(cvss=5.0, epss=epss))["priority"] == expected


@pytest.mark.parametrize("epss, expected", [(0.49, "P2"), (0.5, "P0"), (0.99, "P0")])
def test_epss_exposed_boundary(epss, expected):
    assert classify(finding(cvss=5.0, epss=epss, internet=True))["priority"] == expected


def test_cvss_98_can_rank_below_cvss_75():
    """Ідея завдання: 9.8 без експлуатації, недосяжна й на тестовому активі це не те саме, що 7.5 у KEV."""
    a = classify(finding("A", cvss=9.8, epss=0.01, reachable=False, crit="low"))
    b = classify(finding("B", cvss=7.5, kev=True, reachable=True))
    assert a["priority"] > b["priority"]
    assert (a["priority"], b["priority"]) == ("P3", "P0")


def test_classify_does_not_mutate_input():
    f = finding(cvss=9.8, reachable=False)
    snapshot = repr(f)
    classify(f)
    assert repr(f) == snapshot


@pytest.mark.parametrize("patch", [
    {"cvss": -0.1}, {"cvss": 10.1}, {"cvss": "9.8"}, {"cvss": None}, {"cvss": True},
    {"epss": -0.01}, {"epss": 1.01}, {"epss": "0.5"}, {"epss": True},
    {"in_kev": 1}, {"in_kev": "yes"}, {"in_kev": None},
    {"reachable": "yes"}, {"reachable": 0},
    {"asset": None}, {"asset": {"internet_facing": True}}, {"asset": {"criticality": "high"}},
    {"asset": {"internet_facing": 1, "criticality": "high"}},
    {"asset": {"internet_facing": True, "criticality": "extreme"}},
])
def test_classify_validation(patch):
    f = finding()
    f.update(patch)
    with pytest.raises(ValueError):
        classify(f)


# --- triage: терміни і статуси -------------------------------------------------------------------

def row(results, id):
    return next(r for r in results if r["id"] == id)


def test_due_date_and_status_boundaries():
    # P1 (14 днів): first_seen визначає, скільки днів лишилось до due
    def status_for(first_seen):
        r = triage([finding(cvss=9.8, first_seen=first_seen)], [], TODAY)[0]
        return r["due"], r["status"], r["escalate_to"]

    assert status_for("2026-10-21") == ("2026-11-04", "ok", None)       # 14 днів
    assert status_for("2026-10-11") == ("2026-10-25", "ok", None)       # 4 дні
    assert status_for("2026-10-10") == ("2026-10-24", "due-soon", None)  # 3 дні
    assert status_for("2026-10-07") == ("2026-10-21", "due-soon", None)  # сьогодні: ще не прострочено
    assert status_for("2026-10-06") == ("2026-10-20", "overdue", "team-lead")  # на 1 день


@pytest.mark.parametrize("late_days, expected", [(1, "team-lead"), (7, "team-lead"), (8, "security-lead"),
                                                 (30, "security-lead"), (31, "ciso"), (200, "ciso")])
def test_escalation_ladder(late_days, expected):
    from datetime import timedelta
    first_seen = (TODAY - timedelta(days=14 + late_days)).isoformat()
    r = triage([finding(cvss=9.8, first_seen=first_seen)], [], TODAY)[0]
    assert (r["status"], r["escalate_to"]) == ("overdue", expected)


def test_p0_overdue_escalates_at_least_to_security_lead():
    r = triage([finding(kev=True, reachable=True, first_seen="2026-10-16")], [], TODAY)[0]
    assert r["priority"] == "P0" and r["due"] == "2026-10-19"
    assert (r["status"], r["escalate_to"]) == ("overdue", "security-lead")
    r = triage([finding(kev=True, reachable=True, first_seen="2026-06-01")], [], TODAY)[0]
    assert r["escalate_to"] == "ciso"


def test_not_overdue_has_no_escalation():
    for fs in ("2026-10-21", "2026-10-18"):
        assert triage([finding(cvss=9.8, first_seen=fs)], [], TODAY)[0]["escalate_to"] is None


def test_result_shape_and_order():
    fs = [
        finding("C", cvss=3.0, first_seen="2026-10-01"),
        finding("B", cvss=9.8, first_seen="2026-10-05"),
        finding("A", cvss=9.8, first_seen="2026-10-05"),
        finding("D", kev=True, reachable=True, first_seen="2026-10-20"),
        finding("E", cvss=9.8, first_seen="2026-10-01"),
    ]
    res = triage(fs, [], TODAY)
    assert [r["id"] for r in res] == ["D", "E", "A", "B", "C"]
    assert set(res[0]) == {"id", "priority", "sla_days", "reasons", "due", "status", "escalate_to"}
    assert res[0]["reasons"] == ["kev"] and res[0]["sla_days"] == 3


def test_triage_does_not_mutate_inputs():
    fs = [finding("A", cvss=9.8)]
    ex = [{"id": "A", "owner": "o", "reason": "r", "expires": "2026-11-01"}]
    before = (repr(fs), repr(ex))
    triage(fs, ex, TODAY)
    assert (repr(fs), repr(ex)) == before


def test_triage_validation_errors():
    with pytest.raises(ValueError):
        triage([finding("A"), finding("A")], [], TODAY)
    with pytest.raises(ValueError):
        triage([finding("A", first_seen="21.10.2026")], [], TODAY)
    with pytest.raises(ValueError):
        triage([finding("A", cvss=11)], [], TODAY)
    with pytest.raises(ValueError):
        triage([finding("A")], [{"id": "ZZZ", "owner": "o", "reason": "r", "expires": "2026-11-01"}], TODAY)
    dup = {"id": "A", "owner": "o", "reason": "r", "expires": "2026-11-01"}
    with pytest.raises(ValueError):
        triage([finding("A")], [dup, dict(dup)], TODAY)


# --- triage: винятки -----------------------------------------------------------------------------

def exc(id="A", owner="alice", reason="vendor patch in Q4", expires="2026-11-20"):
    return {"id": id, "owner": owner, "reason": reason, "expires": expires}


OVERDUE = dict(cvss=9.8, first_seen="2026-08-01")  # P1, давно прострочена


def test_valid_exception_marks_excepted_and_stops_escalation():
    r = triage([finding("A", **OVERDUE)], [exc()], TODAY)[0]
    assert r["status"] == "excepted" and r["escalate_to"] is None
    assert not any(x.startswith("exception-invalid") for x in r["reasons"])
    assert r["due"] == "2026-08-15"  # due не змінюється


def test_exception_lasts_through_its_last_day_and_90_day_horizon():
    assert triage([finding("A", **OVERDUE)], [exc(expires="2026-10-21")], TODAY)[0]["status"] == "excepted"
    assert triage([finding("A", **OVERDUE)], [exc(expires="2027-01-19")], TODAY)[0]["status"] == "excepted"  # +90


@pytest.mark.parametrize("patch, why", [
    ({"owner": ""}, "no-owner"), ({"owner": "   "}, "no-owner"), ({"owner": None}, "no-owner"),
    ({"reason": ""}, "no-reason"), ({"reason": " \t"}, "no-reason"),
    ({"expires": "2026-10-20"}, "expired"), ({"expires": "2025-01-01"}, "expired"),
    ({"expires": "2027-01-20"}, "too-long"),
    ({"expires": "soon"}, "bad-date"), ({"expires": None}, "bad-date"), ({"expires": "2026-13-01"}, "bad-date"),
])
def test_invalid_exception_is_ignored_and_explained(patch, why):
    e = exc()
    e.update(patch)
    r = triage([finding("A", **OVERDUE)], [e], TODAY)[0]
    assert r["status"] == "overdue" and r["escalate_to"] == "ciso"
    assert r["reasons"][-1] == "exception-invalid:" + why
    assert r["reasons"][:-1] == ["cvss-critical"]


def test_invalid_exception_reason_priority_order():
    e = exc(owner="", reason="", expires="2020-01-01")
    r = triage([finding("A", **OVERDUE)], [e], TODAY)[0]
    assert r["reasons"][-1] == "exception-invalid:no-owner"
    e = exc(reason="", expires="2020-01-01")
    r = triage([finding("A", **OVERDUE)], [e], TODAY)[0]
    assert r["reasons"][-1] == "exception-invalid:no-reason"
    e = exc(expires="not-a-date")
    r = triage([finding("A", **OVERDUE)], [e], TODAY)[0]
    assert r["reasons"][-1] == "exception-invalid:bad-date"


def test_p0_cannot_be_excepted():
    f = finding("A", kev=True, reachable=True, first_seen="2026-10-10")
    r = triage([f], [exc()], TODAY)[0]
    assert r["status"] == "overdue" and r["escalate_to"] == "security-lead"
    assert r["reasons"] == ["kev", "exception-invalid:p0"]


def test_exception_applies_only_to_its_finding():
    res = triage([finding("A", **OVERDUE), finding("B", **OVERDUE)], [exc("A")], TODAY)
    assert row(res, "A")["status"] == "excepted"
    assert row(res, "B")["status"] == "overdue"
