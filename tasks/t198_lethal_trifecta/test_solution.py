import copy
import itertools

import pytest

from solution import CAPS, analyze, plan_split

P, U, E = CAPS

TOOLS = {
    "read_files": {"private_data": True},
    "web_fetch": {"untrusted_content": True},
    "send_email": {"exfiltration": True},
    "read_inbox": {"private_data": True, "untrusted_content": True},
    "calc": {},
    "post_webhook": {"exfiltration": True},
}


def cfg(sessions=None, tools=None):
    c = {"tools": copy.deepcopy(TOOLS if tools is None else tools)}
    if sessions is not None:
        c["sessions"] = sessions
    return c


# --- analyze: сесії та ризик -------------------------------------------------------------------

def test_default_session_contains_all_tools_and_is_critical():
    report = analyze(cfg())
    assert list(report["sessions"]) == ["default"]
    s = report["sessions"]["default"]
    assert s["count"] == 3 and s["risk"] == "critical"
    assert s["capabilities"] == {P: ["read_files", "read_inbox"], U: ["read_inbox", "web_fetch"],
                                 E: ["post_webhook", "send_email"]}
    assert report["safe"] is False


def test_risk_levels_by_number_of_capabilities():
    report = analyze(cfg({"none": ["calc"], "empty": [], "one": ["web_fetch"], "two": ["read_files", "web_fetch"],
                          "three": ["read_files", "web_fetch", "send_email"]}))
    assert {sid: (s["count"], s["risk"]) for sid, s in report["sessions"].items()} == {
        "none": (0, "low"), "empty": (0, "low"), "one": (1, "low"), "two": (2, "high"), "three": (3, "critical")}
    assert list(report["sessions"]) == ["none", "empty", "one", "two", "three"]
    assert report["sessions"]["empty"]["capabilities"] == {P: [], U: [], E: []}


def test_one_tool_can_provide_two_capabilities_for_the_same_session():
    report = analyze(cfg({"s": ["read_inbox", "send_email"]}))
    assert report["sessions"]["s"]["count"] == 3
    assert report["findings"] == [{"rule": "lethal-trifecta", "session": "s", "tools": ["read_inbox", "send_email"]}]


def test_safe_when_capabilities_are_split_across_sessions():
    report = analyze(cfg({"reader": ["read_files", "web_fetch"], "sender": ["send_email", "calc"], "fetcher": ["web_fetch"]}))
    assert report["safe"] is True and report["findings"] == [] and report["recommendations"] == []
    assert [s["risk"] for s in report["sessions"].values()] == ["high", "low", "low"]


def test_capability_lists_are_sorted_alphabetically_and_only_per_session_tools():
    report = analyze(cfg({"a": ["web_fetch", "read_inbox"], "b": ["send_email"]}))
    assert report["sessions"]["a"]["capabilities"][U] == ["read_inbox", "web_fetch"]
    assert report["sessions"]["b"]["capabilities"] == {P: [], U: [], E: ["send_email"]}


# --- analyze: findings і recommendations -------------------------------------------------------

def test_lethal_trifecta_finding_lists_only_contributing_tools_sorted():
    report = analyze(cfg({"x": ["send_email", "calc", "web_fetch", "read_files"], "y": ["calc"]}))
    assert report["findings"] == [{"rule": "lethal-trifecta", "session": "x",
                                   "tools": ["read_files", "send_email", "web_fetch"]}]


def test_recommendation_removes_the_rarest_capability_with_tie_break_by_caps_order():
    report = analyze(cfg({"s": ["read_files", "web_fetch", "send_email", "post_webhook"]}))
    assert report["recommendations"] == [{"session": "s", "remove_capability": P, "from_tools": ["read_files"]}]
    report = analyze(cfg({"s": ["read_files", "read_inbox", "web_fetch", "send_email", "post_webhook"]}))
    # private: 2, untrusted: 2, exfiltration: 2 -> перша за порядком CAPS
    assert report["recommendations"] == [{"session": "s", "remove_capability": P, "from_tools": ["read_files", "read_inbox"]}]
    report = analyze(cfg({"s": ["read_files", "read_inbox", "web_fetch", "send_email"]}))
    assert report["recommendations"] == [{"session": "s", "remove_capability": E, "from_tools": ["send_email"]}]


def test_recommendations_follow_session_order_and_skip_safe_sessions():
    report = analyze(cfg({"safe": ["calc"], "b": ["read_files", "web_fetch", "send_email"], "a": ["read_inbox", "send_email"]}))
    assert [r["session"] for r in report["recommendations"]] == ["b", "a"]
    assert [f["session"] for f in report["findings"]] == ["b", "a"]
    assert report["recommendations"] == [
        {"session": "b", "remove_capability": P, "from_tools": ["read_files"]},
        {"session": "a", "remove_capability": P, "from_tools": ["read_inbox"]}]


def test_tool_trifecta_finding_even_when_tool_is_in_no_session_and_comes_first():
    tools = {"a": {P: True}, "omni": {P: True, U: True, E: True}, "b": {E: True}, "omni2": {P: True, U: True, E: True}}
    report = analyze({"tools": tools, "sessions": {"s1": ["a", "b"]}})
    assert report["findings"] == [{"rule": "tool-trifecta", "tool": "omni"}, {"rule": "tool-trifecta", "tool": "omni2"}]
    assert report["safe"] is False and report["recommendations"] == []
    both = analyze({"tools": tools, "sessions": {"s1": ["omni"], "s2": ["a", "b", "omni2"]}})
    assert [f["rule"] for f in both["findings"]] == ["tool-trifecta", "tool-trifecta", "lethal-trifecta", "lethal-trifecta"]
    assert both["findings"][2] == {"rule": "lethal-trifecta", "session": "s1", "tools": ["omni"]}


def test_missing_flags_default_to_false_and_all_false_tool_is_ignored():
    report = analyze({"tools": {"t": {}, "u": {"exfiltration": False}}, "sessions": {"s": ["t", "u"]}})
    assert report["sessions"]["s"]["count"] == 0 and report["safe"] is True


def test_analyze_does_not_mutate_config():
    config = cfg({"a": ["read_files", "web_fetch", "send_email"]})
    snapshot = copy.deepcopy(config)
    analyze(config)
    plan_split(config)
    assert config == snapshot


def test_session_may_reuse_tools_from_other_sessions():
    report = analyze(cfg({"a": ["web_fetch", "send_email"], "b": ["web_fetch", "read_files", "send_email"]}))
    assert [s["count"] for s in report["sessions"].values()] == [2, 3]


# --- analyze: валідація (fail closed) ----------------------------------------------------------

@pytest.mark.parametrize("config", [
    None, [], "x", {}, {"tools": None}, {"tools": []}, {"tools": {"": {}}}, {"tools": {5: {}}}, {"tools": {"a": []}},
    {"tools": {"a": None}},
    {"tools": {"a": {"exfiltraton": True}}},                       # опечатка не має робити інструмент «безпечним»
    {"tools": {"a": {"exfiltration": "yes"}}}, {"tools": {"a": {"exfiltration": 1}}}, {"tools": {"a": {"private": True}}},
    {"tools": {"a": {}}, "sessions": {}}, {"tools": {"a": {}}, "sessions": []}, {"tools": {"a": {}}, "sessions": None},
    {"tools": {"a": {}}, "sessions": {"s": "a"}}, {"tools": {"a": {}}, "sessions": {"s": ["missing"]}},
    {"tools": {"a": {}}, "sessions": {"s": ["a", "a"]}}, {"tools": {"a": {}}, "sessions": {"s": None}},
])
def test_invalid_configs(config):
    with pytest.raises(ValueError):
        analyze(config)
    with pytest.raises(ValueError):
        plan_split(config)


def test_empty_tools_is_valid():
    report = analyze({"tools": {}})
    assert report["sessions"]["default"]["count"] == 0 and report["safe"] is True


# --- plan_split --------------------------------------------------------------------------------

def test_plan_split_example_needs_two_sessions():
    plan = plan_split(cfg())
    assert plan == {"possible": True, "unsplittable": [], "sessions": [
        {"lacks": P, "tools": ["web_fetch", "send_email", "calc", "post_webhook"]},
        {"lacks": E, "tools": ["read_files", "read_inbox"]},
    ]}


def test_plan_split_single_session_when_one_capability_is_absent():
    plan = plan_split(cfg(tools={"a": {P: True}, "b": {U: True}, "c": {}}))
    assert plan == {"possible": True, "unsplittable": [], "sessions": [{"lacks": E, "tools": ["a", "b", "c"]}]}
    plan = plan_split(cfg(tools={"a": {U: True}, "b": {E: True}}))
    assert plan["sessions"] == [{"lacks": P, "tools": ["a", "b"]}]


def test_plan_split_prefers_first_single_session_in_caps_order():
    plan = plan_split(cfg(tools={"a": {}, "b": {}}))
    assert plan["sessions"] == [{"lacks": P, "tools": ["a", "b"]}]
    plan = plan_split(cfg(tools={"a": {P: True}}))
    assert plan["sessions"] == [{"lacks": U, "tools": ["a"]}]


def test_plan_split_pair_that_cannot_host_everything_is_skipped_up_to_three_sessions():
    tools = {"pe": {P: True, E: True}, "u": {U: True}, "pu": {P: True, U: True}, "ue": {U: True, E: True}}
    plan = plan_split(cfg(tools=tools))
    # жодна пара (без P, без U), (без P, без E), (без U, без E) не вміщує всі 4 інструменти
    assert plan == {"possible": True, "unsplittable": [], "sessions": [
        {"lacks": P, "tools": ["u", "ue"]}, {"lacks": U, "tools": ["pe"]}, {"lacks": E, "tools": ["pu"]}]}


def test_plan_split_two_sessions_when_every_tool_has_at_most_two_caps_and_pair_fits():
    tools = {"pe": {P: True, E: True}, "u": {U: True}, "e": {E: True}, "p": {P: True}}
    plan = plan_split(cfg(tools=tools))
    # без U вміщує pe, e, p; без P вміщує u, e. Мінімум 2 сесії; перша пара за порядком, що підходить, це (P, U)
    assert plan == {"possible": True, "unsplittable": [], "sessions": [
        {"lacks": P, "tools": ["u", "e"]}, {"lacks": U, "tools": ["pe", "p"]}]}


def test_plan_split_three_sessions_case_and_every_group_has_no_trifecta():
    tools = {"pe": {P: True, E: True}, "pu": {P: True, U: True}, "ue": {U: True, E: True}}
    plan = plan_split(cfg(tools=tools))
    assert plan == {"possible": True, "unsplittable": [], "sessions": [
        {"lacks": P, "tools": ["ue"]}, {"lacks": U, "tools": ["pe"]}, {"lacks": E, "tools": ["pu"]}]}
    for group in plan["sessions"]:
        for t in group["tools"]:
            assert not tools[t].get(group["lacks"], False)


def test_plan_split_unsplittable_tools():
    tools = {"a": {P: True}, "omni": {P: True, U: True, E: True}, "b": {E: True}, "omni2": {P: True, U: True, E: True}}
    assert plan_split(cfg(tools=tools)) == {"possible": False, "sessions": [], "unsplittable": ["omni", "omni2"]}


def test_plan_split_empty_tools():
    assert plan_split({"tools": {}}) == {"possible": True, "sessions": [], "unsplittable": []}


def test_plan_split_ignores_sessions_and_all_tools_are_assigned_exactly_once():
    plan = plan_split(cfg({"s": ["calc"]}))
    assigned = [t for g in plan["sessions"] for t in g["tools"]]
    assert sorted(assigned) == sorted(TOOLS) and len(assigned) == len(set(assigned))


def test_plan_split_random_toolsets_are_minimal_and_safe():
    # повний перебір: мінімальна кількість сесій, що лишає кожну без хоча б однієї можливості
    import random
    rng = random.Random(7)
    for _ in range(60):
        n = rng.randint(1, 6)
        tools = {f"t{i}": {c: rng.random() < 0.4 for c in CAPS} for i in range(n)}
        tools = {k: (v if not all(v.values()) else {**v, E: False}) for k, v in tools.items()}
        plan = plan_split({"tools": tools})
        groups = plan["sessions"]
        for g in groups:
            assert all(not tools[t][g["lacks"]] for t in g["tools"])
        assert sorted(t for g in groups for t in g["tools"]) == sorted(tools)
        best = min(size for size in (1, 2, 3) for combo in itertools.combinations(CAPS, size)
                   if all(any(not tools[t][c] for c in combo) for t in tools))
        assert len(groups) == best
