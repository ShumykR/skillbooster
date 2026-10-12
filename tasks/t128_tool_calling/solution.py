"""Завдання №128: Tool calling: модель викликає ваші функції (пошук замовлення, курс валют), цикл виконання.

Формат як у OpenAI-сумісних API. Модель `llm(messages, tools)` приймає список повідомлень і схеми інструментів та повертає
повідомлення асистента: {"content": str | None, "tool_calls": [{"id": "c1", "name": "get_order", "arguments": "{\"order_id\": \"A1\"}"}]}
(`arguments` це РЯДОК із JSON, як приходить від моделі; tool_calls може бути відсутнім або порожнім).

Tool(name, description, parameters, fn)
    parameters: {"properties": {"order_id": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["order_id"]};
    типи: "string", "integer", "number", "boolean", "array", "object". fn(**args) -> JSON-серіалізований результат.

tool_schemas(tools) -> list[dict]
    [{"type": "function", "function": {"name", "description", "parameters": {"type": "object", "properties": ..., "required": [...]}}}, ...]
    (required, якого немає у parameters, стає []).

validate_args(parameters, args) -> list[str]
    Відсортований список помилок: "missing:<поле>" (обовʼязкового немає), "unknown:<поле>" (немає у properties), "type:<поле>:<очікуваний>".
    bool не є integer і не є number; integer підходить для number; рядок "5" не підходить для integer.

run_conversation(llm, tools, user_message, *, system=None, max_rounds=5, max_result_chars=2000) -> dict
    messages починається з [{"role": "system", "content": system}] (лише якщо system не None) і {"role": "user", "content": user_message}.
    Раунд: викликається llm(копія messages, tool_schemas(tools)). Усього не більше max_rounds викликів llm.
      * Немає tool_calls: готово, {"answer": content or "", "status": "final", ...}.
      * Є tool_calls і це вже max_rounds-й виклик: інструменти НЕ виконуються, {"answer": None, "status": "max_rounds", ...}.
      * Інакше до messages додається повідомлення асистента
          {"role": "assistant", "content": content, "tool_calls": [{"id", "type": "function", "function": {"name", "arguments"}}, ...]}
        і для КОЖНОГО виклику рівно одне повідомлення {"role": "tool", "tool_call_id": id, "content": <рядок JSON>} у тому ж порядку.
        Вміст tool-повідомлення:
          невалідний JSON в arguments: {"error": "invalid JSON arguments"};  JSON не обʼєкт: {"error": "arguments must be an object"};
          невідомий інструмент: {"error": "unknown tool: <імʼя>"};
          validate_args непорожній: {"error": "invalid arguments: <помилки через ', '>"};
          виняток інструмента: {"error": "tool failed: <ТипВинятку>: <текст>"};
          успіх: json.dumps(результат, ensure_ascii=False, sort_keys=True); довше за max_result_chars обрізається до цієї довжини плюс "…[truncated]".
        Помилки інструментів НЕ валять цикл: їх бачить модель і може виправитись.
    Результат {"answer", "status": "final" | "max_rounds", "messages": повний список, "tool_calls": скільки викликів інструментів
    розпізнано й оброблено (включно з помилковими)}.
"""

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    fn: Callable[..., Any]


def tool_schemas(tools: list[Tool]) -> list[dict]:
    raise NotImplementedError


def validate_args(parameters: dict, args: dict) -> list[str]:
    raise NotImplementedError


def run_conversation(llm, tools: list[Tool], user_message: str, *, system: str | None = None, max_rounds: int = 5,
                     max_result_chars: int = 2000) -> dict:
    raise NotImplementedError
