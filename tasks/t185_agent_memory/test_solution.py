import pytest

from solution import AgentMemory


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def tick(self, dt):
        self.t += dt


def make(**kw):
    clock = Clock()
    return AgentMemory(clock, **kw), clock


# --- конструктор -------------------------------------------------------------------------------

@pytest.mark.parametrize("kw", [{"window": 0}, {"window": -1}, {"window": 1.5}, {"window": True}, {"window": "3"},
                                {"default_ttl": 0}, {"default_ttl": -5}, {"default_ttl": "10"}, {"default_ttl": True}])
def test_constructor_validation(kw):
    with pytest.raises(ValueError):
        AgentMemory(Clock(), **kw)


# --- короткострокова памʼять -------------------------------------------------------------------

def test_context_keeps_only_last_window_messages_in_order():
    mem, _ = make(window=3)
    for i in range(5):
        mem.add_message("u1", "user" if i % 2 == 0 else "assistant", f"m{i}")
    assert mem.context("u1") == [{"role": "user", "text": "m2"}, {"role": "assistant", "text": "m3"},
                                 {"role": "user", "text": "m4"}]
    assert mem.context("nobody") == []


def test_default_window_is_six_and_users_have_separate_windows():
    mem, _ = make()
    for i in range(8):
        mem.add_message("a", "user", f"a{i}")
    mem.add_message("b", "tool", "b0")
    assert [m["text"] for m in mem.context("a")] == [f"a{i}" for i in range(2, 8)]
    assert mem.context("b") == [{"role": "tool", "text": "b0"}]


def test_context_returns_copies():
    mem, _ = make()
    mem.add_message("u", "user", "hi")
    mem.context("u")[0]["text"] = "HACKED"
    mem.context("u").append({"role": "user", "text": "x"})
    assert mem.context("u") == [{"role": "user", "text": "hi"}]


@pytest.mark.parametrize("args", [("", "user", "x"), (None, "user", "x"), (5, "user", "x"), ("u", "bot", "x"),
                                  ("u", "", "x"), ("u", None, "x"), ("u", "user", None), ("u", "user", 5), ("u", "USER", "x")])
def test_add_message_validation(args):
    mem, _ = make()
    with pytest.raises(ValueError):
        mem.add_message(*args)
    assert mem.stats() == {"users": 0, "facts": 0, "messages": 0}


def test_empty_text_and_all_roles_are_allowed():
    mem, _ = make(window=10)
    for role in ("user", "assistant", "system", "tool"):
        mem.add_message("u", role, "")
    assert len(mem.context("u")) == 4


# --- remember: додавання, дублі, конфлікти -----------------------------------------------------

def test_added_fact_record_shape():
    mem, clock = make()
    assert mem.remember("u", "city", "Kyiv", "chat:1") == "added"
    assert mem.get("u", "city") == {"value": "Kyiv", "source": "chat:1", "ts": 1000.0, "expires": None, "confirmations": 0}
    assert mem.history("u", "city") == []
    assert mem.get("u", "missing") is None and mem.get("nobody", "city") is None


def test_duplicate_changes_only_confirmations():
    mem, clock = make()
    mem.remember("u", "city", "Kyiv", "chat:1")
    clock.tick(50)
    assert mem.remember("u", "city", "Kyiv", "email:7") == "duplicate"
    assert mem.remember("u", "city", "Kyiv", "email:8", ts=5.0) == "duplicate"        # навіть зі старим ts
    fact = mem.get("u", "city")
    assert fact == {"value": "Kyiv", "source": "chat:1", "ts": 1000.0, "expires": None, "confirmations": 2}
    assert mem.history("u", "city") == []


def test_duplicate_requires_same_type_and_equal_value():
    mem, _ = make()
    mem.remember("u", "flag", 1, "s")
    assert mem.remember("u", "flag", True, "s") == "updated"
    assert mem.remember("u", "flag", True, "s") == "duplicate"
    assert mem.remember("u", "prefs", {"a": [1, 2]}, "s") == "added"
    assert mem.remember("u", "prefs", {"a": [1, 2]}, "s") == "duplicate"
    assert mem.remember("u", "prefs", {"a": [1, 3]}, "s") == "updated"


def test_newer_value_wins_and_old_goes_to_history_in_order():
    mem, clock = make()
    mem.remember("u", "city", "Kyiv", "chat:1")
    clock.tick(10)
    assert mem.remember("u", "city", "Lviv", "chat:2") == "updated"
    clock.tick(10)
    assert mem.remember("u", "city", "Odesa", "profile") == "updated"
    assert mem.get("u", "city") == {"value": "Odesa", "source": "profile", "ts": 1020.0, "expires": None, "confirmations": 0}
    assert mem.history("u", "city") == [{"value": "Kyiv", "source": "chat:1", "ts": 1000.0},
                                        {"value": "Lviv", "source": "chat:2", "ts": 1010.0}]


def test_older_event_is_stale_and_changes_nothing():
    mem, clock = make()
    mem.remember("u", "city", "Lviv", "chat:2", ts=500.0)
    before = (mem.get("u", "city"), mem.history("u", "city"))
    assert mem.remember("u", "city", "Kyiv", "chat:1", ts=499.9) == "stale"
    assert (mem.get("u", "city"), mem.history("u", "city")) == before


def test_equal_timestamp_lets_the_later_write_win():
    mem, _ = make()
    mem.remember("u", "city", "Kyiv", "a", ts=500.0)
    assert mem.remember("u", "city", "Lviv", "b", ts=500.0) == "updated"
    assert mem.get("u", "city")["value"] == "Lviv"


def test_update_resets_confirmations():
    mem, _ = make()
    mem.remember("u", "k", "v1", "s", ts=1.0)
    mem.remember("u", "k", "v1", "s")
    mem.remember("u", "k", "v1", "s")
    assert mem.get("u", "k")["confirmations"] == 2
    mem.remember("u", "k", "v2", "s", ts=2.0)
    assert mem.get("u", "k")["confirmations"] == 0


def test_explicit_ts_is_stored_and_history_keeps_event_times():
    mem, _ = make()
    mem.remember("u", "k", "a", "s1", ts=10)
    mem.remember("u", "k", "b", "s2", ts=20)
    assert mem.get("u", "k")["ts"] == 20 and mem.history("u", "k") == [{"value": "a", "source": "s1", "ts": 10}]


@pytest.mark.parametrize("args", [
    ("", "k", "v", "s"), ("u", "", "v", "s"), ("u", "k", "v", ""), ("u", "k", None, "s"), (None, "k", "v", "s"),
    ("u", 5, "v", "s"), ("u", "k", "v", None), ("u", "k", "v", 7)])
def test_remember_validation_and_nothing_stored(args):
    mem, _ = make()
    with pytest.raises(ValueError):
        mem.remember(*args)
    assert mem.stats()["facts"] == 0


@pytest.mark.parametrize("kw", [{"ttl": 0}, {"ttl": -1}, {"ttl": "5"}, {"ttl": True}, {"ts": "now"}, {"ts": True}])
def test_remember_validation_of_ttl_and_ts(kw):
    mem, _ = make()
    with pytest.raises(ValueError):
        mem.remember("u", "k", "v", "s", **kw)
    assert mem.stats()["facts"] == 0


def test_stored_values_are_isolated_from_caller_mutation():
    mem, _ = make()
    value = {"langs": ["uk"]}
    mem.remember("u", "prefs", value, "s")
    value["langs"].append("en")
    mem.get("u", "prefs")["value"]["langs"].append("de")
    mem.recall("u")["prefs"]["value"]["langs"].append("pl")
    assert mem.get("u", "prefs")["value"] == {"langs": ["uk"]}
    mem.remember("u", "prefs", {"langs": ["fr"]}, "s", ts=2000)
    mem.history("u", "prefs")[0]["value"]["langs"].append("x")
    assert mem.history("u", "prefs")[0]["value"] == {"langs": ["uk"]}


# --- TTL ---------------------------------------------------------------------------------------

def test_ttl_boundary_is_exclusive_and_expires_is_reported():
    mem, clock = make()
    mem.remember("u", "k", "v", "s", ttl=60)
    assert mem.get("u", "k")["expires"] == 1060.0
    clock.t = 1059.999
    assert mem.get("u", "k") is not None
    clock.t = 1060.0
    assert mem.get("u", "k") is None and mem.recall("u") == {}
    assert mem.history("u", "k") == []


def test_default_ttl_and_explicit_ttl_override():
    mem, clock = make(default_ttl=100)
    mem.remember("u", "a", 1, "s")
    mem.remember("u", "b", 2, "s", ttl=10)
    mem.remember("u", "c", 3, "s", ttl=1000)
    assert [mem.get("u", k)["expires"] for k in "abc"] == [1100.0, 1010.0, 2000.0]
    clock.t = 1050
    assert sorted(mem.recall("u")) == ["a", "c"]


def test_expiry_is_based_on_event_ts_not_write_time():
    mem, clock = make()
    mem.remember("u", "k", "v", "s", ttl=100, ts=900.0)        # ts + ttl = 1000 -> уже протермінований
    assert mem.get("u", "k") is None


def test_expired_fact_is_replaced_by_added_and_history_is_reset():
    mem, clock = make()
    mem.remember("u", "k", "old1", "s", ttl=10)
    clock.tick(5)
    mem.remember("u", "k", "old2", "s", ttl=10)
    assert len(mem.history("u", "k")) == 1
    clock.tick(100)
    assert mem.remember("u", "k", "old2", "s2") == "added"              # те саме значення, але факт мертвий: не duplicate
    assert mem.history("u", "k") == [] and mem.get("u", "k")["source"] == "s2"
    clock.tick(1)
    assert mem.remember("u", "k", "older", "s", ts=1.0) == "stale"


def test_stale_check_ignores_expired_facts():
    mem, clock = make()
    mem.remember("u", "k", "v1", "s", ttl=10)
    clock.tick(20)
    assert mem.remember("u", "k", "v2", "s", ts=1.0) == "added"        # протермінований факт не блокує «старіший» запис


def test_fact_without_ttl_never_expires():
    mem, clock = make()
    mem.remember("u", "k", "v", "s")
    clock.tick(10 ** 9)
    assert mem.get("u", "k")["value"] == "v"


def test_purge_removes_only_expired_facts_and_reports_count():
    mem, clock = make()
    mem.remember("a", "x", 1, "s", ttl=10)
    mem.remember("a", "y", 2, "s")
    mem.remember("b", "x", 3, "s", ttl=10)
    mem.remember("b", "z", 4, "s", ttl=1000)
    assert mem.stats()["facts"] == 4
    clock.tick(10)
    assert mem.stats()["facts"] == 4                                    # stats рахує й протерміновані, доки не purge
    assert mem.purge() == 2
    assert mem.stats() == {"users": 2, "facts": 2, "messages": 0}
    assert mem.purge() == 0
    assert sorted(mem.recall("a")) == ["y"] and sorted(mem.recall("b")) == ["z"]


def test_purge_drops_users_who_are_left_with_nothing():
    mem, clock = make()
    mem.remember("a", "x", 1, "s", ttl=1)
    clock.tick(5)
    assert mem.purge() == 1
    assert mem.stats() == {"users": 0, "facts": 0, "messages": 0}


# --- recall ------------------------------------------------------------------------------------

def test_recall_sorted_by_key_and_users_are_isolated():
    mem, _ = make()
    mem.remember("a", "zeta", 1, "s")
    mem.remember("a", "alpha", 2, "s")
    mem.remember("b", "alpha", 99, "s")
    assert list(mem.recall("a")) == ["alpha", "zeta"]
    assert mem.recall("a")["alpha"]["value"] == 2 and mem.recall("b")["alpha"]["value"] == 99
    assert mem.recall("nobody") == {}
    assert mem.get("b", "zeta") is None


# --- forget_user -------------------------------------------------------------------------------

def test_forget_user_removes_everything_about_the_user_only():
    mem, clock = make()
    mem.remember("a", "city", "Kyiv", "s")
    mem.remember("a", "city", "Lviv", "s2")
    mem.remember("a", "old", 1, "s", ttl=1)
    mem.add_message("a", "user", "hello")
    mem.add_message("a", "assistant", "hi")
    mem.remember("b", "city", "Odesa", "s")
    mem.add_message("b", "user", "yo")
    clock.tick(10)
    assert mem.forget_user("a") == {"facts": 2, "messages": 2}            # протермінований факт теж рахується
    assert mem.recall("a") == {} and mem.context("a") == [] and mem.history("a", "city") == []
    assert mem.get("b", "city")["value"] == "Odesa" and mem.context("b") == [{"role": "user", "text": "yo"}]
    assert mem.stats() == {"users": 1, "facts": 1, "messages": 1}
    assert mem.forget_user("a") == {"facts": 0, "messages": 0}
    assert mem.forget_user("never-seen") == {"facts": 0, "messages": 0}


def test_after_forgetting_the_user_starts_clean():
    mem, _ = make()
    mem.remember("a", "city", "Kyiv", "s")
    mem.remember("a", "city", "Lviv", "s")
    mem.forget_user("a")
    assert mem.remember("a", "city", "Lviv", "s2") == "added"            # не duplicate і без старої історії
    assert mem.history("a", "city") == [] and mem.get("a", "city")["confirmations"] == 0


def test_stats_counts_users_with_messages_or_facts_only():
    mem, _ = make()
    mem.add_message("m", "user", "x")
    mem.remember("f", "k", "v", "s")
    mem.remember("both", "k", "v", "s")
    mem.add_message("both", "user", "x")
    assert mem.stats() == {"users": 3, "facts": 2, "messages": 2}
    mem.forget_user("both")
    assert mem.stats() == {"users": 2, "facts": 1, "messages": 1}
