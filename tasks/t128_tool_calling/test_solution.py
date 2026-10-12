import json

import pytest

from solution import Tool, run_conversation, tool_schemas, validate_args

ORDERS = {"A1": {"id": "A1", "status": "shipped", "total": 12.5}}


def get_order(order_id):
    if order_id not in ORDERS:
        raise KeyError(order_id)
    return ORDERS[order_id]


def convert(amount, currency="EUR"):
    return {"amount": round(amount * 1.1, 2), "currency": currency}


def big(n):
    return "x" * n


TOOLS = [
    Tool("get_order", "Знайти замовлення", {"properties": {"order_id": {"type": "string"}}, "required": ["order_id"]}, get_order),
    Tool("convert", "Конвертувати валюту", {"properties": {"amount": {"type": "number"}, "currency": {"type": "string"}}, "required": ["amount"]}, convert),
    Tool("big", "Великий результат", {"properties": {"n": {"type": "integer"}}, "required": ["n"]}, big),
    Tool("ping", "Без аргументів", {}, lambda: "pong"),
]


def call(id, name, **args):
    return {"id": id, "name": name, "arguments": json.dumps(args)}


class ScriptedLLM:
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def __call__(self, messages, tools):
        self.calls.append((messages, tools))
        return self.replies[min(len(self.calls) - 1, len(self.replies) - 1)]


# ---------- schemas and validation --------------------------------------------------------------


def test_tool_schemas():
    schemas = tool_schemas(TOOLS)
    assert schemas[0] == {"type": "function", "function": {
        "name": "get_order", "description": "Знайти замовлення",
        "parameters": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]}}}
    assert schemas[3]["function"]["parameters"] == {"type": "object", "properties": {}, "required": []}


@pytest.mark.parametrize("args, errors", [
    ({"order_id": "A1"}, []),
    ({}, ["missing:order_id"]),
    ({"order_id": 5}, ["type:order_id:string"]),
    ({"order_id": "A1", "extra": 1}, ["unknown:extra"]),
    ({"extra": 1, "z": 2}, ["missing:order_id", "unknown:extra", "unknown:z"]),
])
def test_validate_args(args, errors):
    assert validate_args(TOOLS[0].parameters, args) == errors


@pytest.mark.parametrize("value, ok", [(5, True), (5.5, True), (True, False), ("5", False), (None, False)])
def test_number_type(value, ok):
    assert (validate_args({"properties": {"x": {"type": "number"}}}, {"x": value}) == []) is ok


@pytest.mark.parametrize("value, ok", [(5, True), (5.0, False), (True, False), ("5", False)])
def test_integer_type(value, ok):
    assert (validate_args({"properties": {"x": {"type": "integer"}}}, {"x": value}) == []) is ok


def test_other_types():
    schema = {"properties": {"b": {"type": "boolean"}, "a": {"type": "array"}, "o": {"type": "object"}}}
    assert validate_args(schema, {"b": True, "a": [1], "o": {}}) == []
    assert validate_args(schema, {"b": 1, "a": {}, "o": []}) == ["type:a:array", "type:b:boolean", "type:o:object"]


# ---------- conversation ---------------------------------------------------------------------------


def test_direct_answer_without_tools():
    llm = ScriptedLLM({"content": "Привіт!"})
    result = run_conversation(llm, TOOLS, "hi", system="be nice")
    assert result["answer"] == "Привіт!" and result["status"] == "final" and result["tool_calls"] == 0
    assert result["messages"] == [{"role": "system", "content": "be nice"}, {"role": "user", "content": "hi"}]
    assert llm.calls[0][1] == tool_schemas(TOOLS)


def test_no_system_message_and_empty_answer():
    result = run_conversation(ScriptedLLM({"content": None, "tool_calls": []}), TOOLS, "hi")
    assert result["messages"] == [{"role": "user", "content": "hi"}] and result["answer"] == ""


def test_one_tool_round():
    llm = ScriptedLLM({"content": None, "tool_calls": [call("c1", "get_order", order_id="A1")]}, {"content": "Замовлення відправлено"})
    result = run_conversation(llm, TOOLS, "де A1?")
    assert result["answer"] == "Замовлення відправлено" and result["status"] == "final" and result["tool_calls"] == 1
    assert result["messages"][1:] == [
        {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "type": "function", "function": {
            "name": "get_order", "arguments": '{"order_id": "A1"}'}}]},
        {"role": "tool", "tool_call_id": "c1", "content": '{"id": "A1", "status": "shipped", "total": 12.5}'},
    ]
    second_messages = llm.calls[1][0]
    assert [m["role"] for m in second_messages] == ["user", "assistant", "tool"]


def test_llm_receives_a_copy_of_messages():
    llm = ScriptedLLM({"content": None, "tool_calls": [call("c1", "ping")]}, {"content": "done"})
    run_conversation(llm, TOOLS, "go")
    assert len(llm.calls[0][0]) == 1, "перший виклик бачив лише user-повідомлення, хоча список потім виріс"


def test_parallel_tool_calls_each_get_one_result_in_order():
    llm = ScriptedLLM({"content": "шукаю", "tool_calls": [call("a", "get_order", order_id="A1"), call("b", "convert", amount=10), call("c", "ping")]},
                      {"content": "ok"})
    result = run_conversation(llm, TOOLS, "q")
    tool_msgs = [m for m in result["messages"] if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in tool_msgs] == ["a", "b", "c"]
    assert tool_msgs[1]["content"] == '{"amount": 11.0, "currency": "EUR"}' and tool_msgs[2]["content"] == '"pong"'
    assert result["messages"][1]["content"] == "шукаю" and result["tool_calls"] == 3


@pytest.mark.parametrize("name, arguments, error", [
    ("get_order", "{not json", "invalid JSON arguments"),
    ("get_order", "[1, 2]", "arguments must be an object"),
    ("get_order", "null", "arguments must be an object"),
    ("get_order", None, "invalid JSON arguments"),
    ("nope", "{}", "unknown tool: nope"),
    ("get_order", "{}", "invalid arguments: missing:order_id"),
    ("get_order", '{"order_id": 7, "x": 1}', "invalid arguments: type:order_id:string, unknown:x"),
    ("get_order", '{"order_id": "ZZ"}', "tool failed: KeyError: 'ZZ'"),
])
def test_errors_become_tool_messages_and_the_loop_continues(name, arguments, error):
    llm = ScriptedLLM({"tool_calls": [{"id": "c1", "name": name, "arguments": arguments}]}, {"content": "вибач"})
    result = run_conversation(llm, TOOLS, "q")
    assert json.loads(result["messages"][-1]["content"]) == {"error": error}
    assert result["answer"] == "вибач" and result["status"] == "final" and result["tool_calls"] == 1


def test_a_failed_call_does_not_stop_the_other_calls():
    llm = ScriptedLLM({"tool_calls": [call("a", "get_order", order_id="ZZ"), call("b", "ping")]}, {"content": "ok"})
    msgs = run_conversation(llm, TOOLS, "q")["messages"]
    assert "error" in msgs[-2]["content"] and msgs[-1]["content"] == '"pong"'


def test_long_results_are_truncated():
    llm = ScriptedLLM({"tool_calls": [call("a", "big", n=50)]}, {"content": "ok"})
    content = run_conversation(llm, TOOLS, "q", max_result_chars=10)["messages"][-1]["content"]
    assert content == '"xxxxxxxxx…[truncated]'
    exact = run_conversation(ScriptedLLM({"tool_calls": [call("a", "big", n=8)]}, {"content": "ok"}), TOOLS, "q", max_result_chars=10)
    assert exact["messages"][-1]["content"] == '"' + "x" * 8 + '"', "рівно 10 символів: не обрізається"


def test_non_ascii_results_stay_readable():
    tools = [Tool("hi", "d", {}, lambda: {"привіт": "світ"})]
    llm = ScriptedLLM({"tool_calls": [call("a", "hi")]}, {"content": "ok"})
    assert run_conversation(llm, tools, "q")["messages"][-1]["content"] == '{"привіт": "світ"}'


def test_max_rounds_stops_without_executing_the_last_calls():
    ran = []
    tools = [Tool("t", "d", {}, lambda: ran.append(1) or "x")]
    llm = ScriptedLLM({"tool_calls": [call("a", "t")]})
    result = run_conversation(llm, tools, "q", max_rounds=3)
    assert result["status"] == "max_rounds" and result["answer"] is None
    assert len(llm.calls) == 3 and len(ran) == 2 and result["tool_calls"] == 2
    assert result["messages"][-1]["role"] == "tool"


def test_final_answer_on_the_last_allowed_round_is_accepted():
    llm = ScriptedLLM({"tool_calls": [call("a", "ping")]}, {"content": "готово"})
    result = run_conversation(llm, TOOLS, "q", max_rounds=2)
    assert result["status"] == "final" and result["answer"] == "готово"


def test_one_round_only():
    llm = ScriptedLLM({"tool_calls": [call("a", "ping")]})
    result = run_conversation(llm, TOOLS, "q", max_rounds=1)
    assert result["status"] == "max_rounds" and result["tool_calls"] == 0
