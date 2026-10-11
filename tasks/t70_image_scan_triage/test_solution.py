import datetime

import pytest

from solution import parse_findings, triage

TODAY = datetime.date(2026, 6, 15)


def vuln(vid, pkg="openssl", installed="3.0.1", fixed="3.0.9", sev="HIGH"):
    v = {"VulnerabilityID": vid, "PkgName": pkg, "InstalledVersion": installed, "Severity": sev}
    if fixed is not None:
        v["FixedVersion"] = fixed
    return v


def report(*vulns, target="app (debian 12)"):
    return {"Results": [{"Target": target, "Vulnerabilities": list(vulns)}]}


def ids(findings):
    return [f["id"] for f in findings]


# ---------- parse_findings ----------

def test_parse_fields():
    f = parse_findings(report(vuln("CVE-1", sev="high")))[0]
    assert f == {
        "id": "CVE-1",
        "pkg": "openssl",
        "installed": "3.0.1",
        "fixed": "3.0.9",
        "severity": "HIGH",
        "target": "app (debian 12)",
    }


def test_parse_missing_or_empty_fixed_is_none():
    got = parse_findings(report(vuln("CVE-1", fixed=None), vuln("CVE-2", fixed="")))
    assert [f["fixed"] for f in got] == [None, None]


def test_parse_unknown_severity():
    got = parse_findings(report(
        {"VulnerabilityID": "CVE-1", "PkgName": "a", "InstalledVersion": "1"},
        vuln("CVE-2", sev="weird"),
        vuln("CVE-3", sev=None),
    ))
    assert [f["severity"] for f in got] == ["UNKNOWN"] * 3


def test_parse_empty_inputs():
    assert parse_findings({}) == []
    assert parse_findings({"Results": None}) == []
    assert parse_findings({"Results": [{"Target": "t"}]}) == []
    assert parse_findings({"Results": [{"Target": "t", "Vulnerabilities": None}]}) == []


def test_parse_multiple_results():
    rep = {"Results": [
        {"Target": "os", "Vulnerabilities": [vuln("CVE-1")]},
        {"Target": "python", "Vulnerabilities": [vuln("CVE-2", pkg="django")]},
        {"Target": "empty"},
    ]}
    got = parse_findings(rep)
    assert {(f["id"], f["target"]) for f in got} == {("CVE-1", "os"), ("CVE-2", "python")}


def test_parse_dedup_same_id_pkg_version_target():
    got = parse_findings(report(vuln("CVE-1"), vuln("CVE-1")))
    assert len(got) == 1


def test_parse_dedup_keeps_different_pkg_version_or_target():
    rep = {"Results": [
        {"Target": "a", "Vulnerabilities": [vuln("CVE-1"), vuln("CVE-1", pkg="libssl"), vuln("CVE-1", installed="3.0.2")]},
        {"Target": "b", "Vulnerabilities": [vuln("CVE-1")]},
    ]}
    assert len(parse_findings(rep)) == 4


def test_parse_order_severity_then_id_then_pkg():
    got = parse_findings(report(
        vuln("CVE-9", sev="LOW"),
        vuln("CVE-5", sev="CRITICAL", pkg="b"),
        vuln("CVE-5", sev="CRITICAL", pkg="a"),
        vuln("CVE-2", sev="CRITICAL"),
        vuln("CVE-7", sev="MEDIUM"),
        vuln("CVE-1", sev="UNKNOWN"),
        vuln("CVE-3", sev="HIGH"),
    ))
    assert [(f["id"], f["pkg"]) for f in got] == [
        ("CVE-2", "openssl"), ("CVE-5", "a"), ("CVE-5", "b"), ("CVE-3", "openssl"),
        ("CVE-7", "openssl"), ("CVE-9", "openssl"), ("CVE-1", "openssl"),
    ]


def test_parse_does_not_mutate_input():
    rep = report(vuln("CVE-2"), vuln("CVE-1"))
    before = repr(rep)
    parse_findings(rep)
    assert repr(rep) == before


# ---------- triage: пороги ----------

def run(vulns, today=TODAY, **policy):
    return triage(report(*vulns), policy, today)


def test_default_policy_blocks_high_and_critical_fixable():
    res = run([
        vuln("CVE-C", sev="CRITICAL"), vuln("CVE-H", sev="HIGH"),
        vuln("CVE-M", sev="MEDIUM"), vuln("CVE-L", sev="LOW"), vuln("CVE-U", sev="UNKNOWN"),
    ])
    assert ids(res["blocking"]) == ["CVE-C", "CVE-H"]
    assert res["passed"] is False
    assert res["ignored"] == [] and res["expired_ignores"] == []


def test_passed_when_nothing_blocks():
    res = run([vuln("CVE-M", sev="MEDIUM")])
    assert res["blocking"] == [] and res["passed"] is True and res["fixes"] == {}


@pytest.mark.parametrize("level, expected", [
    ("CRITICAL", ["CVE-C"]),
    ("HIGH", ["CVE-C", "CVE-H"]),
    ("MEDIUM", ["CVE-C", "CVE-H", "CVE-M"]),
    ("LOW", ["CVE-C", "CVE-H", "CVE-M", "CVE-L"]),
    ("UNKNOWN", ["CVE-C", "CVE-H", "CVE-M", "CVE-L", "CVE-U"]),
    ("critical", ["CVE-C"]),
])
def test_fail_on_levels(level, expected):
    vulns = [vuln("CVE-C", sev="CRITICAL"), vuln("CVE-H", sev="HIGH"), vuln("CVE-M", sev="MEDIUM"),
             vuln("CVE-L", sev="LOW"), vuln("CVE-U", sev="UNKNOWN")]
    assert ids(run(vulns, fail_on=level)["blocking"]) == expected


def test_invalid_fail_on():
    with pytest.raises(ValueError):
        run([vuln("CVE-1")], fail_on="SEVERE")


def test_only_fixable_default_skips_unfixed():
    res = run([vuln("CVE-1", fixed=None), vuln("CVE-2", fixed="")])
    assert res["blocking"] == [] and res["passed"] is True


def test_only_fixable_false_blocks_unfixed():
    res = run([vuln("CVE-1", fixed=None), vuln("CVE-2")], only_fixable=False)
    assert ids(res["blocking"]) == ["CVE-1", "CVE-2"]
    assert res["fixes"] == {"openssl": "3.0.9"}


def test_blocking_findings_are_parse_dicts():
    res = run([vuln("CVE-1")])
    assert res["blocking"][0] == parse_findings(report(vuln("CVE-1")))[0]


# ---------- triage: ignore ----------

def test_ignore_active_moves_to_ignored():
    res = run([vuln("CVE-1"), vuln("CVE-2")],
              ignore=[{"id": "CVE-1", "until": "2026-12-31", "reason": "не досяжна"}])
    assert ids(res["blocking"]) == ["CVE-2"]
    assert len(res["ignored"]) == 1
    assert res["ignored"][0]["finding"]["id"] == "CVE-1"
    assert res["ignored"][0]["reason"] == "не досяжна"
    assert res["expired_ignores"] == []


def test_ignore_last_day_inclusive():
    res = run([vuln("CVE-1")], today=datetime.date(2026, 6, 15),
              ignore=[{"id": "CVE-1", "until": "2026-06-15", "reason": "r"}])
    assert res["blocking"] == [] and len(res["ignored"]) == 1


def test_ignore_expired_does_not_ignore():
    res = run([vuln("CVE-1")], today=datetime.date(2026, 6, 16),
              ignore=[{"id": "CVE-1", "until": "2026-06-15", "reason": "r"}])
    assert ids(res["blocking"]) == ["CVE-1"]
    assert res["ignored"] == []
    assert res["expired_ignores"] == ["CVE-1"]


def test_expired_ignores_sorted_unique():
    res = run([], today=datetime.date(2027, 1, 1), ignore=[
        {"id": "CVE-9", "until": "2026-01-01", "reason": "r"},
        {"id": "CVE-2", "until": "2026-01-01", "reason": "r"},
        {"id": "CVE-9", "until": "2026-03-01", "reason": "r", "pkg": "x"},
    ])
    assert res["expired_ignores"] == ["CVE-2", "CVE-9"]


def test_expired_listed_even_without_matching_finding():
    res = run([vuln("CVE-1")], today=datetime.date(2027, 1, 1),
              ignore=[{"id": "CVE-77", "until": "2026-01-01", "reason": "r"}])
    assert res["expired_ignores"] == ["CVE-77"]


def test_ignore_scoped_to_pkg():
    vulns = [vuln("CVE-1", pkg="zlib"), vuln("CVE-1", pkg="libz")]
    res = run(vulns, ignore=[{"id": "CVE-1", "until": "2026-12-31", "reason": "r", "pkg": "zlib"}])
    assert [f["pkg"] for f in res["blocking"]] == ["libz"]
    assert [i["finding"]["pkg"] for i in res["ignored"]] == ["zlib"]


def test_ignore_without_pkg_covers_all_packages():
    vulns = [vuln("CVE-1", pkg="zlib"), vuln("CVE-1", pkg="libz")]
    res = run(vulns, ignore=[{"id": "CVE-1", "until": "2026-12-31", "reason": "r"}])
    assert res["blocking"] == [] and len(res["ignored"]) == 2


def test_ignore_below_threshold_not_listed():
    res = run([vuln("CVE-1", sev="LOW")], ignore=[{"id": "CVE-1", "until": "2026-12-31", "reason": "r"}])
    assert res["ignored"] == [] and res["blocking"] == []


def test_ignore_unfixed_not_listed_when_only_fixable():
    res = run([vuln("CVE-1", fixed=None)], ignore=[{"id": "CVE-1", "until": "2026-12-31", "reason": "r"}])
    assert res["ignored"] == []


def test_ignored_not_in_fixes():
    res = run([vuln("CVE-1", fixed="9.9.9")], ignore=[{"id": "CVE-1", "until": "2026-12-31", "reason": "r"}])
    assert res["fixes"] == {}


@pytest.mark.parametrize("entry", [
    {"id": "CVE-1", "reason": "r"},
    {"id": "CVE-1", "until": "", "reason": "r"},
    {"id": "CVE-1", "until": "2026-13-45", "reason": "r"},
    {"id": "CVE-1", "until": "завтра", "reason": "r"},
    {"id": "CVE-1", "until": "2026-12-31"},
    {"id": "CVE-1", "until": "2026-12-31", "reason": "   "},
])
def test_invalid_ignore_entries(entry):
    with pytest.raises(ValueError):
        run([vuln("CVE-1")], ignore=[entry])


def test_invalid_ignore_even_when_expired():
    with pytest.raises(ValueError):
        run([], today=datetime.date(2030, 1, 1), ignore=[{"id": "CVE-1", "until": "2020-01-01"}])


# ---------- triage: fixes ----------

def test_fixes_single():
    assert run([vuln("CVE-1", installed="3.0.1", fixed="3.0.9")])["fixes"] == {"openssl": "3.0.9"}


def test_fixes_max_across_findings_of_a_package():
    res = run([vuln("CVE-1", fixed="3.0.9"), vuln("CVE-2", fixed="3.0.12"), vuln("CVE-3", fixed="3.0.10")])
    assert res["fixes"] == {"openssl": "3.0.12"}


def test_fixes_numeric_not_lexicographic():
    res = run([vuln("CVE-1", fixed="3.0.9"), vuln("CVE-2", fixed="3.0.10")])
    assert res["fixes"]["openssl"] == "3.0.10"


def test_fixes_per_package():
    res = run([vuln("CVE-1", pkg="a", installed="1.0", fixed="1.1"), vuln("CVE-2", pkg="b", installed="2.0", fixed="2.5")])
    assert res["fixes"] == {"a": "1.1", "b": "2.5"}


def test_fixes_multiple_branches_pick_lowest_not_below_installed():
    res = run([vuln("CVE-1", installed="1.3.0", fixed="1.2.9, 1.3.4, 2.0.1")])
    assert res["fixes"] == {"openssl": "1.3.4"}


def test_fixes_branches_without_spaces():
    assert run([vuln("CVE-1", installed="1.0.0", fixed="1.0.5,1.1.2")])["fixes"] == {"openssl": "1.0.5"}


def test_fixes_installed_equal_to_branch_is_acceptable():
    assert run([vuln("CVE-1", installed="1.3.4", fixed="1.3.4")])["fixes"] == {"openssl": "1.3.4"}


def test_fixes_no_usable_branch_skips_package():
    res = run([vuln("CVE-1", installed="5.0.0", fixed="1.2.3, 2.0.0")])
    assert res["fixes"] == {}
    assert ids(res["blocking"]) == ["CVE-1"]


def test_fixes_ignore_findings_without_fix_when_not_only_fixable():
    res = run([vuln("CVE-1", fixed=None), vuln("CVE-2", fixed="3.0.9")], only_fixable=False)
    assert res["fixes"] == {"openssl": "3.0.9"}


def test_fixes_covers_all_blocking_findings_of_lower_severity_threshold():
    res = run([vuln("CVE-1", sev="MEDIUM", fixed="3.0.20"), vuln("CVE-2", fixed="3.0.9")], fail_on="HIGH")
    assert res["fixes"] == {"openssl": "3.0.9"}


def test_fixes_with_suffix_versions():
    res = run([vuln("CVE-1", pkg="zlib", installed="1.2.11-r0", fixed="1.2.12-r3")])
    assert res["fixes"] == {"zlib": "1.2.12-r3"}


# ---------- загальне ----------

def test_result_keys():
    res = run([])
    assert set(res) == {"blocking", "ignored", "expired_ignores", "fixes", "passed"}


def test_triage_does_not_mutate_inputs():
    rep = report(vuln("CVE-1"), vuln("CVE-2", fixed="1.0"))
    pol = {"fail_on": "HIGH", "ignore": [{"id": "CVE-1", "until": "2026-12-31", "reason": "r"}]}
    b1, b2 = repr(rep), repr(pol)
    triage(rep, pol, TODAY)
    assert repr(rep) == b1 and repr(pol) == b2


def test_empty_report_and_policy():
    res = triage({}, {}, TODAY)
    assert res == {"blocking": [], "ignored": [], "expired_ignores": [], "fixes": {}, "passed": True}
