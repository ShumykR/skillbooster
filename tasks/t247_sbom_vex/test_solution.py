import copy

import pytest

from solution import (JUSTIFICATIONS, apply_vex, diff_sbom, imported_modules, match_vulns,
                      normalize_name, parse_version, triage)


def C(name, version, ref=None, group=None):
    c = {"name": name, "version": version}
    if ref:
        c["bom-ref"] = ref
    if group:
        c["group"] = group
    return c


def sbom(*components, deps=None):
    d = {"components": list(components)}
    if deps is not None:
        d["dependencies"] = [{"ref": r, "dependsOn": list(t)} for r, t in deps.items()]
    return d


def osv(oid, name, events=None, versions=None, aliases=(), ecosystem="PyPI", withdrawn=None, extra_affected=()):
    aff = {"package": {"name": name, "ecosystem": ecosystem}}
    if events is not None:
        aff["ranges"] = [{"type": "ECOSYSTEM", "events": events}]
    if versions is not None:
        aff["versions"] = versions
    rec = {"id": oid, "aliases": list(aliases), "affected": [aff, *extra_affected]}
    if withdrawn:
        rec["withdrawn"] = withdrawn
    return rec


def rng(introduced="0", fixed=None, last=None):
    ev = [{"introduced": introduced}]
    if fixed:
        ev.append({"fixed": fixed})
    if last:
        ev.append({"last_affected": last})
    return ev


# --- helpers дано ------------------------------------------------------------------------------

def test_given_helpers():
    assert normalize_name("Py_YAML.x") == "py-yaml-x"
    assert parse_version("2.0.0") == parse_version("2") == (2,)
    assert parse_version("1.10") > parse_version("1.9")
    with pytest.raises(ValueError):
        parse_version("1.0rc1")
    assert "code_not_reachable" in JUSTIFICATIONS


# --- 1. diff_sbom ------------------------------------------------------------------------------

def test_diff_basic():
    old = sbom(C("requests", "2.30.0"), C("six", "1.16.0"), C("gone", "1.0"), C("flask", "2.0"))
    new = sbom(C("requests", "2.31.0"), C("six", "1.16.0"), C("new-lib", "0.1"), C("flask", "1.9"))
    d = diff_sbom(old, new)
    assert d == {
        "added": [{"name": "new-lib", "version": "0.1"}],
        "removed": [{"name": "gone", "version": "1.0"}],
        "updated": [
            {"name": "flask", "from": "2.0", "to": "1.9", "direction": "downgrade"},
            {"name": "requests", "from": "2.30.0", "to": "2.31.0", "direction": "upgrade"},
        ],
        "unchanged": 1,
    }


def test_diff_lists_are_sorted_by_key():
    old = sbom()
    new = sbom(C("zeta", "1"), C("Alpha", "1"), C("mid", "1"))
    assert [a["name"] for a in diff_sbom(old, new)["added"]] == ["Alpha", "mid", "zeta"]
    assert [a["name"] for a in diff_sbom(new, old)["removed"]] == ["Alpha", "mid", "zeta"]


def test_diff_matches_names_after_normalization():
    old = sbom(C("PyYAML", "5.4"), C("typing_extensions", "4.0"))
    new = sbom(C("pyyaml", "6.0"), C("typing-extensions", "4.0"))
    d = diff_sbom(old, new)
    assert d["added"] == [] and d["removed"] == []
    assert d["unchanged"] == 1
    assert d["updated"] == [{"name": "pyyaml", "from": "5.4", "to": "6.0", "direction": "upgrade"}]


def test_diff_group_is_part_of_the_key():
    old = sbom(C("util", "1.0", group="acme"))
    new = sbom(C("util", "1.0", group="evil"))
    d = diff_sbom(old, new)
    assert d["added"] == [{"name": "evil/util", "version": "1.0"}]
    assert d["removed"] == [{"name": "acme/util", "version": "1.0"}]
    assert d["unchanged"] == 0


@pytest.mark.parametrize("a, b, direction", [
    ("1.0rc1", "1.0", "changed"), ("2.0", "2.0.0", "changed"), ("1.9", "1.10", "upgrade"), ("1.10", "1.9", "downgrade"),
    ("1.0", "weird", "changed"),
])
def test_diff_direction(a, b, direction):
    d = diff_sbom(sbom(C("x", a)), sbom(C("x", b)))
    assert d["updated"][0]["direction"] == direction


def test_diff_same_component_twice_is_one_component():
    d = diff_sbom(sbom(C("x", "1"), C("x", "1")), sbom(C("x", "1")))
    assert d["unchanged"] == 1 and d["updated"] == []


def test_diff_invalid_sboms():
    with pytest.raises(ValueError):
        diff_sbom(sbom(C("x", "1"), C("x", "2")), sbom())
    with pytest.raises(ValueError):
        diff_sbom(sbom(), sbom(C("x", "1"), C("X", "2")))
    with pytest.raises(ValueError):
        diff_sbom(sbom({"version": "1"}), sbom())
    with pytest.raises(ValueError):
        diff_sbom(sbom(), sbom({"name": "x"}))


def test_diff_empty():
    assert diff_sbom({}, {}) == {"added": [], "removed": [], "updated": [], "unchanged": 0}


# --- 2. match_vulns ----------------------------------------------------------------------------

def finding_ids(sb, records):
    return [(f["id"], f["component"], f["version"], f["fixed"]) for f in match_vulns(sb, records)]


@pytest.mark.parametrize("version, hit", [("2.31.0", True), ("0.1", True), ("2.31.99", True), ("2.32.0", False),
                                          ("2.32", False), ("2.32.1", False)])
def test_range_fixed_is_exclusive(version, hit):
    res = finding_ids(sbom(C("requests", version)), [osv("V1", "requests", rng("0", "2.32.0"))])
    assert res == ([("V1", "requests", version, "2.32.0")] if hit else [])


@pytest.mark.parametrize("version, hit", [("1.4", False), ("1.5", True), ("1.9.9", True), ("2.0", False), ("10.0", False)])
def test_range_introduced_in_the_middle(version, hit):
    res = finding_ids(sbom(C("x", version)), [osv("V", "x", rng("1.5", "2.0"))])
    assert bool(res) is hit


def test_last_affected_is_inclusive_and_has_no_fix():
    recs = [osv("V", "x", rng("0", last="2.0"))]
    assert finding_ids(sbom(C("x", "2.0")), recs) == [("V", "x", "2.0", None)]
    assert finding_ids(sbom(C("x", "2.0.1")), recs) == []


def test_open_ended_range_is_infinite():
    recs = [osv("V", "x", rng("3.0"))]
    assert finding_ids(sbom(C("x", "99.0")), recs) == [("V", "x", "99.0", None)]
    assert finding_ids(sbom(C("x", "2.9")), recs) == []


def test_multiple_intervals_and_unsorted_events():
    events = [{"fixed": "2.5"}, {"introduced": "2.0"}, {"fixed": "1.0"}, {"introduced": "0"}]
    recs = [osv("V", "x", events)]
    assert finding_ids(sbom(C("x", "0.5")), recs) == [("V", "x", "0.5", "1.0")]
    assert finding_ids(sbom(C("x", "1.5")), recs) == []
    assert finding_ids(sbom(C("x", "2.1")), recs) == [("V", "x", "2.1", "2.5")]


def test_event_order_tie_closing_event_first_so_adjacent_intervals_stay_separate():
    events = [{"introduced": "1.0"}, {"fixed": "2.0"}, {"fixed": "1.0"}, {"introduced": "0"}]
    recs = [osv("V", "x", events)]
    assert finding_ids(sbom(C("x", "0.9")), recs) == [("V", "x", "0.9", "1.0")]
    assert finding_ids(sbom(C("x", "1.0")), recs) == [("V", "x", "1.0", "2.0")]
    assert finding_ids(sbom(C("x", "2.0")), recs) == []


def test_explicit_versions_list():
    recs = [osv("V", "x", versions=["3.0.0", "3.0.1"])]
    assert finding_ids(sbom(C("x", "3.0.1")), recs) == [("V", "x", "3.0.1", None)]
    assert finding_ids(sbom(C("x", "3.0.2")), recs) == []


def test_ecosystem_name_normalization_group_and_other_packages():
    recs = [
        osv("PYPI", "PyYAML", rng("0", "6.0")),
        osv("NPM", "pyyaml", rng("0", "6.0"), ecosystem="npm"),
        osv("OTHER", "requests", rng("0", "9.0")),
    ]
    sb = sbom(C("pyyaml", "5.4", group="acme"))
    assert finding_ids(sb, recs) == [("PYPI", "pyyaml", "5.4", "6.0")]


def test_non_ecosystem_range_types_are_ignored():
    rec = osv("V", "x", rng("0", "2.0"))
    rec["affected"][0]["ranges"][0]["type"] = "GIT"
    assert finding_ids(sbom(C("x", "1.0")), [rec]) == []


def test_withdrawn_records_are_skipped():
    assert finding_ids(sbom(C("x", "1.0")), [osv("V", "x", rng("0", "2.0"), withdrawn="2024-01-01T00:00:00Z")]) == []


def test_aliases_are_carried_and_trailing_zeros_equal():
    f = match_vulns(sbom(C("x", "1.0")), [osv("GHSA-1", "x", rng("0", "2"), aliases=["CVE-1", "CVE-2"])])[0]
    assert f["aliases"] == ["CVE-1", "CVE-2"]
    assert finding_ids(sbom(C("x", "2")), [osv("V", "x", rng("0", "2.0.0"))]) == []


def test_one_finding_per_record_and_max_fix_over_affected_entries():
    second = {"package": {"name": "X", "ecosystem": "PyPI"}, "ranges": [{"type": "ECOSYSTEM", "events": rng("0", "3.0")}]}
    rec = osv("V", "x", rng("0", "2.0"), extra_affected=[second])
    assert finding_ids(sbom(C("x", "1.0")), [rec]) == [("V", "x", "1.0", "3.0")]
    rec2 = osv("V2", "x", rng("0", "2.0"), versions=["1.0"])
    assert finding_ids(sbom(C("x", "1.0")), [rec2]) == [("V2", "x", "1.0", "2.0")]


def test_findings_sorted_by_component_then_id():
    sb = sbom(C("Zlib", "1.0"), C("alpha", "1.0"))
    recs = [osv("B", "zlib", rng("0", "2")), osv("Z", "alpha", rng("0", "2")), osv("A", "zlib", rng("0", "2"))]
    assert [(f["component"], f["id"]) for f in match_vulns(sb, recs)] == [("alpha", "Z"), ("Zlib", "A"), ("Zlib", "B")]


def test_match_does_not_mutate_inputs():
    sb, recs = sbom(C("x", "1.0")), [osv("V", "x", rng("0", "2.0"), aliases=["CVE-1"])]
    before = copy.deepcopy((sb, recs))
    f = match_vulns(sb, recs)
    f[0]["aliases"].append("zzz")
    assert (sb, recs) == before


# --- 3. apply_vex ------------------------------------------------------------------------------

def F(oid="V1", component="requests", version="2.31.0", aliases=("CVE-1",), fixed="2.32.0"):
    return {"id": oid, "aliases": list(aliases), "component": component, "version": version, "fixed": fixed}


def S(state, id="V1", component="requests", versions=None, justification=None):
    s = {"id": id, "component": component, "state": state}
    if versions is not None:
        s["versions"] = versions
    if justification:
        s["justification"] = justification
    return s


def test_not_affected_with_justification_suppresses():
    res = apply_vex([F()], [S("not_affected", justification="code_not_reachable")])
    assert res["active"] == []
    assert res["suppressed"] == [dict(F(), vex="not_affected")]


@pytest.mark.parametrize("just", [None, "", "because", "CODE_NOT_REACHABLE"])
def test_not_affected_without_valid_justification_stays_active(just):
    res = apply_vex([F()], [S("not_affected", justification=just)])
    assert res["suppressed"] == []
    assert res["active"] == [dict(F(), vex="invalid")]


def test_false_positive_needs_no_justification():
    res = apply_vex([F()], [S("false_positive")])
    assert res["suppressed"] == [dict(F(), vex="false_positive")] and res["active"] == []


def test_exploitable_beats_not_affected_and_triage_states():
    res = apply_vex([F()], [S("not_affected", justification="code_not_present"), S("exploitable"), S("in_triage")])
    assert res["suppressed"] == []
    assert res["active"][0]["vex"] == "exploitable"


def test_in_triage_and_resolved():
    assert apply_vex([F()], [S("in_triage")])["active"][0]["vex"] == "in_triage"
    assert apply_vex([F()], [S("resolved")])["active"][0]["vex"] is None
    assert apply_vex([F()], [])["active"][0]["vex"] is None
    assert apply_vex([F()], [S("in_triage"), S("not_affected")])["active"][0]["vex"] == "in_triage"


def test_matching_by_alias_version_and_component_normalization():
    ok = S("not_affected", id="CVE-1", component="Requests", versions=["2.31.0"], justification="requires_environment")
    assert apply_vex([F()], [ok])["suppressed"]
    wrong_version = S("not_affected", id="CVE-1", versions=["2.30.0"], justification="requires_environment")
    assert apply_vex([F()], [wrong_version])["suppressed"] == []
    empty_versions = S("not_affected", id="CVE-1", versions=[], justification="requires_environment")
    assert apply_vex([F()], [empty_versions])["suppressed"]
    other_component = S("not_affected", id="V1", component="urllib3", justification="requires_environment")
    assert apply_vex([F()], [other_component])["suppressed"] == []
    other_id = S("not_affected", id="V2", justification="requires_environment")
    assert apply_vex([F()], [other_id])["suppressed"] == []


def test_order_preserved_inputs_not_mutated():
    findings = [F("B"), F("A"), F("C")]
    vex = [S("not_affected", id="A", justification="code_not_present")]
    before = copy.deepcopy((findings, vex))
    res = apply_vex(findings, vex)
    assert [f["id"] for f in res["active"]] == ["B", "C"]
    assert [f["id"] for f in res["suppressed"]] == ["A"]
    assert (findings, vex) == before
    assert "vex" not in findings[0]


# --- 4. imported_modules -----------------------------------------------------------------------

def test_imported_modules_forms():
    src = {
        "a.py": "import os, requests.adapters as ra\nfrom yaml import safe_load\nfrom urllib3.util import retry\n",
        "b.py": "from . import sibling\nfrom .pkg import x\nfrom .. import up\n",
        "c.py": "def f():\n    import flask\n    try:\n        import ujson\n    except ImportError:\n        from json import loads\n",
        "d.py": "class K:\n    import jinja2\nx = 1\n",
    }
    assert imported_modules(src) == {"os", "requests", "yaml", "urllib3", "flask", "ujson", "json", "jinja2"}


def test_imported_modules_empty_and_never_executes():
    assert imported_modules({}) == set()
    assert imported_modules({"x.py": "raise SystemExit('executed')\nimport safe\n"}) == {"safe"}


def test_imported_modules_syntax_error():
    with pytest.raises(ValueError):
        imported_modules({"ok.py": "import a\n", "bad.py": "def (:\n"})


# --- 5. triage ---------------------------------------------------------------------------------

OLD = sbom(C("requests", "2.30.0", "r1"), C("PyYAML", "5.4.1", "r2"), C("flask", "2.0.0", "r3"),
           C("urllib3", "1.26.0", "r4"), C("jinja2", "3.0", "r5"), C("markupsafe", "2.0", "r6"), C("gone", "1.0", "r7"))
NEW = sbom(C("requests", "2.31.0", "r1"), C("PyYAML", "5.4.1", "r2"), C("flask", "3.0.0", "r3"),
           C("urllib3", "1.26.5", "r4"), C("jinja2", "3.1.2", "r5"), C("markupsafe", "2.1", "r6"),
           deps={"r1": ["r4"], "r3": ["r5"], "r5": ["r6"]})
SOURCES = {"app.py": "import requests\nimport yaml\n", "tests/test_x.py": "from . import helper\n"}
NAMES = {"PyYAML": ["yaml"]}
RECORDS = [
    osv("OSV-REQ-1", "requests", rng("0", "2.32.0"), aliases=["CVE-REQ-1"]),
    osv("OSV-REQ-2", "requests", rng("0", "2.31.1")),
    osv("OSV-YAML-1", "pyyaml", rng("0", "6.0"), aliases=["CVE-YAML-1"]),
    osv("OSV-YAML-2", "PyYAML", versions=["5.4.1"]),
    osv("OSV-URL-1", "urllib3", rng("0", "1.26.18")),
    osv("OSV-JINJA-1", "jinja2", rng("0", "3.1.5")),
    osv("OSV-JINJA-2", "jinja2", rng("0", "3.1.3")),
    osv("OSV-MS-1", "markupsafe", rng("0", "3.0")),
    osv("OSV-GONE-1", "gone", rng("0", "2.0")),
    osv("OSV-FLASK-WD", "flask", rng("0", "9.0"), withdrawn="2025-01-01T00:00:00Z"),
]
VEX = [{"id": "CVE-YAML-1", "component": "pyyaml", "state": "not_affected", "justification": "code_not_reachable"}]


def run_triage(**kw):
    args = dict(old_sbom=OLD, new_sbom=NEW, osv_records=RECORDS, vex=VEX, sources=SOURCES, import_names=NAMES)
    args.update(kw)
    return triage(**args)


def test_triage_full_scenario():
    res = run_triage()
    assert res["actions"] == [
        {"component": "requests", "version": "2.31.0", "action": "upgrade", "ids": ["OSV-REQ-1", "OSV-REQ-2"],
         "fixed_in": "2.32.0", "unfixed": [], "reachable": True, "new_in_release": True},
        {"component": "urllib3", "version": "1.26.5", "action": "upgrade", "ids": ["OSV-URL-1"],
         "fixed_in": "1.26.18", "unfixed": [], "reachable": True, "new_in_release": True},
        {"component": "PyYAML", "version": "5.4.1", "action": "review", "ids": ["OSV-YAML-2"],
         "fixed_in": None, "unfixed": ["OSV-YAML-2"], "reachable": True, "new_in_release": False},
        {"component": "jinja2", "version": "3.1.2", "action": "monitor", "ids": ["OSV-JINJA-1", "OSV-JINJA-2"],
         "fixed_in": "3.1.5", "unfixed": [], "reachable": False, "new_in_release": True},
        {"component": "markupsafe", "version": "2.1", "action": "monitor", "ids": ["OSV-MS-1"],
         "fixed_in": "3.0", "unfixed": [], "reachable": False, "new_in_release": True},
    ]
    assert res["suppressed"] == [{"id": "OSV-YAML-1", "component": "PyYAML", "version": "5.4.1", "vex": "not_affected"}]
    assert res["summary"] == {"upgrade": 2, "review": 1, "monitor": 2, "suppressed": 1}


def test_triage_counts_only_new_sbom():
    res = run_triage()
    assert all(a["component"] != "gone" for a in res["actions"])


def test_triage_new_in_release_for_new_component_and_empty_old():
    res = run_triage(old_sbom=sbom())
    assert all(a["new_in_release"] for a in res["actions"])
    res = run_triage(old_sbom=NEW)
    assert not any(a["new_in_release"] for a in res["actions"])


def test_triage_transitive_reachability_through_graph_and_cycles():
    new = sbom(C("app-lib", "1.0", "a"), C("mid", "1.0", "b"), C("deep", "1.0", "c"), C("lonely", "1.0", "d"),
               deps={"a": ["b", "ghost"], "b": ["c"], "c": ["a", "b"]})
    recs = [osv("V-DEEP", "deep", rng("0", "2")), osv("V-LONELY", "lonely", rng("0", "2"))]
    res = triage(sbom(), new, recs, [], {"m.py": "import app_lib\n"})
    by = {a["component"]: a for a in res["actions"]}
    assert by["deep"]["reachable"] is True and by["deep"]["action"] == "upgrade"
    assert by["lonely"]["reachable"] is False and by["lonely"]["action"] == "monitor"
    assert [a["component"] for a in res["actions"]] == ["deep", "lonely"]


def test_triage_default_module_name_and_nested_imports():
    new = sbom(C("my-lib", "1.0", "a"))
    recs = [osv("V", "my-lib", rng("0", "2"))]
    src = {"m.py": "def f():\n    import my_lib\n"}
    assert triage(sbom(), new, recs, [], src)["actions"][0]["reachable"] is True
    assert triage(sbom(), new, recs, [], {"m.py": "import my_lib_other\nfrom . import my_lib\n"})["actions"][0]["reachable"] is False
    assert triage(sbom(), new, recs, [], src, {"my_lib": ["other_name"]})["actions"][0]["reachable"] is False
    assert triage(sbom(), new, recs, [], {"m.py": "import other_name\n"}, {"My_Lib": ["other_name"]})["actions"][0]["reachable"] is True


def test_triage_exploitable_vex_keeps_the_action():
    vex = [{"id": "OSV-YAML-1", "component": "pyyaml", "state": "exploitable"},
           {"id": "OSV-YAML-1", "component": "pyyaml", "state": "not_affected", "justification": "code_not_reachable"}]
    res = run_triage(vex=vex)
    yaml_action = next(a for a in res["actions"] if a["component"] == "PyYAML")
    assert yaml_action["ids"] == ["OSV-YAML-1", "OSV-YAML-2"]
    assert yaml_action["fixed_in"] == "6.0" and yaml_action["unfixed"] == ["OSV-YAML-2"]
    assert yaml_action["action"] == "upgrade"
    assert res["suppressed"] == []


def test_triage_everything_suppressed_gives_no_actions():
    vex = [{"id": r["id"], "component": r["affected"][0]["package"]["name"], "state": "false_positive"} for r in RECORDS]
    res = run_triage(vex=vex)
    assert res["actions"] == []
    assert res["summary"] == {"upgrade": 0, "review": 0, "monitor": 0, "suppressed": 8}
    assert [s["id"] for s in res["suppressed"]][:2] == ["OSV-JINJA-1", "OSV-JINJA-2"]


def test_triage_syntax_error_in_sources_is_value_error():
    with pytest.raises(ValueError):
        run_triage(sources={"bad.py": "def (:\n"})


def test_triage_does_not_mutate_inputs():
    snapshot = copy.deepcopy((OLD, NEW, RECORDS, VEX, SOURCES, NAMES))
    run_triage()
    assert (OLD, NEW, RECORDS, VEX, SOURCES, NAMES) == snapshot
