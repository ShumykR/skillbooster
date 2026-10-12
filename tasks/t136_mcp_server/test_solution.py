import json

import pytest

from solution import McpServer

ORDERS = {"A1": {"id": "A1", "status": "відправлено", "items": 2}}


def order_status(order_id):
    if order_id not in ORDERS:
        raise KeyError(order_id)
    return ORDERS[order_id]


def tool(name, props, required, handler, description="d"):
    return {"name": name, "description": description, "inputSchema": {"type": "object", "properties": props, "required": required}, "handler": handler}


TOOLS = [
    tool("order_status", {"order_id": {"type": "string"}}, ["order_id"], order_status, "Статус замовлення"),
    tool("add", {"a": {"type": "number"}, "b": {"type": "number"}}, ["a", "b"], lambda a, b: a + b),
    tool("greet", {"name": {"type": "string"}}, [], lambda name="world": f"hello {name}"),
    tool("count", {"n": {"type": "integer"}, "flag": {"type": "boolean"}, "xs": {"type": "array"}, "o": {"type": "object"}}, [], lambda **kw: len(kw)),
]
RESOURCES = {"docs://faq": {"name": "FAQ", "mimeType": "text/markdown", "read": lambda: "# FAQ\nПовернення за 14 днів"}}


@pytest.fixture
def server():
    s = McpServer("shop", "1.2.3", TOOLS, RESOURCES)
    s.handle(req("initialize", id=0))
    return s


def req(method, params=None, id=1):
    m = {"jsonrpc": "2.0", "method": method}
    if id is not None:
        m["id"] = id
    if params is not None:
        m["params"] = params
    return m


def call(server, name, arguments=None, id=1):
    params = {"name": name}
    if arguments is not None:
        params["arguments"] = arguments
    return server.handle(req("tools/call", params, id))


def error_of(response):
    return response["error"]["code"], response["error"]["message"]


# ---------- protocol basics --------------------------------------------------------------------------------------------


def test_parse_error_and_invalid_requests():
    s = McpServer("x", "1")
    assert s.handle("{not json") == {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
    for bad in (5, "[1,", None, {"method": "ping"}, {"jsonrpc": "1.0", "method": "ping", "id": 1}, {"jsonrpc": "2.0", "method": 7, "id": 9}, {"jsonrpc": "2.0", "id": 2}):
        out = s.handle(bad)
        assert out["error"]["code"] in (-32600, -32700), bad
    assert s.handle({"jsonrpc": "2.0", "method": 7, "id": 9}) == {"jsonrpc": "2.0", "id": 9, "error": {"code": -32600, "message": "Invalid Request"}}
    assert s.handle({"method": "ping"})["id"] is None
    assert s.handle([]) == {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}


def test_ping_works_before_initialize_and_ids_are_echoed():
    s = McpServer("x", "1")
    assert s.handle(req("ping", id=0)) == {"jsonrpc": "2.0", "id": 0, "result": {}}, "id 0 це не відсутній id"
    assert s.handle(req("ping", id="abc"))["id"] == "abc"


def test_notifications_get_no_response():
    s = McpServer("x", "1")
    assert s.handle(req("notifications/initialized", id=None)) is None
    assert s.handle(req("no/such/method", id=None)) is None
    assert s.handle(req("tools/call", {"bad": 1}, id=None)) is None
    assert s.handle_json(json.dumps(req("ping", id=None))) is None


def test_unknown_method():
    s = McpServer("x", "1")
    assert error_of(s.handle(req("nope"))) == (-32601, "Method not found")


# ---------- initialize --------------------------------------------------------------------------------------------------------


def test_initialize_result_and_state():
    s = McpServer("shop", "1.2.3", TOOLS, RESOURCES)
    assert s.initialized is False
    assert s.handle(req("initialize", {"protocolVersion": "x"})) == {"jsonrpc": "2.0", "id": 1, "result": {
        "protocolVersion": "2024-11-05", "capabilities": {"tools": {}, "resources": {}}, "serverInfo": {"name": "shop", "version": "1.2.3"}}}
    assert s.initialized is True


def test_capabilities_reflect_what_exists():
    assert McpServer("a", "1", TOOLS).handle(req("initialize"))["result"]["capabilities"] == {"tools": {}}
    assert McpServer("a", "1", (), RESOURCES).handle(req("initialize"))["result"]["capabilities"] == {"resources": {}}
    assert McpServer("a", "1").handle(req("initialize"))["result"]["capabilities"] == {}


@pytest.mark.parametrize("method, params", [("tools/list", None), ("tools/call", {"name": "add"}), ("resources/list", None), ("resources/read", {"uri": "docs://faq"})])
def test_methods_need_initialize_first(method, params):
    s = McpServer("x", "1", TOOLS, RESOURCES)
    assert error_of(s.handle(req(method, params))) == (-32002, "Server not initialized")
    s.handle(req("initialize"))
    after = s.handle(req(method, params))
    assert error_of(after)[0] != -32002 if "error" in after else True


# ---------- tools --------------------------------------------------------------------------------------------------------------


def test_tools_list_hides_handlers_and_keeps_order(server):
    tools = server.handle(req("tools/list"))["result"]["tools"]
    assert [t["name"] for t in tools] == ["order_status", "add", "greet", "count"]
    assert tools[0] == {"name": "order_status", "description": "Статус замовлення", "inputSchema": TOOLS[0]["inputSchema"]}
    assert all(set(t) == {"name", "description", "inputSchema"} for t in tools)


def test_call_results_are_text_content(server):
    r = call(server, "order_status", {"order_id": "A1"})
    assert r["result"] == {"content": [{"type": "text", "text": '{"id": "A1", "items": 2, "status": "відправлено"}'}], "isError": False}
    assert call(server, "add", {"a": 2, "b": 3.5})["result"]["content"][0]["text"] == "5.5"
    assert call(server, "greet", {"name": "Анна"})["result"]["content"][0]["text"] == "hello Анна"
    assert call(server, "greet")["result"]["content"][0]["text"] == "hello world", "arguments необовʼязкові"
    assert call(server, "greet", {})["result"]["isError"] is False


def test_tool_exceptions_are_results_not_protocol_errors(server):
    r = call(server, "order_status", {"order_id": "ZZ"})
    assert "error" not in r
    assert r["result"] == {"content": [{"type": "text", "text": "Tool failed: KeyError: 'ZZ'"}], "isError": True}


def test_unknown_tool_and_bad_params(server):
    assert error_of(call(server, "nope")) == (-32602, "Unknown tool: nope")
    assert error_of(server.handle(req("tools/call", "text"))) == (-32602, "Invalid params")
    assert error_of(server.handle(req("tools/call", {"name": "greet", "arguments": [1]}))) == (-32602, "Invalid params")
    assert error_of(server.handle(req("tools/call", {}))) == (-32602, "Unknown tool: None")


@pytest.mark.parametrize("name, arguments, message", [
    ("order_status", {}, "Invalid arguments: missing order_id"),
    ("order_status", {"order_id": 7}, "Invalid arguments: order_id must be string"),
    ("order_status", {"order_id": "A1", "extra": 1}, "Invalid arguments: unknown extra"),
    ("add", {}, "Invalid arguments: missing a, missing b"),
    ("add", {"b": "x", "z": 0}, "Invalid arguments: missing a, b must be number, unknown z"),
    ("add", {"a": True, "b": 1}, "Invalid arguments: a must be number"),
    ("count", {"n": 1.5}, "Invalid arguments: n must be integer"),
    ("count", {"n": True}, "Invalid arguments: n must be integer"),
    ("count", {"flag": 1, "xs": {}, "o": []}, "Invalid arguments: flag must be boolean, xs must be array, o must be object"),
])
def test_argument_validation(server, name, arguments, message):
    assert error_of(call(server, name, arguments)) == (-32602, message)


def test_valid_typed_arguments(server):
    assert call(server, "count", {"n": 1, "flag": False, "xs": [1], "o": {}})["result"]["content"][0]["text"] == "4"


# ---------- resources ------------------------------------------------------------------------------------------------------------


def test_resources(server):
    assert server.handle(req("resources/list"))["result"] == {"resources": [{"uri": "docs://faq", "name": "FAQ", "mimeType": "text/markdown"}]}
    assert server.handle(req("resources/read", {"uri": "docs://faq"}))["result"] == {
        "contents": [{"uri": "docs://faq", "mimeType": "text/markdown", "text": "# FAQ\nПовернення за 14 днів"}]}
    assert error_of(server.handle(req("resources/read", {"uri": "docs://nope"}))) == (-32602, "Resource not found: docs://nope")
    assert error_of(server.handle(req("resources/read", "docs://faq"))) == (-32602, "Invalid params")


# ---------- batches and JSON --------------------------------------------------------------------------------------------------------


def test_batch_keeps_order_and_skips_notifications(server):
    batch = [req("ping", id=10), req("notifications/initialized", id=None), req("nope", id=11), {"bad": True}, req("tools/list", id="t")]
    out = server.handle(batch)
    assert [r["id"] for r in out] == [10, 11, None, "t"]
    assert out[0]["result"] == {} and out[1]["error"]["code"] == -32601 and out[2]["error"]["code"] == -32600 and "tools" in out[3]["result"]


def test_batch_of_only_notifications_has_no_response(server):
    assert server.handle([req("ping", id=None), req("nope", id=None)]) is None


def test_handle_accepts_json_strings_and_handle_json_serialises(server):
    out = server.handle(json.dumps(req("ping", id=5)))
    assert out == {"jsonrpc": "2.0", "id": 5, "result": {}}
    text = server.handle_json(json.dumps(req("tools/call", {"name": "greet", "arguments": {"name": "Анна"}}, 3)))
    assert "Анна" in text and json.loads(text)["result"]["content"][0]["text"] == "hello Анна", "не екранувати кирилицю"
    assert json.loads(server.handle_json("{oops"))["error"]["code"] == -32700
    assert json.loads(server.handle_json(json.dumps([req("ping", id=1), req("ping", id=2)]))) == [
        {"jsonrpc": "2.0", "id": 1, "result": {}}, {"jsonrpc": "2.0", "id": 2, "result": {}}]
