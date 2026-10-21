import copy

import pytest

from solution import ExchangeError, audit_chain, authorize, exchange

NOW = 1_000_000

POLICY = {
    "max_ttl": 300,
    "max_depth": 3,
    "agents": {
        "agent-a": {"audiences": ["files-api", "calendar-api"],
                    "max_scope": ["files:read", "files:write", "calendar:read"],
                    "delegates_to": ["agent-b", "agent-c"]},
        "agent-b": {"audiences": ["files-api"],
                    "max_scope": ["files:read", "files:write", "files:admin"],
                    "delegates_to": ["agent-a", "agent-c"]},
        "agent-c": {"audiences": ["files-api"], "max_scope": ["files:read"], "delegates_to": ["agent-a"]},
        "agent-d": {"audiences": ["files-api"], "max_scope": ["files:read"], "delegates_to": []},
    },
}
TASK = ["files:read", "files:write", "calendar:read", "files:admin"]


def user_token(**kw):
    t = {"sub": "alice", "aud": ["files-api", "calendar-api"], "iat": NOW - 10, "exp": NOW + 3600,
         "scope": "files:read files:write files:admin calendar:read mail:send"}
    t.update(kw)
    return t


def ex(token=None, actor="agent-a", audience="files-api", now=NOW, policy=POLICY, task=TASK, requested=None):
    return exchange(token if token is not None else user_token(), actor, audience, now, policy, task, requested)


def code_of(**kw):
    with pytest.raises(ExchangeError) as e:
        ex(**kw)
    return e.value.code


# --- успішний обмін ----------------------------------------------------------------------------

def test_exchange_narrows_to_intersection_of_user_task_and_agent():
    t = ex(task=["files:read", "files:write", "mail:send"])
    assert t["scope"] == "files:read files:write"  # mail:send поза стелею агента, calendar поза задачею


def test_exchange_shape_and_binding():
    t = ex()
    assert t["sub"] == "alice"
    assert t["aud"] == "files-api"
    assert t["iat"] == NOW
    assert t["act"] == {"sub": "agent-a"}
    assert t["scope"] == "calendar:read files:read files:write"
    assert set(t) == {"sub", "aud", "scope", "iat", "exp", "act"}


def test_scope_is_sorted_and_deduplicated():
    t = ex(requested="files:write files:read files:write")
    assert t["scope"] == "files:read files:write"
    t = ex(requested=["files:write", "files:read", "files:read"], task=["files:read", "files:write"])
    assert t["scope"] == "files:read files:write"


def test_requested_subset_is_granted_exactly():
    assert ex(requested="files:read")["scope"] == "files:read"
    assert ex(requested={"calendar:read"}, audience="calendar-api")["scope"] == "calendar:read"


def test_ttl_is_short_and_never_exceeds_subject_token():
    assert ex()["exp"] == NOW + 300
    assert ex(token=user_token(exp=NOW + 100))["exp"] == NOW + 100
    assert ex(token=user_token(exp=NOW + 301))["exp"] == NOW + 300
    assert ex(token=user_token(exp=NOW + 300))["exp"] == NOW + 300
    assert ex(token=user_token(exp=NOW + 1))["exp"] == NOW + 1


def test_audience_is_exactly_the_requested_one_even_if_subject_has_many():
    t = ex(audience="calendar-api", task=["calendar:read", "files:read"])
    assert t["aud"] == "calendar-api" and isinstance(t["aud"], str)
    assert t["scope"] == "calendar:read files:read"


def test_subject_aud_may_be_a_plain_string():
    t = ex(token=user_token(aud="files-api"))
    assert t["aud"] == "files-api"


def test_inputs_are_not_mutated():
    token, policy = user_token(), copy.deepcopy(POLICY)
    snap = copy.deepcopy(token)
    first = exchange(token, "agent-a", "files-api", NOW, policy, TASK)
    exchange(first, "agent-b", "files-api", NOW, policy, TASK)
    assert token == snap and policy == POLICY
    assert first["act"] == {"sub": "agent-a"}


# --- ланцюжок і заборона ескалації між агентами ------------------------------------------------

def test_delegation_chain_grows_and_scope_only_shrinks():
    t1 = ex(actor="agent-a")
    t2 = exchange(t1, "agent-b", "files-api", NOW + 5, POLICY, TASK)
    assert t2["act"] == {"sub": "agent-b", "act": {"sub": "agent-a"}}
    assert t2["sub"] == "alice"
    assert set(t2["scope"].split()) <= set(t1["scope"].split())
    assert "files:admin" not in t2["scope"].split()  # агент A цього не мав, B не отримає через A
    t3 = exchange(t2, "agent-c", "files-api", NOW + 6, POLICY, TASK)
    assert t3["act"] == {"sub": "agent-c", "act": {"sub": "agent-b", "act": {"sub": "agent-a"}}}
    assert t3["scope"] == "files:read"


def test_sub_delegation_cannot_exceed_parent_token_even_if_agent_ceiling_is_higher():
    t1 = ex(actor="agent-a", task=["files:read", "files:admin"])
    assert t1["scope"] == "files:read"
    t2 = exchange(t1, "agent-b", "files-api", NOW, POLICY, TASK)
    assert t2["scope"] == "files:read"
    with pytest.raises(ExchangeError) as e:
        exchange(t1, "agent-b", "files-api", NOW, POLICY, TASK, "files:admin")
    assert e.value.code == "scope-escalation" and e.value.detail == ["files:admin"]


def test_sub_delegation_expiry_is_bounded_by_parent_token():
    t1 = ex(actor="agent-a")
    t2 = exchange(t1, "agent-b", "files-api", NOW + 250, POLICY, TASK)
    assert t2["exp"] == t1["exp"] == NOW + 300


def test_delegation_only_to_agents_listed_in_delegates_to():
    t1 = ex(actor="agent-a")
    with pytest.raises(ExchangeError) as e:
        exchange(t1, "agent-d", "files-api", NOW, POLICY, TASK)
    assert e.value.code == "delegation-not-allowed"
    t_d = ex(actor="agent-d", task=["files:read"])
    with pytest.raises(ExchangeError) as e:
        exchange(t_d, "agent-a", "files-api", NOW, POLICY, TASK)
    assert e.value.code == "delegation-not-allowed"  # d нікому нічого не делегує


def test_actor_cycle_is_rejected_anywhere_in_chain():
    t1 = ex(actor="agent-a")
    t2 = exchange(t1, "agent-b", "files-api", NOW, POLICY, TASK)
    assert code_of(token=t2, actor="agent-a") == "actor-cycle"
    t3 = exchange(t2, "agent-c", "files-api", NOW, POLICY, TASK)
    with pytest.raises(ExchangeError) as e:
        exchange(t3, "agent-a", "files-api", NOW, POLICY, TASK)
    assert e.value.code == "actor-cycle"  # a глибоко всередині ланцюжка


def test_chain_depth_limit():
    t1 = ex(actor="agent-a")
    t2 = exchange(t1, "agent-b", "files-api", NOW, POLICY, TASK)
    t3 = exchange(t2, "agent-c", "files-api", NOW, POLICY, TASK)  # довжина 3 = max_depth: ще можна
    assert len(audit_chain(t3)) == 4
    pol = copy.deepcopy(POLICY)
    pol["agents"]["agent-c"]["delegates_to"] = ["agent-d"]
    pol["agents"]["agent-d"]["audiences"] = ["files-api"]
    with pytest.raises(ExchangeError) as e:
        exchange(t3, "agent-d", "files-api", NOW, pol, TASK)
    assert e.value.code == "chain-too-deep"
    pol["max_depth"] = 1
    with pytest.raises(ExchangeError) as e:
        exchange(t1, "agent-b", "files-api", NOW, pol, TASK)
    assert e.value.code == "chain-too-deep"
    pol["max_depth"] = 0
    assert code_of(policy=pol) == "chain-too-deep"


# --- відмови: кожна причина окремо -------------------------------------------------------------

@pytest.mark.parametrize("token", [
    None, "token", 42, [], {}, {"sub": "a", "aud": "x", "scope": "s"}, {"sub": "a", "aud": "x", "exp": NOW + 5},
    {"sub": "a", "scope": "s", "exp": NOW + 5}, {"aud": "x", "scope": "s", "exp": NOW + 5},
    user_token(act="agent-a"), user_token(act=["agent-a"]),
])
def test_invalid_subject_token(token):
    with pytest.raises(ExchangeError) as e:
        exchange(token, "agent-a", "files-api", NOW, POLICY, TASK)
    assert e.value.code == "invalid-token"


def test_expired_subject_token_boundary():
    assert code_of(token=user_token(exp=NOW)) == "expired"
    assert code_of(token=user_token(exp=NOW - 1)) == "expired"
    assert ex(token=user_token(exp=NOW + 1))["exp"] == NOW + 1


def test_unknown_actor():
    assert code_of(actor="agent-x") == "unknown-actor"
    assert code_of(actor="") == "unknown-actor"


def test_audience_not_allowed_for_agent():
    assert code_of(actor="agent-b", audience="calendar-api") == "audience-not-allowed"
    assert code_of(audience="mail-api") == "audience-not-allowed"


def test_audience_mismatch_with_subject_token():
    assert code_of(token=user_token(aud="calendar-api")) == "audience-mismatch"
    assert code_of(token=user_token(aud=["calendar-api", "mail-api"])) == "audience-mismatch"


def test_scope_escalation_lists_sorted_offenders():
    with pytest.raises(ExchangeError) as e:
        ex(requested="files:read mail:send files:admin")
    assert e.value.code == "scope-escalation"
    assert e.value.detail == ["files:admin", "mail:send"]
    with pytest.raises(ExchangeError) as e:
        ex(requested=["files:write"], task=["files:read"])
    assert e.value.code == "scope-escalation" and e.value.detail == ["files:write"]


def test_scope_escalation_for_scope_user_does_not_have():
    with pytest.raises(ExchangeError) as e:
        ex(token=user_token(scope="files:read"), requested="files:write")
    assert e.value.code == "scope-escalation"


def test_empty_scope_when_intersection_is_empty():
    assert code_of(task=["mail:send"]) == "empty-scope"
    assert code_of(token=user_token(scope="mail:send")) == "empty-scope"
    assert code_of(task=[]) == "empty-scope"
    assert code_of(requested="") == "empty-scope"
    assert code_of(requested=[]) == "empty-scope"


def test_check_order():
    expired_unknown = user_token(exp=NOW - 1)
    assert code_of(token=expired_unknown, actor="agent-x") == "expired"
    assert code_of(actor="agent-x", audience="mail-api") == "unknown-actor"
    assert code_of(audience="mail-api", requested="mail:send") == "audience-not-allowed"
    assert code_of(token=user_token(aud="calendar-api"), requested="mail:send") == "audience-mismatch"
    assert code_of(token=user_token(scope="x"), task=[], requested="mail:send") == "scope-escalation"
    t1 = ex(actor="agent-a")
    assert code_of(token=t1, actor="agent-a", audience="mail-api") == "delegation-not-allowed"
    assert code_of(token=t1, actor="agent-x", audience="mail-api") == "unknown-actor"


# --- authorize (ресурсний сервер) --------------------------------------------------------------

def test_authorize_ok_for_exchanged_token():
    t = ex()
    assert authorize(t, "files-api", "files:read", NOW + 10) == (True, "ok")
    assert authorize(t, "files-api", ["files:read", "files:write"], NOW + 10) == (True, "ok")
    assert authorize(t, "files-api", [], NOW + 10) == (True, "ok")


def test_authorize_expiry_boundary():
    t = ex()
    assert authorize(t, "files-api", "files:read", t["exp"] - 1) == (True, "ok")
    assert authorize(t, "files-api", "files:read", t["exp"]) == (False, "expired")
    assert authorize(t, "files-api", "files:read", t["exp"] + 1000) == (False, "expired")


def test_authorize_audience_binding():
    t = ex()
    assert authorize(t, "calendar-api", "files:read", NOW) == (False, "wrong-audience")
    assert authorize(user_token(), "calendar-api", "calendar:read", NOW) == (True, "ok")
    assert authorize(user_token(aud="files-api"), "files-api", "files:read", NOW) == (True, "ok")
    assert authorize(user_token(aud="files-api"), "files", "files:read", NOW) == (False, "wrong-audience")


def test_authorize_scope():
    t = ex(requested="files:read")
    assert authorize(t, "files-api", "files:write", NOW) == (False, "insufficient-scope")
    assert authorize(t, "files-api", "files:read files:write", NOW) == (False, "insufficient-scope")
    assert authorize(t, "files-api", ["files:read", "files:admin"], NOW) == (False, "insufficient-scope")
    assert authorize(t, "files-api", "files:rea", NOW) == (False, "insufficient-scope")


def test_authorize_reason_order_and_invalid():
    t = ex(requested="files:read")
    assert authorize(t, "calendar-api", "files:write", t["exp"]) == (False, "expired")
    assert authorize(t, "calendar-api", "files:write", NOW) == (False, "wrong-audience")
    for bad in (None, "x", {}, {"sub": "a", "aud": "x", "scope": "s"}, {"aud": "x", "scope": "s", "exp": NOW + 5}):
        assert authorize(bad, "x", "s", NOW) == (False, "invalid-token")


# --- audit_chain -------------------------------------------------------------------------------

def test_audit_chain_is_chronological():
    assert audit_chain({"sub": "alice"}) == ["alice"]
    assert audit_chain({"sub": "alice", "act": {"sub": "a"}}) == ["alice", "a"]
    assert audit_chain({"sub": "alice", "act": {"sub": "b", "act": {"sub": "a"}}}) == ["alice", "a", "b"]
    t1 = ex(actor="agent-a")
    t2 = exchange(t1, "agent-b", "files-api", NOW, POLICY, TASK)
    assert audit_chain(t2) == ["alice", "agent-a", "agent-b"]
    assert audit_chain(user_token()) == ["alice"]


def nest(n):
    act = None
    for i in range(n):
        act = {"sub": f"a{i}", **({"act": act} if act else {})}
    return {"sub": "s", "act": act}


def test_audit_chain_depth_limit_and_malformed():
    assert audit_chain(nest(10)) == ["s"] + [f"a{i}" for i in range(10)]
    with pytest.raises(ValueError):
        audit_chain(nest(11))
    cyc = {"sub": "x"}
    cyc["act"] = cyc
    with pytest.raises(ValueError):
        audit_chain({"sub": "alice", "act": cyc})
    for bad in ({"sub": "a", "act": "agent"}, {"sub": "a", "act": {"no": "sub"}},
                {"sub": "a", "act": {"sub": "b", "act": 5}}):
        with pytest.raises(ValueError):
            audit_chain(bad)


def test_result_does_not_alias_the_presented_token():
    t1 = ex(actor="agent-a")
    t2 = exchange(t1, "agent-b", "files-api", NOW, POLICY, TASK)
    t2["act"]["act"]["sub"] = "tampered"
    assert t1["act"] == {"sub": "agent-a"}
