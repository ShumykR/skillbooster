"""Завдання №136: MCP-сервер: обгортка над вашим API з tools і resources (ядро протоколу на JSON-RPC 2.0).

Model Context Protocol це JSON-RPC 2.0: клієнт (застосунок з LLM) питає, які інструменти й ресурси є, і викликає їх. Транспорт (stdio чи HTTP)
тут не потрібен: реалізуй обробник повідомлень, який потім підключається до справжнього SDK.

Tool = {"name", "description", "inputSchema": {"type": "object", "properties": {...}, "required": [...]}, "handler": fn(**arguments)}
Resource = {"uri": {"name", "mimeType", "read": fn() -> str}}  (resources це словник uri -> опис)

McpServer(name, version, tools=(), resources=None)
    .initialized -> bool                       True після успішного виклику методу "initialize".
    .handle(message) -> dict | list | None     message: словник, список (batch) або рядок з JSON.
    .handle_json(text) -> str | None           handle, а результат серіалізований через json.dumps(ensure_ascii=False); None, якщо відповіді немає.

Правила handle:
    * рядок, що не є JSON: {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}};
    * не словник і не список, словник без "jsonrpc": "2.0" або з method не рядком: -32600 "Invalid Request" (id береться з повідомлення, якщо
      воно є, інакше None); порожній список: одна відповідь -32600 з id None (не список);
    * список: кожен елемент обробляється окремо, відповіді (без None) збираються у список у тому ж порядку; якщо відповідей немає, результат None;
    * повідомлення без ключа "id" це notification: відповіді НЕ буде (None), навіть якщо метод невідомий чи параметри хибні;
    * успіх: {"jsonrpc": "2.0", "id": id, "result": ...}; помилка: {"jsonrpc": "2.0", "id": id, "error": {"code": int, "message": str}}.
    Методи (params необовʼязкові, якщо не сказано інше; params не словник там, де вони потрібні, це -32602 "Invalid params"):
      "initialize"      -> {"protocolVersion": "2024-11-05", "capabilities": {"tools": {} (лише якщо є tools), "resources": {} (лише якщо є
                           resources)}, "serverInfo": {"name", "version"}}; після нього initialized = True.
      "ping"            -> {} (дозволений і до initialize).
      Решта методів до initialize: -32002 "Server not initialized".
      "tools/list"      -> {"tools": [{"name", "description", "inputSchema"}, ...]} (без handler) у порядку реєстрації.
      "tools/call"      params {"name", "arguments": {...} (типово {})}: невідомий інструмент: -32602 "Unknown tool: <name>"; аргументи, що не
                           проходять схему (відсутні required, невідомі властивості, типи string/integer/number/boolean/array/object; bool не є
                           integer/number): -32602 "Invalid arguments: <помилки через ', '>" де помилки це "missing <поле>", "unknown <поле>",
                           "<поле> must be <тип>" у порядку: спершу всі missing (за порядком required), потім за порядком аргументів unknown чи
                           type-помилка. Успіх: {"content": [{"type": "text", "text": текст}], "isError": False}, де текст = результат, якщо це
                           рядок, інакше json.dumps(результат, ensure_ascii=False, sort_keys=True). Виняток handler: НЕ протокольна помилка, а
                           результат {"content": [{"type": "text", "text": "Tool failed: <Тип>: <текст>"}], "isError": True}.
      "resources/list"  -> {"resources": [{"uri", "name", "mimeType"}, ...]} у порядку словника.
      "resources/read"  params {"uri"}: невідомий uri: -32602 "Resource not found: <uri>"; успіх {"contents": [{"uri", "mimeType", "text": read()}]}.
      будь-який інший метод: -32601 "Method not found".
"""

import json  # noqa: F401


class McpServer:
    def __init__(self, name: str, version: str, tools=(), resources: dict | None = None) -> None:
        raise NotImplementedError

    @property
    def initialized(self) -> bool:
        raise NotImplementedError

    def handle(self, message):
        raise NotImplementedError

    def handle_json(self, text: str) -> str | None:
        raise NotImplementedError
