import copy
import datetime

import pytest

from solution import check_dependencies, decide, edit_distance, normalize, parse_requirements, precommit

NOW = datetime.date(2026, 10, 21)


def days_ago(n):
    return (NOW - datetime.timedelta(days=n)).isoformat()


def pkg(age, releases=10):
    return {"first_release": days_ago(age), "releases": releases}


REGISTRY = {
    "requests": pkg(5000, 150),
    "numpy": pkg(6000, 200),
    "python-dateutil": pkg(4000, 40),
    "flask": pkg(5000, 80),
    "fastapi": pkg(2500, 120),
    "pydantic": pkg(3000, 150),
    "colorama": pkg(4500, 20),
    "pip": pkg(5000, 300),
    "reqeusts": pkg(12, 1),          # сквот на requests: щойно зареєстрований
    "fresh-lib": pkg(3, 5),
    "one-shot": pkg(900, 1),
    "age-30": pkg(30, 5),
    "age-29": pkg(29, 5),
    "future-lib": pkg(-2, 5),
    "healthy-lib": pkg(400, 12),
    "pyp": pkg(1000, 10),
}
POPULAR = {"requests", "numpy", "python-dateutil", "flask", "fastapi", "pydantic", "colorama", "pip"}


def check(names, **kw):
    kw.setdefault("registry", REGISTRY)
    kw.setdefault("popular", POPULAR)
    kw.setdefault("now", NOW)
    return check_dependencies(names, **kw)


def rules(findings, name=None):
    return [f["rule"] for f in findings if name is None or f["name"] == name]


# --- normalize / edit_distance -----------------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("Python_Dateutil", "python-dateutil"), ("zope.interface", "zope-interface"), ("A__B..C--D", "a-b-c-d"),
    ("requests", "requests"), ("FLASK", "flask"),
])
def test_normalize(raw, expected):
    assert normalize(raw) == expected


@pytest.mark.parametrize("a, b, d", [
    ("kitten", "sitting", 3), ("", "abc", 3), ("abc", "", 3), ("a", "a", 0), ("flaw", "lawn", 2),
    ("reqeusts", "requests", 1), ("ab", "ba", 1), ("ca", "abc", 3), ("numpy", "nunpy", 1), ("numpy", "numpyy", 1),
    ("flask", "flas", 1), ("abcd", "badc", 2),
])
def test_edit_distance(a, b, d):
    assert edit_distance(a, b) == d
    assert edit_distance(b, a) == d


# --- parse_requirements ------------------------------------------------------------------------

def test_parse_requirements_variants():
    text = """
    # production deps
    requests==2.32.0
    Flask>=3.0,<4  # web
    python_dateutil ~= 2.9
    uvicorn[standard]>=0.30 ; python_version >= "3.10"
    pydantic @ https://example.com/pydantic-2.0.whl
    numpy \\
        --hash=sha256:abc
    -r base.txt
    --index-url https://pypi.org/simple
    -e .
    git+https://github.com/org/repo.git#egg=repo
    https://example.com/pkg.whl
    REQUESTS
    zope.interface!=5.0

    """
    lines = [l.strip() for l in text.splitlines()]
    assert parse_requirements("\n".join(lines)) == [
        "requests", "flask", "python-dateutil", "uvicorn", "pydantic", "numpy", "zope-interface"]


def test_parse_requirements_empty_and_comments_only():
    assert parse_requirements("") == []
    assert parse_requirements("# only comment\n\n   \n-r other.txt\n") == []


# --- check_dependencies: окремі правила --------------------------------------------------------

def test_clean_dependencies_have_no_findings():
    assert check(["requests", "numpy", "python-dateutil", "healthy-lib", "Flask", "Python_Dateutil"]) == []


def test_hallucinated_package_is_not_in_registry_with_suggestions():
    f = check(["reqests"])
    assert rules(f) == ["not-in-registry", "lookalike"]
    nir = f[0]
    assert nir["name"] == "reqests"
    assert nir["suggestions"] == ["reqeusts", "requests"]
    assert f[1]["similar_to"] == "requests"


def test_completely_unknown_package_has_no_suggestions_and_no_lookalike():
    f = check(["acme-ai-super-toolkit"])
    assert f == [{"name": "acme-ai-super-toolkit", "rule": "not-in-registry", "suggestions": []}]


def test_suggestions_are_at_most_three_sorted_by_distance_then_name():
    reg = {n: pkg(1000) for n in ["abcde", "abcdf", "abcdg", "abcdh", "abcd", "xbcde"]}
    f = check_dependencies(["abcdx"], reg, set(), NOW)
    assert f == [{"name": "abcdx", "rule": "not-in-registry", "suggestions": ["abcd", "abcde", "abcdf"]}]


def test_typosquat_that_exists_in_registry_is_lookalike_new_and_low_history():
    f = check(["reqeusts"])
    assert rules(f) == ["lookalike", "too-new", "low-history"]
    assert f[0]["similar_to"] == "requests"
    assert f[1]["age_days"] == 12
    assert f[2]["releases"] == 1


@pytest.mark.parametrize("name", ["numpyy", "nunpy", "flaask", "pydantik", "colorame", "fastap"])
def test_one_edit_from_popular_is_lookalike(name):
    f = check_dependencies([name], {name: pkg(900, 9)}, POPULAR, NOW)
    assert rules(f) == ["lookalike"]


def test_separator_variants_are_lookalike_even_when_edit_distance_is_large():
    f = check_dependencies(["p-y-thon-dateutil"], {"p-y-thon-dateutil": pkg(900, 9)}, POPULAR, NOW)
    assert rules(f) == ["lookalike"]
    assert f[0]["similar_to"] == "python-dateutil"
    f = check_dependencies(["pythondateutil"], {"pythondateutil": pkg(900, 9)}, POPULAR, NOW)
    assert rules(f) == ["lookalike"]


def test_popular_packages_are_not_lookalikes_of_each_other():
    popular = {"flask", "flasks", "numpy"}
    reg = {n: pkg(900, 9) for n in popular}
    assert check_dependencies(["flasks", "flask"], reg, popular, NOW) == []


def test_short_popular_names_are_not_used_for_lookalike():
    f = check(["pyp"])
    assert f == []  # "pip" коротший за 5 символів, а "pyp" є в реєстрі зі старою історією


def test_max_distance_is_configurable():
    reg = {"numpxy": pkg(900, 9), "nuxpxy": pkg(900, 9)}
    assert rules(check_dependencies(["numpxy"], reg, POPULAR, NOW)) == ["lookalike"]
    assert check_dependencies(["nuxpxy"], reg, POPULAR, NOW) == []
    assert rules(check_dependencies(["nuxpxy"], reg, POPULAR, NOW, max_distance=2)) == ["lookalike"]
    assert check_dependencies(["numpxy"], reg, POPULAR, NOW, max_distance=0) == []


def test_lookalike_picks_the_closest_popular_name():
    popular = {"abcdefxx", "bcdefy"}
    reg = {"bcdefx": pkg(900, 9)}
    f = check_dependencies(["bcdefx"], reg, popular, NOW, max_distance=2)
    assert f == [{"name": "bcdefx", "rule": "lookalike", "similar_to": "bcdefy"}]


def test_too_new_boundary():
    assert rules(check(["age-30"])) == []
    f = check(["age-29"])
    assert f == [{"name": "age-29", "rule": "too-new", "age_days": 29}]
    assert rules(check(["fresh-lib"])) == ["too-new"]
    assert rules(check(["age-30"], min_age_days=31)) == ["too-new"]
    assert rules(check(["fresh-lib"], min_age_days=3)) == []


def test_release_date_in_the_future_is_too_new():
    f = check(["future-lib"])
    assert f == [{"name": "future-lib", "rule": "too-new", "age_days": -2}]


def test_low_history_boundary():
    f = check(["one-shot"])
    assert f == [{"name": "one-shot", "rule": "low-history", "releases": 1}]
    assert rules(check(["one-shot"], min_releases=1)) == []
    assert rules(check(["healthy-lib"], min_releases=13)) == ["low-history"]


# --- allowlist, internal, нормалізація, порядок ------------------------------------------------

def test_allowlist_and_internal_skip_every_rule():
    assert check(["reqests", "reqeusts", "fresh-lib"], allowlist={"reqests", "reqeusts", "fresh-lib"}) == []
    assert check(["acme-internal-sdk"], internal={"acme-internal-sdk"}) == []
    f = check(["acme-internal-sdk", "reqests"], internal={"acme-internal-sdk"})
    assert {x["name"] for x in f} == {"reqests"}


def test_names_are_normalized_before_every_lookup():
    assert check(["Python_Dateutil", "NUMPY"]) == []
    assert rules(check(["Fresh_Lib"])) == ["too-new"]
    assert check(["Fresh_Lib"])[0]["name"] == "fresh-lib"
    assert check(["REQEUSTS"], allowlist={"reqeusts"}) == []


def test_duplicates_are_reported_once():
    f = check(["fresh-lib", "Fresh_Lib", "fresh.lib"])
    assert rules(f) == ["too-new"]


def test_findings_sorted_by_name_then_rule_order():
    f = check(["reqeusts", "fresh-lib", "acme-unknown", "age-29"])
    assert [(x["name"], x["rule"]) for x in f] == [
        ("acme-unknown", "not-in-registry"), ("age-29", "too-new"), ("fresh-lib", "too-new"),
        ("reqeusts", "lookalike"), ("reqeusts", "too-new"), ("reqeusts", "low-history"),
    ]


def test_inputs_are_not_mutated_and_empty_input_is_clean():
    reg, pop = copy.deepcopy(REGISTRY), set(POPULAR)
    check(["reqeusts", "nope"], registry=reg, popular=pop)
    assert reg == REGISTRY and pop == POPULAR
    assert check([]) == []


# --- decide ------------------------------------------------------------------------------------

def test_decide_blocking_and_warnings():
    f = check(["reqests", "fresh-lib", "one-shot"])
    d = decide(f)
    assert d["exit_code"] == 1
    assert [x["rule"] for x in d["blocking"]] == ["not-in-registry", "lookalike"]
    assert [x["name"] for x in d["warnings"]] == ["fresh-lib", "one-shot"]


def test_decide_warnings_only_pass_unless_strict():
    f = check(["fresh-lib", "one-shot"])
    assert decide(f) == {"exit_code": 0, "blocking": [], "warnings": f}
    d = decide(f, strict=True)
    assert d["exit_code"] == 1 and d["blocking"] == [] and d["warnings"] == f


def test_decide_no_findings():
    assert decide([]) == {"exit_code": 0, "blocking": [], "warnings": []}
    assert decide([], strict=True)["exit_code"] == 0


# --- precommit ---------------------------------------------------------------------------------

def test_precommit_blocks_hallucinated_dependency():
    text = "requests==2.32\nreqests==1.0  # AI typo\nnumpy\n"
    code, lines = precommit(text, REGISTRY, POPULAR, NOW)
    assert code == 1
    assert lines == ["BLOCK reqests not-in-registry", "BLOCK reqests lookalike"]


def test_precommit_clean_file_passes_with_no_output():
    assert precommit("requests\nnumpy>=1.26\n# comment\n-r base.txt\n", REGISTRY, POPULAR, NOW) == (0, [])


def test_precommit_warnings_pass_but_are_reported():
    code, lines = precommit("fresh-lib\none-shot\n", REGISTRY, POPULAR, NOW)
    assert code == 0
    assert lines == ["WARN fresh-lib too-new", "WARN one-shot low-history"]
    code, lines = precommit("fresh-lib\n", REGISTRY, POPULAR, NOW, strict=True)
    assert code == 1 and lines == ["WARN fresh-lib too-new"]


def test_precommit_respects_internal_and_allowlist():
    text = "acme-internal-sdk\nreqeusts\n"
    code, lines = precommit(text, REGISTRY, POPULAR, NOW, internal={"acme-internal-sdk"}, allowlist={"reqeusts"})
    assert (code, lines) == (0, [])


def test_precommit_mixed_order_follows_findings():
    text = "one-shot\nreqeusts\nacme-unknown\n"
    code, lines = precommit(text, REGISTRY, POPULAR, NOW)
    assert code == 1
    assert lines == ["BLOCK acme-unknown not-in-registry", "WARN one-shot low-history", "BLOCK reqeusts lookalike",
                     "WARN reqeusts too-new", "WARN reqeusts low-history"]
