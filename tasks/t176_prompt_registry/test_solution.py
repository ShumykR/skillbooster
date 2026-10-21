import hashlib

import pytest

from solution import MissingVariable, PromptRegistry, Rendered


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        self.t += 1.0
        return self.t


@pytest.fixture
def reg():
    return PromptRegistry(clock=Clock())


def bucket(name, salt, user_id, total):
    return int(hashlib.sha256(f"{name}:{salt}:{user_id}".encode()).hexdigest()[:8], 16) % total


def expected_variant(name, salt, user_id, weights):
    total = sum(weights.values())
    b = bucket(name, salt, user_id, total)
    acc = 0
    for v in sorted(weights):
        acc += weights[v]
        if b < acc:
            return v


# --- версії --------------------------------------------------------------------------------------

def test_register_returns_incrementing_versions_per_name(reg):
    assert reg.register("greet", "Hi {{name}}") == 1
    assert reg.register("greet", "Hello {{name}}") == 2
    assert reg.register("other", "x") == 1
    assert reg.get("greet") == "Hello {{name}}"
    assert reg.get("greet", 1) == "Hi {{name}}"
    assert reg.get("other") == "x"


def test_register_same_text_as_latest_is_idempotent(reg):
    reg.register("p", "A")
    reg.register("p", "B")
    reg.activate("p", 1)
    assert reg.register("p", "B") == 2  # збігається з останньою версією
    assert reg.get("p") == "A"  # активність не змінилась
    assert reg.register("p", "A") == 3  # не остання: нова версія
    assert reg.get("p") == "A" and reg.get("p", 3) == "A"


def test_versions_are_immutable(reg):
    reg.register("p", "one {{a}}")
    reg.register("p", "two {{a}}")
    assert reg.get("p", 1) == "one {{a}}"


@pytest.mark.parametrize("name", ["", "Upper", "has space", "a/b", "ім'я", "a:b"])
def test_bad_names_rejected(reg, name):
    with pytest.raises(ValueError):
        reg.register(name, "x")


@pytest.mark.parametrize("name, version", [("nope", None), ("nope", 1)])
def test_unknown_prompt(reg, name, version):
    with pytest.raises(LookupError):
        reg.get(name, version)


@pytest.mark.parametrize("version", [0, 2, -1, 99])
def test_unknown_version(reg, version):
    reg.register("p", "x")
    with pytest.raises(LookupError):
        reg.get("p", version)
    with pytest.raises(LookupError):
        reg.activate("p", version)


# --- шаблони -------------------------------------------------------------------------------------

def test_variables_sorted_unique(reg):
    reg.register("p", "{{b}} {{a}} {{b}} and {{a_1}} { } {not} json {\"k\": 1}")
    assert reg.variables("p") == ["a", "a_1", "b"]


@pytest.mark.parametrize("tpl", ["{{ x }}", "{{1}}", "{{x", "x}}", "{{}}", "{{X}}", "{{a-b}}", "{{x}", "a {{ b", "{{a}} }}"])
def test_bad_templates_rejected_at_register(reg, tpl):
    with pytest.raises(ValueError):
        reg.register("p", tpl)


def test_single_braces_and_triple_braces_are_literal_text(reg):
    reg.register("p", 'Return JSON {"k": "{{v}}"} and {{{v}}}')
    assert reg.render("p", {"v": "X"}).text == 'Return JSON {"k": "X"} and {X}'


def test_render_substitutes_all_occurrences_and_str_values(reg):
    reg.register("p", "{{a}}-{{b}}-{{a}}")
    assert reg.render("p", {"a": 1, "b": 2.5}).text == "1-2.5-1"


def test_render_substitution_is_single_pass(reg):
    reg.register("p", "Q: {{q}} / ctx: {{ctx}}")
    out = reg.render("p", {"q": "{{ctx}}", "ctx": "SECRET"}).text
    assert out == "Q: {{ctx}} / ctx: SECRET"


def test_render_does_not_interpret_format_syntax(reg):
    reg.register("p", "{{x}}")
    assert reg.render("p", {"x": "{0.__class__} {x!r}"}).text == "{0.__class__} {x!r}"
    reg.register("q", "value: {x.__class__}")  # не плейсхолдер
    assert reg.render("q", {}).text == "value: {x.__class__}"


def test_missing_and_extra_variables(reg):
    reg.register("p", "{{a}} {{b}}")
    with pytest.raises(MissingVariable):
        reg.render("p", {"a": 1})
    with pytest.raises(ValueError):
        reg.render("p", {"a": 1, "b": 2, "c": 3})
    assert issubclass(MissingVariable, ValueError)
    assert reg.journal == []  # невдалий render не пишеться в журнал


def test_render_without_variables(reg):
    reg.register("p", "static text")
    r = reg.render("p", {})
    assert isinstance(r, Rendered) and r.text == "static text" and r.version == 1 and r.source == "active"


# --- активація і відкат --------------------------------------------------------------------------

def test_new_version_is_active_and_rollback_walks_back(reg):
    for text in ("v1", "v2", "v3"):
        reg.register("p", text)
    assert reg.get("p") == "v3"
    assert reg.rollback("p") == 2
    assert reg.get("p") == "v2"
    assert reg.rollback("p") == 1
    assert reg.get("p") == "v1"
    with pytest.raises(ValueError):
        reg.rollback("p")
    assert reg.get("p") == "v1"


def test_activate_then_rollback_returns_to_previous_active(reg):
    for text in ("v1", "v2", "v3"):
        reg.register("p", text)
    reg.activate("p", 1)
    assert reg.get("p") == "v1"
    assert reg.rollback("p") == 3
    assert reg.get("p") == "v3"


def test_activating_the_active_version_is_a_noop(reg):
    reg.register("p", "v1")
    reg.register("p", "v2")
    reg.activate("p", 2)
    reg.activate("p", 2)
    assert reg.rollback("p") == 1
    with pytest.raises(ValueError):
        reg.rollback("p")


def test_rollback_with_single_version_and_unknown_name(reg):
    reg.register("p", "v1")
    with pytest.raises(ValueError):
        reg.rollback("p")
    with pytest.raises(LookupError):
        reg.rollback("missing")


def test_rollback_changes_what_render_uses(reg):
    reg.register("p", "old {{x}}")
    reg.register("p", "new {{x}}")
    assert reg.render("p", {"x": 1}).text == "new 1"
    reg.rollback("p")
    r = reg.render("p", {"x": 1})
    assert (r.text, r.version) == ("old 1", 1)


# --- A/B ----------------------------------------------------------------------------------------

def make_ab(reg, weights, salt=""):
    reg.register("p", "A {{x}}")
    reg.register("p", "B {{x}}")
    reg.register("p", "C {{x}}")
    reg.set_experiment("p", weights, salt)


def test_assign_matches_documented_hash_formula(reg):
    weights = {1: 1, 2: 1, 3: 2}
    make_ab(reg, weights, salt="s1")
    for uid in list(range(50)) + ["alice", "bob", "user-42"]:
        assert reg.assign("p", uid) == expected_variant("p", "s1", uid, weights)


def test_assign_is_stable_and_order_of_weights_dict_irrelevant(reg):
    make_ab(reg, {3: 2, 1: 1, 2: 1})
    first = [reg.assign("p", u) for u in range(200)]
    assert first == [reg.assign("p", u) for u in range(200)]
    assert first == [expected_variant("p", "", u, {1: 1, 2: 1, 3: 2}) for u in range(200)]


def test_distribution_follows_weights(reg):
    make_ab(reg, {1: 50, 2: 30, 3: 20})
    counts = {1: 0, 2: 0, 3: 0}
    n = 5000
    for u in range(n):
        counts[reg.assign("p", f"user-{u}")] += 1
    assert abs(counts[1] / n - 0.5) < 0.03
    assert abs(counts[2] / n - 0.3) < 0.03
    assert abs(counts[3] / n - 0.2) < 0.03


def test_zero_weight_version_never_chosen_and_salt_changes_split(reg):
    make_ab(reg, {1: 0, 2: 1, 3: 1}, salt="x")
    assert all(reg.assign("p", u) in (2, 3) for u in range(300))
    a = [reg.assign("p", u) for u in range(300)]
    reg.set_experiment("p", {1: 0, 2: 1, 3: 1}, salt="y")
    assert a != [reg.assign("p", u) for u in range(300)]


def test_integer_and_string_user_ids_with_same_text_agree(reg):
    make_ab(reg, {1: 1, 2: 1})
    assert reg.assign("p", 7) == reg.assign("p", "7")


def test_no_experiment_assign_is_active_and_clear_experiment(reg):
    reg.register("p", "A")
    reg.register("p", "B")
    assert reg.assign("p", "u") == 2
    reg.set_experiment("p", {1: 1})
    assert reg.assign("p", "u") == 1
    reg.clear_experiment("p")
    assert reg.assign("p", "u") == 2


@pytest.mark.parametrize("weights", [{}, {1: 0}, {1: -1, 2: 3}, {1: 1.5}, {1: True, 2: 0}])
def test_bad_experiment_weights(reg, weights):
    reg.register("p", "A")
    reg.register("p", "B")
    with pytest.raises(ValueError):
        reg.set_experiment("p", weights)


def test_experiment_unknown_version(reg):
    reg.register("p", "A")
    with pytest.raises(LookupError):
        reg.set_experiment("p", {1: 1, 5: 1})


def test_render_source_priority(reg):
    make_ab(reg, {1: 1, 2: 1, 3: 1})
    uid = "alice"
    want = expected_variant("p", "", uid, {1: 1, 2: 1, 3: 1})
    r = reg.render("p", {"x": 0}, user_id=uid)
    assert (r.version, r.source) == (want, "experiment")
    r = reg.render("p", {"x": 0}, user_id=uid, version=2)
    assert (r.version, r.source) == (2, "explicit")
    r = reg.render("p", {"x": 0})  # без user_id: активна версія
    assert (r.version, r.source) == (3, "active")


# --- журнали -------------------------------------------------------------------------------------

def test_journal_records_every_render():
    clock = Clock()
    reg = PromptRegistry(clock=clock)
    reg.register("p", "A {{x}}")
    reg.register("p", "B {{x}}")
    reg.render("p", {"x": 1}, user_id="u1")
    reg.render("p", {"x": 2}, version=1)
    assert [(j["name"], j["version"], j["user_id"], j["source"]) for j in reg.journal] == [
        ("p", 2, "u1", "active"), ("p", 1, None, "explicit")]
    assert reg.journal[0]["ts"] < reg.journal[1]["ts"]
    assert set(reg.journal[0]) == {"name", "version", "user_id", "source", "ts"}


def test_history_lists_events_in_order_with_timestamps(reg):
    reg.register("p", "A")
    reg.register("p", "B")
    reg.activate("p", 1)
    reg.rollback("p")
    reg.set_experiment("p", {1: 1, 2: 1})
    reg.clear_experiment("p")
    hist = reg.history("p")
    assert [(e["event"], e["version"]) for e in hist] == [
        ("register", 1), ("register", 2), ("activate", 1), ("rollback", 2),
        ("experiment", None), ("experiment-clear", None)]
    ts = [e["ts"] for e in hist]
    assert ts == sorted(ts) and len(set(ts)) == len(ts)


def test_history_of_unknown_prompt(reg):
    with pytest.raises(LookupError):
        reg.history("nope")


def test_registries_are_independent():
    a, b = PromptRegistry(), PromptRegistry()
    a.register("p", "x")
    with pytest.raises(LookupError):
        b.get("p")
    a.render("p", {})
    assert b.journal == []
