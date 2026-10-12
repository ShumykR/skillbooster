"""Завдання №131: Evals: еталонний датасет, перевірки відповідей, LLM-as-judge і регресійний гейт для CI.

Зміна промпту «на око» виправляє один кейс і ламає три. Eval це набір кейсів із автоматичними перевірками, який запускається при кожній
зміні промпту чи моделі, як юніт-тести для LLM. Модель (SUT) і суддя тут звичайні функції, тож завдання детерміноване.

Case = {"id": str, "input": str, "checks": [check, ...], "tag": str (необовʼязково)}
check = {"type": ..., ...}:
    "exact"        {"value"}                    output.strip() == value.strip()
    "contains"     {"value"}                    value in output
    "not_contains" {"value"}                    value not in output   (заборонена фраза, витік секрету)
    "regex"        {"pattern"}                  re.search(pattern, output)
    "max_chars"    {"value": n}                 len(output) <= n
    "json"         {"path", "value"}            output це JSON (навколо може бути огорожа ```/```json, її зняти); path це ключі через крапку,
                                                числа в path індекси списків ("items.0.name"); значення за шляхом == value. Не JSON,
                                                шляху немає: перевірка не пройдена.
    "judge"        {"criteria", "min_score": 4}  оцінка судді >= min_score (див. нижче)
    Для exact/contains/not_contains/regex необовʼязковий "ignore_case": True. Невідомий type: ValueError.

grade(output, check, *, input="", judge=None) -> str | None
    None, якщо перевірку пройдено, інакше її мітку невдачі: type перевірки; для judge: "judge" (оцінка нижча за поріг),
    "judge_unparsable" (у відповіді судді немає "SCORE: n", n в 1..5; береться перший збіг), "judge_error" (суддя кинув Exception).
    judge(prompt) -> str. prompt складається з рядків через "\n":
      "You are a strict grader. Rate the answer from 1 to 5 against the criteria.", f"Criteria: {criteria}", f"Question: {input}",
      f"Answer: {output}", "Reply with: SCORE: <number>".

run_eval(sut, cases, *, judge=None, repeats=1, pass_threshold=1.0) -> dict
    Якщо є judge-перевірка, а judge None: ValueError (до запуску). sut(input) -> str. Для кожного кейсу sut викликається repeats разів;
    повтор проходить, якщо всі checks пройдені (виняток sut Exception: повтор провалений з міткою "error"). Кейс проходить, якщо
    частка пройдених повторів >= pass_threshold. Результат кейсу:
      {"id", "passed", "pass_count", "repeats", "failures": відсортовані унікальні мітки з усіх провалених повторів, "output": відповідь
       останнього повтору ("" якщо він завершився винятком)}.
    Підсумок: {"total", "passed", "pass_rate": passed / total (4 знаки; 0.0 без кейсів), "results": [...] у порядку cases,
               "by_tag": {tag: {"total", "passed"}} для кейсів із tag}.
    repeats < 1 або pass_threshold не в (0, 1]: ValueError. Дублікати id: ValueError.

compare_runs(baseline, current, *, tolerance=0.0) -> dict
    baseline і current це підсумки run_eval. {"regressions": id, що пройшли в baseline і не проходять тепер (відсортовано),
    "fixed": навпаки, "new_cases": id лише в current, "removed_cases": id лише в baseline (усі відсортовані),
    "pass_rate_delta": round(current - baseline, 4), "ok": немає regressions і pass_rate_delta >= -tolerance}.
"""

import json  # noqa: F401
import re  # noqa: F401


def grade(output: str, check: dict, *, input: str = "", judge=None) -> str | None:
    raise NotImplementedError


def run_eval(sut, cases: list[dict], *, judge=None, repeats: int = 1, pass_threshold: float = 1.0) -> dict:
    raise NotImplementedError


def compare_runs(baseline: dict, current: dict, *, tolerance: float = 0.0) -> dict:
    raise NotImplementedError
