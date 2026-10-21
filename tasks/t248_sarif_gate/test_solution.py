import datetime
import hashlib

import pytest

from solution import evaluate_gate, merge_sarif

TODAY = datetime.date(2026, 10, 21)


def day(n):
    return (TODAY + datetime.timedelta(days=n)).isoformat()


def result(rule="R1", path="src/a.py", line=1, text=None, level=None, msg="problem", **extra):
    res = {
        "ruleId": rule,
        "message": {"text": msg},
        "locations": [{"physicalLocation": {"artifactLocation": {"uri": path}, "region": {"startLine": line}}}],
    }
    if text is not None:
        res["locations"][0]["physicalLocation"]["region"]["snippet"] = {"text": text}
    if level is not None:
        res["level"] = level
    res.update(extra)
    return res


def sarif(results, tool="scanner", rules=None, version="2.1.0"):
    driver = {"name": tool}
    if rules is not None:
        driver["rules"] = rules
    return {"version": version, "runs": [{"tool": {"driver": driver}, "results": results}]}


def one(doc):
    findings = merge_sarif([doc])
    assert len(findings) == 1
    return findings[0]


def fp_of(tool, rule, path, text):
    return hashlib.sha256("\x1f".join([tool, rule, path, " ".join(text.split())]).encode()).hexdigest()[:16]


# --- merge_sarif: форма й severity -------------------------------------------------------------

def test_basic_shape():
    f = one(sarif([result("SQLI", "src/db.py", 42, text="cursor.execute(q)", level="error", msg="SQL injection")]))
    assert set(f) == {"fingerprint", "tool", "rule", "severity", "path", "line", "message"}
    assert (f["tool"], f["rule"], f["severity"], f["path"], f["line"], f["message"]) == (
        "scanner", "SQLI", "high", "src/db.py", 42, "SQL injection")


@pytest.mark.parametrize("level, expected", [
    ("error", "high"), ("warning", "medium"), ("note", "low"), ("none", "info"), (None, "medium"),
])
def test_severity_from_level(level, expected):
    assert one(sarif([result(level=level)]))["severity"] == expected


@pytest.mark.parametrize("score, expected", [
    (10.0, "critical"), (9.0, "critical"), (8.9, "high"), (7.0, "high"), (6.9, "medium"), (4.0, "medium"),
    (3.9, "low"), (0.1, "low"), (0, "info"), ("9.5", "critical"), ("5.0", "medium"),
])
def test_severity_from_security_severity_beats_level(score, expected):
    doc = sarif([result("R1", level="note", properties={"security-severity": score})])
    assert one(doc)["severity"] == expected


def test_rule_level_security_severity_and_result_override():
    rules = [{"id": "R1", "properties": {"security-severity": "9.8"}}, {"id": "R2", "properties": {"security-severity": "2.0"}}]
    findings = merge_sarif([sarif([result("R1", "a.py", 1, level="note"), result("R2", "b.py", 1, level="error"),
                                   result("R2", "c.py", 1, properties={"security-severity": "7.5"})], rules=rules)])
    assert [f["severity"] for f in findings] == ["critical", "low", "high"]


def test_garbage_score_falls_back_to_level_and_rule_default_level():
    rules = [{"id": "R1", "defaultConfiguration": {"level": "error"}}]
    f1 = one(sarif([result("R1", properties={"security-severity": "n/a"})], rules=rules))
    assert f1["severity"] == "high"
    f2 = one(sarif([result("R1", level="note", properties={"security-severity": None})], rules=rules))
    assert f2["severity"] == "low"


def test_rule_from_rule_index_and_unknown_defaults():
    rules = [{"id": "A"}, {"id": "B"}]
    res = result()
    del res["ruleId"]
    res["ruleIndex"] = 1
    assert one(sarif([res], rules=rules))["rule"] == "B"
    res2 = result()
    del res2["ruleId"]
    assert one(sarif([res2]))["rule"] == "unknown"
    doc = {"version": "2.1.0", "runs": [{"tool": {"driver": {}}, "results": [result()]}]}
    assert one(doc)["tool"] == "unknown"


@pytest.mark.parametrize("uri, expected", [
    ("src/a.py", "src/a.py"), ("./src/a.py", "src/a.py"), ("/src/a.py", "src/a.py"), ("file:///src/a.py", "src/a.py"),
    ("src\\win\\a.py", "src/win/a.py"), ("src/my%20file.py", "src/my file.py"), ("././src/a.py", "src/a.py"),
])
def test_path_normalisation(uri, expected):
    assert one(sarif([result(path=uri)]))["path"] == expected


def test_result_without_location():
    f = one(sarif([{"ruleId": "R", "message": {"text": "global issue"}, "level": "error"}]))
    assert (f["path"], f["line"], f["message"]) == ("", 0, "global issue")


def test_suppressed_results_are_skipped():
    doc = sarif([result("R1", suppressions=[{"kind": "inSource"}]), result("R2", "b.py"), result("R3", "c.py", suppressions=[])])
    assert [f["rule"] for f in merge_sarif([doc])] == ["R2", "R3"]


@pytest.mark.parametrize("bad", [None, [], "x", {"version": "2.0.0", "runs": []}, {"version": "2.1.0"},
                                 {"version": "2.1.0", "runs": {}}])
def test_invalid_documents(bad):
    with pytest.raises(ValueError):
        merge_sarif([bad])
    with pytest.raises(ValueError):
        merge_sarif([sarif([]), bad])


def test_empty_inputs():
    assert merge_sarif([]) == []
    assert merge_sarif([sarif([])]) == []


# --- merge_sarif: відбитки ---------------------------------------------------------------------

def test_fingerprint_is_specified_hash_of_normalised_snippet():
    f = one(sarif([result("R", "src/a.py", 7, text="  x =   eval(y)\n")], tool="T"))
    assert f["fingerprint"] == fp_of("T", "R", "src/a.py", "x = eval(y)")


def test_fingerprint_falls_back_to_message():
    f = one(sarif([result("R", "a.py", 3, msg="Hardcoded   password")], tool="T"))
    assert f["fingerprint"] == fp_of("T", "R", "a.py", "Hardcoded password")


def test_fingerprint_stable_when_line_moves_or_path_is_spelled_differently():
    a = one(sarif([result("R", "src/a.py", 10, text="danger()")]))
    b = one(sarif([result("R", "./src/a.py", 250, text="danger()")]))
    assert a["fingerprint"] == b["fingerprint"]


def test_fingerprint_differs_by_each_component():
    base = one(sarif([result("R", "a.py", 1, text="x")], tool="T"))["fingerprint"]
    for doc in (sarif([result("R2", "a.py", 1, text="x")], tool="T"), sarif([result("R", "b.py", 1, text="x")], tool="T"),
                sarif([result("R", "a.py", 1, text="y")], tool="T"), sarif([result("R", "a.py", 1, text="x")], tool="U")):
        assert one(doc)["fingerprint"] != base


def test_duplicate_quadruples_get_occurrence_suffix_in_line_order():
    results = [result("R", "a.py", 30, text="eval(x)"), result("R", "a.py", 10, text="eval(x)"),
               result("R", "a.py", 20, text="eval(x)")]
    findings = merge_sarif([sarif(results, tool="T")])
    base = fp_of("T", "R", "a.py", "eval(x)")
    assert [(f["line"], f["fingerprint"]) for f in findings] == [(10, base), (20, base + "#2"), (30, base + "#3")]


def test_duplicate_suffix_is_stable_when_input_order_changes():
    r = [result("R", "a.py", n, text="eval(x)") for n in (5, 9)]
    a = merge_sarif([sarif(r)])
    b = merge_sarif([sarif(list(reversed(r)))])
    assert a == b


def test_same_tool_same_result_in_two_documents_is_merged():
    r = result("R", "a.py", 4, text="x")
    assert len(merge_sarif([sarif([r], tool="T"), sarif([r], tool="T")])) == 1


def test_different_tools_are_not_merged_and_output_is_sorted():
    findings = merge_sarif([
        sarif([result("R", "b.py", 1, text="x"), result("R", "a.py", 9, text="x")], tool="T1"),
        sarif([result("R", "a.py", 9, text="x"), result("Q", "a.py", 2, text="y")], tool="T2"),
    ])
    assert [(f["path"], f["line"], f["rule"], f["tool"]) for f in findings] == [
        ("a.py", 2, "Q", "T2"), ("a.py", 9, "R", "T1"), ("a.py", 9, "R", "T2"), ("b.py", 1, "R", "T1")]


def test_multiple_runs_in_one_document():
    doc = {"version": "2.1.0", "runs": [sarif([result("A", "a.py")], tool="T1")["runs"][0],
                                        sarif([result("B", "b.py")], tool="T2")["runs"][0]]}
    assert [(f["tool"], f["rule"]) for f in merge_sarif([doc])] == [("T1", "A"), ("T2", "B")]


# --- evaluate_gate -----------------------------------------------------------------------------

def finding(fp, severity="high", path="a.py", line=1, rule="R"):
    return {"fingerprint": fp, "tool": "t", "rule": rule, "severity": severity, "path": path, "line": line, "message": ""}


_DEFAULT = object()


def waiver(fp, owner="alice", reason="false positive", expires=_DEFAULT):
    return {"fingerprint": fp, "owner": owner, "reason": reason, "expires": day(30) if expires is _DEFAULT else expires}


def gate(findings, baseline=(), waivers=(), policy=None):
    return evaluate_gate(findings, set(baseline), list(waivers), policy or {}, TODAY)


def test_clean_run_passes():
    r = gate([])
    assert r["passed"] is True and r["blocking"] == [] and r["explanation"].startswith("PASS")
    assert r == {**r, "waived": [], "baselined": [], "ignored": 0, "problems": [], "unused_waivers": []}


@pytest.mark.parametrize("policy, severity, blocks", [
    ({}, "critical", True), ({}, "high", True), ({}, "medium", False), ({}, "low", False), ({}, "info", False),
    ({"block_on": "medium"}, "medium", True), ({"block_on": "medium"}, "low", False),
    ({"block_on": "critical"}, "high", False), ({"block_on": "critical"}, "critical", True),
    ({"block_on": "info"}, "info", True),
])
def test_threshold(policy, severity, blocks):
    r = gate([finding("f1", severity)], policy=policy)
    assert r["passed"] is (not blocks)
    assert bool(r["blocking"]) is blocks
    assert r["ignored"] == (0 if blocks else 1)


def test_unknown_threshold_name_is_value_error():
    with pytest.raises(ValueError):
        gate([], policy={"block_on": "severe"})


def test_baseline_does_not_block_but_new_finding_does():
    r = gate([finding("old"), finding("new", line=5)], baseline={"old"})
    assert r["baselined"] == ["old"]
    assert [b["fingerprint"] for b in r["blocking"]] == ["new"]
    assert r["blocking"][0]["reason"] == "new finding"
    assert r["passed"] is False


def test_baseline_only_counts_for_findings_above_threshold():
    r = gate([finding("old", "low"), finding("old2")], baseline={"old", "old2"})
    assert r["baselined"] == ["old2"] and r["ignored"] == 1 and r["passed"] is True


def test_blocking_entry_fields_and_sorting():
    fs = [finding("c", "high", "z.py", 1, "R3"), finding("b", "critical", "m.py", 9, "R2"),
          finding("a", "high", "a.py", 20, "R1"), finding("d", "high", "a.py", 3, "R4")]
    blocking = gate(fs)["blocking"]
    assert [b["fingerprint"] for b in blocking] == ["b", "d", "a", "c"]
    assert set(blocking[0]) == {"fingerprint", "severity", "rule", "path", "line", "reason"}
    assert (blocking[0]["severity"], blocking[0]["rule"], blocking[0]["path"], blocking[0]["line"]) == ("critical", "R2", "m.py", 9)


def test_valid_waiver_waives_and_unused_is_reported():
    r = gate([finding("f1"), finding("f2")], waivers=[waiver("f1"), waiver("ghost")])
    assert r["waived"] == ["f1"] and [b["fingerprint"] for b in r["blocking"]] == ["f2"]
    assert r["unused_waivers"] == ["ghost"] and r["problems"] == []


def test_waiver_for_ignored_or_baselined_finding_is_not_unused():
    r = gate([finding("low", "low"), finding("old")], baseline={"old"}, waivers=[waiver("low"), waiver("old")])
    assert r["unused_waivers"] == [] and r["waived"] == [] and r["passed"] is True


def test_waiver_expiry_boundaries():
    assert gate([finding("f")], waivers=[waiver("f", expires=day(0))])["waived"] == ["f"]
    r = gate([finding("f")], waivers=[waiver("f", expires=day(-1))])
    assert r["passed"] is False and r["blocking"][0]["reason"] == "waiver expired"
    assert r["problems"] == [{"fingerprint": "f", "problem": "expired"}]


def test_waiver_max_horizon():
    assert gate([finding("f")], waivers=[waiver("f", expires=day(90))])["waived"] == ["f"]
    r = gate([finding("f")], waivers=[waiver("f", expires=day(91))])
    assert r["blocking"][0]["reason"] == "waiver too-long" and r["problems"][0]["problem"] == "too-long"
    assert gate([finding("f")], waivers=[waiver("f", expires=day(200))], policy={"max_waiver_days": 365})["waived"] == ["f"]
    assert gate([finding("f")], waivers=[waiver("f", expires=day(11))], policy={"max_waiver_days": 10})["passed"] is False


@pytest.mark.parametrize("w, problem", [
    (waiver("f", owner=""), "no-owner"), (waiver("f", owner="   "), "no-owner"), (waiver("f", owner=None), "no-owner"),
    (waiver("f", reason=""), "no-reason"), (waiver("f", reason="  \n"), "no-reason"),
    (waiver("f", expires="31/12/2026"), "bad-date"), (waiver("f", expires="2026-13-01"), "bad-date"),
    (waiver("f", expires=""), "bad-date"), (waiver("f", expires=None), "bad-date"),
])
def test_invalid_waivers_do_not_waive(w, problem):
    r = gate([finding("f")], waivers=[w])
    assert r["passed"] is False and r["waived"] == []
    assert r["blocking"][0]["reason"] == f"waiver {problem}"
    assert r["problems"] == [{"fingerprint": "f", "problem": problem}]


def test_problem_check_order_owner_before_reason_before_date():
    r = gate([finding("f")], waivers=[waiver("f", owner="", reason="", expires=day(-5))])
    assert r["problems"][0]["problem"] == "no-owner"
    r = gate([finding("f")], waivers=[waiver("f", reason="", expires="bad")])
    assert r["problems"][0]["problem"] == "no-reason"
    r = gate([finding("f")], waivers=[waiver("f", expires=day(-1))])
    assert r["problems"][0]["problem"] == "expired"


def test_latest_expiry_waiver_wins():
    ws = [waiver("f", expires=day(-3)), waiver("f", expires=day(20)), waiver("f", owner="", expires=day(10))]
    r = gate([finding("f")], waivers=ws)
    assert r["waived"] == ["f"] and r["problems"] == []


def test_problems_only_for_findings_that_reach_the_waiver_step():
    r = gate([finding("old"), finding("low", "low")], baseline={"old"},
             waivers=[waiver("old", owner=""), waiver("low", expires=day(-9))])
    assert r["problems"] == [] and r["passed"] is True


def test_explanation_texts():
    ok = gate([finding("a", "low")])
    assert ok["explanation"].startswith("PASS")
    bad = gate([finding("fp-one"), finding("fp-two", "critical", line=7)])
    assert bad["explanation"].startswith("FAIL") and "2" in bad["explanation"]
    assert "fp-one" in bad["explanation"] and "fp-two" in bad["explanation"]


def test_input_is_not_mutated():
    fs = [finding("a"), finding("b")]
    ws = [waiver("a")]
    base = {"b"}
    gate(fs, baseline=base, waivers=ws)
    assert fs == [finding("a"), finding("b")] and ws == [waiver("a")] and base == {"b"}


# --- наскрізний сценарій -----------------------------------------------------------------------

def test_end_to_end_baseline_survives_line_shifts():
    v1 = merge_sarif([sarif([result("SQLI", "src/db.py", 10, text="execute(q)", level="error"),
                             result("XSS", "src/web.py", 5, text="render(x)", level="error")], tool="sast")])
    baseline = {f["fingerprint"] for f in v1}
    v2 = merge_sarif([
        sarif([result("SQLI", "./src/db.py", 99, text="execute(q)", level="error"),
               result("XSS", "src/web.py", 6, text="render(x)", level="error")], tool="sast"),
        sarif([result("SECRET", "config.py", 1, text="KEY='abc'", properties={"security-severity": "9.1"})], tool="secrets"),
    ])
    r = evaluate_gate(v2, baseline, [], {}, TODAY)
    assert r["passed"] is False
    assert [b["rule"] for b in r["blocking"]] == ["SECRET"]
    assert len(r["baselined"]) == 2
    waived = evaluate_gate(v2, baseline, [waiver(r["blocking"][0]["fingerprint"])], {}, TODAY)
    assert waived["passed"] is True
