import pytest

from solution import authorize_tool_call


def session(role="customer", confirmed=(), user_id=7):
    return {"user_id": user_id, "role": role, "confirmed_actions": set(confirmed)}


def call(tool, args, cid="c1"):
    return {"id": cid, "tool": tool, "args": args}


ALLOWED = [
    ("customer", "search_faq", {"query": "як повернути товар"}, ()),
    ("support", "search_faq", {"query": "x"}, ()),
    ("customer", "list_my_orders", {"user_id": 7}, ()),
    ("support", "list_my_orders", {"user_id": 7}, ()),
    ("customer", "get_order", {"order_id": 5}, ()),
    ("support", "get_any_user", {"user_id": 99}, ()),
    ("customer", "refund_order", {"order_id": 5, "amount": 100}, ("c1",)),
    ("customer", "refund_order", {"order_id": 5, "amount": 40.5}, ("c1",)),
    ("support", "refund_order", {"order_id": 5, "amount": 1000}, ("c1",)),
]

DENIED = [
    # невідомий інструмент
    ("customer", "delete_database", {}, ()),
    ("support", "read_file", {"path": "/etc/passwd"}, ()),
    # роль
    ("customer", "get_any_user", {"user_id": 99}, ()),
    # IDOR: чужий user_id
    ("customer", "list_my_orders", {"user_id": 8}, ()),
    ("support", "list_my_orders", {"user_id": 8}, ()),
    # зайві й відсутні args
    ("customer", "search_faq", {"query": "x", "limit": 1000}, ()),
    ("customer", "get_order", {}, ()),
    ("customer", "refund_order", {"order_id": 5}, ("c1",)),
    # валідація значень
    ("customer", "search_faq", {"query": ""}, ()),
    ("customer", "search_faq", {"query": "x" * 501}, ()),
    ("customer", "search_faq", {"query": 123}, ()),
    ("customer", "get_order", {"order_id": "5; DROP TABLE orders"}, ()),
    ("customer", "get_order", {"order_id": True}, ()),
    # refund без підтвердження людини
    ("customer", "refund_order", {"order_id": 5, "amount": 40}, ()),
    ("support", "refund_order", {"order_id": 5, "amount": 40}, ()),
    # підтвердження чужого виклику не рахується
    ("customer", "refund_order", {"order_id": 5, "amount": 40}, ("other",)),
    # ліміти сум
    ("customer", "refund_order", {"order_id": 5, "amount": 100.01}, ("c1",)),
    ("support", "refund_order", {"order_id": 5, "amount": 1000.01}, ("c1",)),
    ("customer", "refund_order", {"order_id": 5, "amount": 0}, ("c1",)),
    ("customer", "refund_order", {"order_id": 5, "amount": -5}, ("c1",)),
    ("customer", "refund_order", {"order_id": 5, "amount": "40"}, ("c1",)),
    ("customer", "refund_order", {"order_id": 5, "amount": float("nan")}, ("c1",)),
]


@pytest.mark.parametrize("role, tool, args, confirmed", ALLOWED)
def test_allowed(role, tool, args, confirmed):
    ok, reason = authorize_tool_call(call(tool, args), session(role, confirmed))
    assert ok is True, reason
    assert isinstance(reason, str) and reason


@pytest.mark.parametrize("role, tool, args, confirmed", DENIED)
def test_denied(role, tool, args, confirmed):
    ok, reason = authorize_tool_call(call(tool, args), session(role, confirmed))
    assert ok is False
    assert isinstance(reason, str) and reason


def test_model_cannot_self_confirm_via_args():
    c = call("refund_order", {"order_id": 5, "amount": 40, "confirmed": True})
    ok, _ = authorize_tool_call(c, session("customer", ()))
    assert ok is False
    c2 = call("refund_order", {"order_id": 5, "amount": 40})
    c2["confirmed"] = True
    ok, _ = authorize_tool_call(c2, session("customer", ()))
    assert ok is False


def test_unknown_role_denied():
    ok, reason = authorize_tool_call(call("search_faq", {"query": "x"}), session("hacker"))
    assert ok is False and reason


def test_malformed_call_does_not_crash():
    for bad in ({}, {"tool": "search_faq"}, {"tool": "search_faq", "args": None}, {"tool": 5, "args": {}}):
        ok, reason = authorize_tool_call(bad, session())
        assert ok is False and reason
