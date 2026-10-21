import copy
import hmac
import importlib

import pytest

import solution as sol


# звертаємось через `sol.`: один тест перезавантажує модуль, і «старі» імена вказували б на застарілі класи
def validate_card(card):
    return sol.validate_card(card)


def select_agent(cards, tags):
    return sol.select_agent(cards, tags)


def authenticate(card, headers, credentials):
    return sol.authenticate(card, headers, credentials)


def Task(*args):
    return sol.Task(*args)


def card(name="billing", version="1.0.0", skills=None, url="https://billing.example.com/a2a", schemes=("bearer",), **extra):
    c = {"name": name, "url": url, "version": version,
         "skills": skills if skills is not None else [{"id": "invoice", "tags": ["finance", "pdf"]}],
         "auth": {"schemes": list(schemes)}}
    c.update(extra)
    return c


# --- validate_card -----------------------------------------------------------------------------

def test_valid_cards():
    assert validate_card(card()) == []
    assert validate_card(card(url="http://localhost:8080/a2a")) == []
    assert validate_card(card(url="http://127.0.0.1/a2a", schemes=("bearer", "apikey"))) == []
    assert validate_card(card(skills=[{"id": "a"}, {"id": "b", "tags": []}, {"id": "c", "name": "C", "tags": ["x"]}])) == []
    assert validate_card(card(version="10.20.30")) == []


@pytest.mark.parametrize("bad", [None, [], "card", 5, ()])
def test_not_an_object(bad):
    assert validate_card(bad) == ["not-an-object"]


@pytest.mark.parametrize("name", [None, "", 5, ["a"]])
def test_missing_name(name):
    c = card()
    c["name"] = name
    assert validate_card(c) == ["missing:name"]
    del c["name"]
    assert validate_card(c) == ["missing:name"]


@pytest.mark.parametrize("url", [None, 5, "", "billing.example.com", "ftp://x.com/a", "http://example.com/a",
                                 "https://", "https:///path", "https://user:pass@example.com/a", "http://localhost.evil.com/a",
                                 "http://user@localhost/a", "javascript:alert(1)", "//example.com/a"])
def test_bad_url(url):
    c = card()
    c["url"] = url
    assert validate_card(c) == ["bad-url"]


@pytest.mark.parametrize("version", [None, 1, "1.0", "1.0.0.0", "v1.0.0", "1.0.x", "", "1.0.0-beta", " 1.0.0", "1.0.0\n"])
def test_bad_version(version):
    c = card()
    c["version"] = version
    assert validate_card(c) == ["bad-version"]


@pytest.mark.parametrize("skills", [None, [], "skills", {}, {"id": "a"}])
def test_no_skills(skills):
    c = card()
    c["skills"] = skills
    assert validate_card(c) == ["no-skills"]


def test_skill_problems_by_index_and_duplicate_ids_sorted():
    c = card(skills=["x", {"id": ""}, {"name": "no id"}, {"id": 5}, {"id": "ok", "tags": "finance"},
                     {"id": "ok2", "tags": ["a", ""]}, {"id": "ok3", "tags": [1]}, {"id": "dup"}, {"id": "b"}, {"id": "dup"},
                     {"id": "b"}, {"id": "dup"}])
    assert validate_card(c) == ["skill[0]:not-an-object", "skill[1]:missing-id", "skill[2]:missing-id", "skill[3]:missing-id",
                                "skill[4]:bad-tags", "skill[5]:bad-tags", "skill[6]:bad-tags",
                                "skill:duplicate-id:b", "skill:duplicate-id:dup"]


@pytest.mark.parametrize("auth", [None, {}, {"schemes": []}, {"schemes": None}, {"schemes": "bearer"}, "bearer", []])
def test_auth_missing(auth):
    c = card()
    c["auth"] = auth
    assert validate_card(c) == ["auth-missing"]
    del c["auth"]
    assert validate_card(c) == ["auth-missing"]


def test_unknown_auth_schemes_including_none():
    assert validate_card(card(schemes=("none",))) == ["auth-scheme:none"]
    assert validate_card(card(schemes=("bearer", "basic", "oauth"))) == ["auth-scheme:basic", "auth-scheme:oauth"]
    assert validate_card(card(schemes=("Bearer",))) == ["auth-scheme:Bearer"]


def test_problems_come_in_documented_order_and_validate_does_not_mutate():
    c = {"name": "", "url": "x", "version": "1", "skills": [], "auth": None}
    assert validate_card(c) == ["missing:name", "bad-url", "bad-version", "no-skills", "auth-missing"]
    good = card()
    snapshot = copy.deepcopy(good)
    validate_card(good)
    assert good == snapshot


# --- select_agent ------------------------------------------------------------------------------

def test_selects_agent_with_all_required_tags_in_one_skill():
    cards = [card("a", skills=[{"id": "s1", "tags": ["finance"]}, {"id": "s2", "tags": ["pdf"]}]),
             card("b", skills=[{"id": "inv", "tags": ["finance", "pdf", "eu"]}])]
    result = select_agent(cards, ["finance", "pdf"])
    assert result["agent"] == "b" and result["skill"] == "inv"
    assert result["ranking"] == [{"agent": "b", "skill": "inv", "version": "1.0.0", "matches": 1}]
    assert result["rejected"] == []


def test_no_match_returns_none_and_valid_cards_are_not_rejected():
    result = select_agent([card("a")], ["legal"])
    assert result == {"agent": None, "skill": None, "ranking": [], "rejected": []}
    assert select_agent([], ["x"]) == {"agent": None, "skill": None, "ranking": [], "rejected": []}


def test_tags_are_case_sensitive():
    assert select_agent([card("a", skills=[{"id": "s", "tags": ["Finance"]}])], ["finance"])["agent"] is None


def test_ranking_prefers_more_matching_skills_then_higher_numeric_version_then_name():
    cards = [
        card("zeta", "2.0.0", [{"id": "z", "tags": ["t"]}]),
        card("alpha", "2.0.0", [{"id": "a", "tags": ["t"]}]),
        card("many", "0.1.0", [{"id": "m1", "tags": ["t"]}, {"id": "skip", "tags": ["u"]}, {"id": "m2", "tags": ["t", "u"]}]),
        card("newer", "1.10.0", [{"id": "n", "tags": ["t"]}]),
        card("older", "1.9.0", [{"id": "o", "tags": ["t"]}]),
    ]
    result = select_agent(cards, ["t"])
    assert [r["agent"] for r in result["ranking"]] == ["many", "alpha", "zeta", "newer", "older"]
    assert result["agent"] == "many" and result["skill"] == "m1"          # перша підхожа навичка за порядком картки
    assert result["ranking"][0]["matches"] == 2
    assert [r["matches"] for r in result["ranking"][1:]] == [1, 1, 1, 1]


def test_version_compare_is_numeric_not_lexicographic():
    cards = [card("a", "1.9.0"), card("b", "1.10.0")]
    assert select_agent(cards, ["finance"])["agent"] == "b"
    cards = [card("a", "10.0.0"), card("b", "9.9.9")]
    assert select_agent(cards, ["finance"])["agent"] == "a"


def test_invalid_cards_are_rejected_with_problems_in_input_order_and_never_selected():
    bad_auth = card("evil", schemes=("none",))
    bad_url = card("web", url="http://example.com")
    cards = [bad_auth, card("good"), bad_url, {"url": "https://x.com"}, "garbage"]
    result = select_agent(cards, ["finance"])
    assert result["agent"] == "good"
    assert result["rejected"] == [
        {"agent": "evil", "problems": ["auth-scheme:none"]},
        {"agent": "web", "problems": ["bad-url"]},
        {"agent": None, "problems": ["missing:name", "bad-version", "no-skills", "auth-missing"]},
        {"agent": None, "problems": ["not-an-object"]},
    ]


def test_duplicate_names_reject_all_claimants_as_impersonation():
    cards = [card("billing", "1.0.0"), card("billing", "9.9.9", url="https://evil.example.com/a2a"), card("other")]
    result = select_agent(cards, ["finance"])
    assert result["agent"] == "other"
    assert result["rejected"] == [{"agent": "billing", "problems": ["duplicate-name"]},
                                  {"agent": "billing", "problems": ["duplicate-name"]}]


def test_duplicate_name_problem_comes_after_other_problems():
    cards = [card("x", url="http://bad"), card("x")]
    result = select_agent(cards, ["finance"])
    assert result["rejected"] == [{"agent": "x", "problems": ["bad-url", "duplicate-name"]},
                                  {"agent": "x", "problems": ["duplicate-name"]}]


@pytest.mark.parametrize("tags", [[], None, "finance", [""], [1], ["a", None], ("finance",)])
def test_select_agent_validates_tags(tags):
    with pytest.raises(ValueError):
        select_agent([card()], tags)


def test_select_agent_does_not_mutate_cards():
    cards = [card("b"), card("a")]
    snapshot = copy.deepcopy(cards)
    select_agent(cards, ["finance"])
    assert cards == snapshot


# --- authenticate ------------------------------------------------------------------------------

CREDS = {"bearer": ["tok-1", "tok-2"], "apikey": ["key-1"]}


def test_bearer_authentication():
    c = card(schemes=("bearer",))
    assert authenticate(c, {"Authorization": "Bearer tok-1"}, CREDS) is True
    assert authenticate(c, {"authorization": "bearer tok-2"}, CREDS) is True
    assert authenticate(c, {"AUTHORIZATION": "BEARER tok-1"}, CREDS) is True
    for bad in ("Bearer tok-3", "Bearer  tok-1", "Bearer tok-1 ", "Bearertok-1", "tok-1", "Bearer ", "Bearer", "Basic tok-1",
                "Token tok-1", "", "bearer TOK-1"):
        assert authenticate(c, {"Authorization": bad}, CREDS) is False, bad


def test_apikey_authentication():
    c = card(schemes=("apikey",))
    assert authenticate(c, {"X-API-Key": "key-1"}, CREDS) is True
    assert authenticate(c, {"x-api-key": "key-1"}, CREDS) is True
    assert authenticate(c, {"X-API-Key": "KEY-1"}, CREDS) is False
    assert authenticate(c, {"X-API-Key": ""}, CREDS) is False
    assert authenticate(c, {"Authorization": "Bearer key-1"}, CREDS) is False


def test_only_schemes_declared_in_the_card_count():
    assert authenticate(card(schemes=("bearer",)), {"X-API-Key": "key-1"}, CREDS) is False
    assert authenticate(card(schemes=("apikey",)), {"Authorization": "Bearer tok-1"}, CREDS) is False
    both = card(schemes=("bearer", "apikey"))
    assert authenticate(both, {"X-API-Key": "key-1"}, CREDS) is True
    assert authenticate(both, {"Authorization": "Bearer tok-2"}, CREDS) is True
    assert authenticate(both, {"Authorization": "Bearer wrong", "X-API-Key": "key-1"}, CREDS) is True


@pytest.mark.parametrize("headers", [None, [], "Bearer tok-1", {}, {"Authorization": None}, {"Authorization": 5},
                                     {"Authorization": ["Bearer tok-1"]}, {"X-Other": "Bearer tok-1"}])
def test_missing_or_garbage_headers_fail_closed(headers):
    assert authenticate(card(schemes=("bearer", "apikey")), headers, CREDS) is False


@pytest.mark.parametrize("creds", [{}, {"bearer": []}, {"apikey": []}, {"bearer": [], "apikey": []}, None])
def test_no_credentials_means_nobody_gets_in(creds):
    assert authenticate(card(schemes=("bearer", "apikey")), {"Authorization": "Bearer ", "X-API-Key": "x"}, creds) is False
    assert authenticate(card(schemes=("bearer",)), {"Authorization": "Bearer tok-1"}, creds or {}) is False


def test_empty_values_never_authenticate_even_if_an_empty_credential_is_configured():
    creds = {"bearer": [""], "apikey": [""]}
    c = card(schemes=("bearer", "apikey"))
    assert authenticate(c, {"Authorization": "Bearer "}, creds) is False
    assert authenticate(c, {"X-API-Key": ""}, creds) is False


def test_invalid_card_never_authenticates():
    headers = {"Authorization": "Bearer tok-1"}
    assert authenticate(card(schemes=("none",)), headers, CREDS) is False
    assert authenticate(card(schemes=("bearer", "none")), headers, CREDS) is False
    assert authenticate(card(url="http://example.com"), headers, CREDS) is False
    assert authenticate(None, headers, CREDS) is False


def test_credential_comparison_is_constant_time_and_checks_all_values(monkeypatch):
    calls = []
    real = hmac.compare_digest

    def spy(a, b):
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr(hmac, "compare_digest", spy)
    importlib.reload(sol)
    try:
        assert sol.authenticate(card(schemes=("bearer",)), {"Authorization": "Bearer tok-1"}, CREDS) is True
        assert len(calls) == 2                                             # не зупиняється на першому збігу
        calls.clear()
        assert sol.authenticate(card(schemes=("apikey",)), {"X-API-Key": "key-1"}, CREDS) is True
        assert len(calls) == 1
    finally:
        monkeypatch.undo()
        importlib.reload(sol)


# --- Task: життєвий цикл -----------------------------------------------------------------------

def task():
    return Task("t-1", "billing", "alice")


def test_initial_state_and_happy_path_with_history():
    t = task()
    assert t.state == "submitted" and t.history == [] and t.is_terminal is False
    t.transition("working", "billing")
    t.transition("input-required", "billing")
    t.transition("working", "alice")
    t.transition("completed", "billing")
    assert t.state == "completed" and t.is_terminal is True
    assert t.history == [("submitted", "working", "billing"), ("working", "input-required", "billing"),
                         ("input-required", "working", "alice"), ("working", "completed", "billing")]


@pytest.mark.parametrize("path, actor_ok", [
    (["working"], "billing"), (["failed"], "billing"), (["canceled"], "alice"),
    (["working", "failed"], "billing"), (["working", "canceled"], "alice"),
    (["working", "input-required", "canceled"], "alice"), (["working", "input-required", "failed"], "billing"),
])
def test_all_documented_transitions_work(path, actor_ok):
    t = task()
    for state in path[:-1]:
        t.transition(state, "alice" if (t.state, state) in {("input-required", "working")} else "billing")
    t.transition(path[-1], actor_ok)
    assert t.state == path[-1]


@pytest.mark.parametrize("state_path, new", [
    ([], "completed"), ([], "input-required"), ([], "submitted"), ([], "bogus"), ([], None), ([], 5),
    (["working"], "submitted"), (["working"], "working"), (["working", "input-required"], "completed"),
    (["working", "input-required"], "input-required"),
    (["working", "completed"], "working"), (["working", "completed"], "canceled"), (["failed"], "working"),
    (["canceled"], "working"), (["canceled"], "failed"),
])
def test_forbidden_transitions_raise_transition_error_and_keep_state(state_path, new):
    t = task()
    who = lambda s: "alice" if s == "canceled" else "billing"
    for s in state_path:
        t.transition(s, who(s))
    before = (t.state, t.history)
    for actor in ("billing", "alice", "mallory"):
        with pytest.raises(sol.TransitionError):
            t.transition(new, actor)
    assert (t.state, t.history) == before


def test_transition_error_is_a_value_error():
    assert issubclass(sol.TransitionError, ValueError)


@pytest.mark.parametrize("state_path, new, wrong_actors", [
    ([], "working", ["alice", "mallory", "", None]),
    ([], "failed", ["alice", "mallory"]),
    ([], "canceled", ["billing", "mallory"]),
    (["working"], "completed", ["alice", "mallory"]),
    (["working"], "input-required", ["alice", "mallory"]),
    (["working"], "canceled", ["billing", "mallory"]),
    (["working", "input-required"], "working", ["billing", "mallory"]),
    (["working", "input-required"], "failed", ["alice", "mallory"]),
    (["working", "input-required"], "canceled", ["billing", "mallory"]),
])
def test_wrong_actor_gets_permission_error_and_nothing_changes(state_path, new, wrong_actors):
    t = task()
    for s in state_path:
        t.transition(s, "billing")
    before = (t.state, t.history)
    for actor in wrong_actors:
        with pytest.raises(PermissionError):
            t.transition(new, actor)
    assert (t.state, t.history) == before


def test_history_is_a_copy_and_terminal_flags():
    t = task()
    t.transition("working", "billing")
    t.history.append(("x", "y", "z"))
    assert len(t.history) == 1
    for terminal in ("completed", "failed"):
        u = task()
        u.transition("working", "billing")
        u.transition(terminal, "billing")
        assert u.is_terminal is True
    c = task()
    c.transition("canceled", "alice")
    assert c.is_terminal is True


@pytest.mark.parametrize("args", [("", "a", "b"), ("t", "", "b"), ("t", "a", ""), (None, "a", "b"), ("t", None, "b"),
                                  ("t", "a", None), ("t", "same", "same"), (1, "a", "b")])
def test_task_constructor_validation(args):
    with pytest.raises(ValueError):
        Task(*args)
