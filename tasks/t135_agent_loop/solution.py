"""Завдання №135: Цикл агента з запобіжниками.

Агент: модель на кожному кроці або викликає інструмент, або дає фінальну відповідь.
`llm` тут функція messages -> dict, тож завдання не залежить від провайдера:
    {"tool": "search", "args": {"q": "..."}}   # викликати інструмент
    {"final": "відповідь"}                      # завершити
"""
import json
from typing import Any, Callable


def run_agent(
    llm: Callable[[list[dict]], dict],
    tools: dict[str, Callable[..., Any]],
    question: str,
    *,
    max_steps: int = 5,
) -> dict:
    """Повертає {"answer": str | None, "steps": int, "stopped": "final" | "max_steps" | "loop"}.

    Правила:
    - messages починається з [{"role": "user", "content": question}];
    - `steps` = кількість викликів llm;
    - при {"final": ...} повертаємо answer і stopped="final";
    - при виклику інструмента: до messages додається
        {"role": "assistant", "content": <json.dumps(call, sort_keys=True)>}
        {"role": "tool", "name": <імʼя>, "content": <результат як str>}
    - невідомий інструмент або виняток інструмента НЕ валить агента: у "content"
      записується рядок, що починається з "ERROR:", і цикл триває;
    - спостереження довші за 500 символів обрізаються до 500;
    - якщо ТОЙ САМИЙ виклик (імʼя + args) просять утретє, не виконуй його,
      заверши зі stopped="loop" і answer=None;
    - якщо за max_steps викликів llm фінальної відповіді немає: stopped="max_steps", answer=None;
    - args передаються в інструмент як **kwargs.
    """
    raise NotImplementedError
