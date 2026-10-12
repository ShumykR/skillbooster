import pytest

from solution import compare_runs, grade, run_eval


# ---------- grade ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("output, check, expected", [
    ("Paris", {"type": "exact", "value": "Paris"}, None),
    ("  Paris \n", {"type": "exact", "value": "Paris"}, None),
    ("paris", {"type": "exact", "value": "Paris"}, "exact"),
    ("paris", {"type": "exact", "value": "Paris", "ignore_case": True}, None),
    ("The capital is Paris.", {"type": "contains", "value": "Paris"}, None),
    ("The capital is paris.", {"type": "contains", "value": "Paris"}, "contains"),
    ("The capital is paris.", {"type": "contains", "value": "Paris", "ignore_case": True}, None),
    ("fine", {"type": "not_contains", "value": "secret"}, None),
    ("my SECRET key", {"type": "not_contains", "value": "secret"}, None),
    ("my SECRET key", {"type": "not_contains", "value": "secret", "ignore_case": True}, "not_contains"),
    ("order #123 shipped", {"type": "regex", "pattern": r"#\d+"}, None),
    ("order shipped", {"type": "regex", "pattern": r"#\d+"}, "regex"),
    ("ORDER", {"type": "regex", "pattern": "order", "ignore_case": True}, None),
    ("ORDER", {"type": "regex", "pattern": "order"}, "regex"),
    ("abc", {"type": "max_chars", "value": 3}, None),
    ("abcd", {"type": "max_chars", "value": 3}, "max_chars"),
])
def test_simple_checks(output, check, expected):
    assert grade(output, check) == expected


@pytest.mark.parametrize("output, path, value, expected", [
    ('{"a": {"b": 5}}', "a.b", 5, None),
    ('{"a": {"b": 5}}', "a.b", 6, "json"),
    ('{"items": [{"name": "x"}, {"name": "y"}]}', "items.1.name", "y", None),
    ('{"items": []}', "items.0", 1, "json"),
    ('{"a": 1}', "b", 1, "json"),
    ('{"a": 1}', "a.b", 1, "json"),
    ('```json\n{"ok": true}\n```', "ok", True, None),
    ('```\n{"ok": true}\n```', "ok", True, None),
    ("not json", "a", 1, "json"),
    ("[1, 2, 3]", "1", 2, None),
    ("[1, 2, 3]", "x", 2, "json"),
])
def test_json_checks(output, path, value, expected):
    assert grade(output, {"type": "json", "path": path, "value": value}) == expected


def test_unknown_check_type_is_a_configuration_error():
    with pytest.raises(ValueError):
        grade("x", {"type": "vibes"})


class Judge:
    def __init__(self, reply):
        self.reply, self.prompts = reply, []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def test_judge_prompt_and_scores():
    judge = Judge("Reasoning... SCORE: 5")
    assert grade("Because of gravity.", {"type": "judge", "criteria": "explains gravity"}, input="Why do things fall?", judge=judge) is None
    assert judge.prompts[0] == ("You are a strict grader. Rate the answer from 1 to 5 against the criteria.\nCriteria: explains gravity\n"
                                "Question: Why do things fall?\nAnswer: Because of gravity.\nReply with: SCORE: <number>")


@pytest.mark.parametrize("reply, min_score, expected", [
    ("SCORE: 4", 4, None), ("SCORE: 3", 4, "judge"), ("SCORE:5", 5, None), ("score: 5", 4, "judge_unparsable"),
    ("SCORE: 9", 4, "judge_unparsable"), ("no idea", 4, "judge_unparsable"), ("SCORE: 2 then SCORE: 5", 4, "judge"), ("SCORE: 3", 3, None)])
def test_judge_scores(reply, min_score, expected):
    assert grade("a", {"type": "judge", "criteria": "c", "min_score": min_score}, judge=Judge(reply)) == expected


def test_judge_default_threshold_and_errors():
    assert grade("a", {"type": "judge", "criteria": "c"}, judge=Judge("SCORE: 3")) == "judge"
    assert grade("a", {"type": "judge", "criteria": "c"}, judge=Judge("SCORE: 4")) is None
    assert grade("a", {"type": "judge", "criteria": "c"}, judge=Judge(TimeoutError())) == "judge_error"


# ---------- run_eval -------------------------------------------------------------------------------------------

CASES = [
    {"id": "capital", "input": "capital of France?", "checks": [{"type": "contains", "value": "Paris"}], "tag": "geo"},
    {"id": "polite", "input": "hello", "checks": [{"type": "not_contains", "value": "idiot"}, {"type": "max_chars", "value": 20}], "tag": "tone"},
    {"id": "json", "input": "give json", "checks": [{"type": "json", "path": "ok", "value": True}], "tag": "format"},
]


def good_model(prompt):
    return {"capital of France?": "Paris", "hello": "Hi there!", "give json": '{"ok": true}'}[prompt]


def test_all_passing():
    r = run_eval(good_model, CASES)
    assert (r["total"], r["passed"], r["pass_rate"]) == (3, 3, 1.0)
    assert [x["id"] for x in r["results"]] == ["capital", "polite", "json"]
    assert r["results"][0] == {"id": "capital", "passed": True, "pass_count": 1, "repeats": 1, "failures": [], "output": "Paris"}
    assert r["by_tag"] == {"geo": {"total": 1, "passed": 1}, "tone": {"total": 1, "passed": 1}, "format": {"total": 1, "passed": 1}}


def test_failures_are_listed_per_case():
    def model(prompt):
        return {"capital of France?": "Lyon", "hello": "You idiot, this reply is far too long", "give json": '{"ok": true}'}[prompt]

    r = run_eval(model, CASES)
    assert r["passed"] == 1 and r["pass_rate"] == 0.3333
    assert r["results"][0]["failures"] == ["contains"] and r["results"][1]["failures"] == ["max_chars", "not_contains"]
    assert r["by_tag"]["geo"] == {"total": 1, "passed": 0}


def test_sut_exceptions_fail_the_case_not_the_run():
    def model(prompt):
        if prompt == "hello":
            raise ConnectionError("down")
        return good_model(prompt)

    r = run_eval(model, CASES)
    assert r["results"][1] == {"id": "polite", "passed": False, "pass_count": 0, "repeats": 1, "failures": ["error"], "output": ""}
    assert r["passed"] == 2


def test_repeats_and_pass_threshold_for_flaky_models():
    answers = iter(["Paris", "Lyon", "Paris", "Paris"])
    case = [CASES[0]]
    r = run_eval(lambda p: next(answers), case, repeats=4, pass_threshold=0.75)
    assert r["results"][0]["pass_count"] == 3 and r["results"][0]["passed"] is True and r["results"][0]["failures"] == ["contains"]
    answers = iter(["Paris", "Lyon", "Paris", "Lyon"])
    assert run_eval(lambda p: next(answers), case, repeats=4, pass_threshold=0.75)["passed"] == 0
    answers = iter(["Paris", "Lyon"])
    assert run_eval(lambda p: next(answers), case, repeats=2)["results"][0]["passed"] is False, "порог за замовчуванням 1.0"


def test_output_is_from_the_last_repeat():
    outputs = iter(["Paris", "Lyon"])
    r = run_eval(lambda p: next(outputs), [CASES[0]], repeats=2, pass_threshold=0.5)
    assert r["results"][0]["output"] == "Lyon" and r["results"][0]["passed"] is True


def test_judge_cases_need_a_judge():
    cases = [{"id": "j", "input": "q", "checks": [{"type": "judge", "criteria": "helpful"}]}]
    with pytest.raises(ValueError):
        run_eval(lambda p: "a", cases)
    assert run_eval(lambda p: "a", cases, judge=Judge("SCORE: 5"))["passed"] == 1
    assert run_eval(lambda p: "a", cases, judge=Judge("SCORE: 1"))["results"][0]["failures"] == ["judge"]


@pytest.mark.parametrize("kwargs", [dict(repeats=0), dict(pass_threshold=0), dict(pass_threshold=1.5)])
def test_run_eval_validation(kwargs):
    with pytest.raises(ValueError):
        run_eval(good_model, CASES, **kwargs)
    with pytest.raises(ValueError):
        run_eval(good_model, CASES + [CASES[0]])


def test_empty_dataset_and_cases_without_tag():
    r = run_eval(good_model, [])
    assert r == {"total": 0, "passed": 0, "pass_rate": 0.0, "results": [], "by_tag": {}}
    untagged = [{"id": "x", "input": "hello", "checks": []}]
    assert run_eval(good_model, untagged)["by_tag"] == {} and run_eval(good_model, untagged)["passed"] == 1


# ---------- compare_runs -----------------------------------------------------------------------------------------


def make_run(**status):
    results = [{"id": k, "passed": v} for k, v in status.items()]
    passed = sum(status.values())
    return {"total": len(status), "passed": passed, "pass_rate": round(passed / len(status), 4), "results": results, "by_tag": {}}


def test_compare_finds_regressions_and_fixes():
    base = make_run(a=True, b=True, c=False, d=True)
    cur = make_run(a=True, b=False, c=True, d=True, e=True)
    diff = compare_runs(base, cur)
    assert diff == {"regressions": ["b"], "fixed": ["c"], "new_cases": ["e"], "removed_cases": [], "pass_rate_delta": 0.05, "ok": False}


def test_better_overall_but_with_a_regression_is_not_ok():
    base = make_run(a=True, b=False, c=False)
    cur = make_run(a=False, b=True, c=True)
    d = compare_runs(base, cur)
    assert d["pass_rate_delta"] > 0 and d["regressions"] == ["a"] and d["ok"] is False


def test_tolerance_applies_to_the_rate_but_not_to_regressions():
    base = make_run(a=True, b=True, c=True, d=True)
    cur = make_run(a=True, b=True, c=True, d=True, e=False)
    assert compare_runs(base, cur)["ok"] is False
    assert compare_runs(base, cur, tolerance=0.2)["ok"] is True
    assert compare_runs(base, cur, tolerance=0.19)["ok"] is False
    reg = make_run(a=True, b=True, c=True, d=False, e=True, f=True, g=True, h=True, i=True, j=True)
    assert compare_runs(make_run(**{k: True for k in "abcdefghij"}), reg, tolerance=0.5)["ok"] is False, "регресія d блокує навіть при високому допуску"


def test_removed_cases_and_identical_runs():
    base = make_run(a=True, b=True)
    cur = make_run(a=True)
    assert compare_runs(base, cur)["removed_cases"] == ["b"] and compare_runs(base, cur)["regressions"] == []
    same = compare_runs(base, base)
    assert same["ok"] is True and same["pass_rate_delta"] == 0.0 and same["regressions"] == same["fixed"] == []


def test_failures_are_merged_across_repeats_and_errors_blank_the_output():
    case = [{"id": "x", "input": "q", "checks": [{"type": "contains", "value": "Paris"}, {"type": "max_chars", "value": 5}]}]
    outputs = iter(["Lyon", "Paris is great", "Paris"])
    r = run_eval(lambda p: next(outputs), case, repeats=3, pass_threshold=0.3)
    assert r["results"][0]["failures"] == ["contains", "max_chars"] and r["results"][0]["pass_count"] == 1

    state = {"n": 0}

    def last_fails(p):
        state["n"] += 1
        if state["n"] == 2:
            raise ConnectionError
        return "Paris"

    assert run_eval(last_fails, [CASES[0]], repeats=2, pass_threshold=0.5)["results"][0]["output"] == ""
